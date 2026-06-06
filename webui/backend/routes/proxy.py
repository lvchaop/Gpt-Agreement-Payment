"""出口代理控制（Webshare API 触发整池 IP 轮换）。

用于解决 `app.midtrans.com` 这种 Cloudflare 边缘节流（429 + 空 body）—
按 IP 限流，换 IP 即解。复用 `pipeline._rotate_webshare_ip`：
  1. POST Webshare /proxy/list/refresh/ 触发整池替换
  2. 轮询新 IP 直到不同于旧 IP
  3. swap gost 本地 relay 上游
  4. 可选：同步 team 全局代理（默认关）
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import signal
import socket
import time

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..auth import CurrentUser
from .. import settings as s


router = APIRouter(prefix="/api/proxy", tags=["proxy"])


class TrojanBridgeRequest(BaseModel):
    pool_file: str = "output/trojan_pool.txt"
    http_start_port: int = 18081
    bridge_bin: str = "sing-box"
    auto_start: bool = True


def _bridge_dir() -> Path:
    return s.ROOT / "output" / "proxy_bridge"


def _resolve_project_path(raw: str) -> Path:
    text = (raw or "").strip()
    if not text:
        return s.ROOT / "output" / "trojan_pool.txt"
    path = Path(text).expanduser()
    if not path.is_absolute():
        path = s.ROOT / path
    return path


def _port_open(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", int(port)), timeout=0.25):
            return True
    except OSError:
        return False


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _read_bridge_pid() -> int:
    pid_path = _bridge_dir() / "sing-box.pid"
    try:
        return int(pid_path.read_text(encoding="utf-8").strip() or "0")
    except Exception:
        return 0


def _read_bridge_nodes_from_config() -> list[dict]:
    config_path = _bridge_dir() / "sing-box.trojan-pool.json"
    try:
        cfg = json.loads(config_path.read_text(encoding="utf-8"))
    except Exception:
        return []
    nodes = []
    inbounds = cfg.get("inbounds") or []
    rules = ((cfg.get("route") or {}).get("rules") or [])
    inbound_to_outbound = {}
    for rule in rules:
        outbound = rule.get("outbound", "")
        for tag in rule.get("inbound") or []:
            inbound_to_outbound[tag] = outbound
    for inbound in inbounds:
        if inbound.get("type") != "http":
            continue
        port = int(inbound.get("listen_port") or 0)
        tag = inbound.get("tag", "")
        nodes.append({
            "tag": tag,
            "port": port,
            "url": f"http://127.0.0.1:{port}" if port else "",
            "outbound": inbound_to_outbound.get(tag, ""),
            "open": _port_open(port) if port else False,
        })
    return nodes


def _trojan_status(extra: dict | None = None) -> dict:
    pid = _read_bridge_pid()
    nodes = _read_bridge_nodes_from_config()
    running = _pid_alive(pid) and bool(nodes) and all(n.get("open") for n in nodes)
    return {
        "ok": running,
        "running": running,
        "pid": pid if _pid_alive(pid) else 0,
        "nodes": nodes,
        "config_path": str(_bridge_dir() / "sing-box.trojan-pool.json"),
        "pid_path": str(_bridge_dir() / "sing-box.pid"),
        **(extra or {}),
    }


def _read_pay_config() -> dict:
    try:
        return json.loads(Path(s.PAY_CONFIG_PATH).read_text(encoding="utf-8"))
    except Exception:
        return {}


@router.get("/current")
def get_current(user: str = CurrentUser):
    """读取当前 Webshare 池中的第一条代理（不触发轮换）。"""
    cfg = _read_pay_config()
    ws_cfg = (cfg.get("webshare") or {})
    if not ws_cfg.get("enabled"):
        raise HTTPException(status_code=400, detail="webshare 未启用")
    api_key = (ws_cfg.get("api_key") or "").strip()
    if not api_key:
        raise HTTPException(status_code=400, detail="webshare.api_key 为空")

    # 用 sys.path hack 而不是直接 import pipeline，避免触发 pipeline 顶部的
    # 副作用（建 OUTPUT_DIR/logs 等）。WebshareClient 只是个轻量 HTTP wrapper。
    import sys
    sys.path.insert(0, str(s.ROOT))
    try:
        from pipeline import WebshareClient
    finally:
        try:
            sys.path.remove(str(s.ROOT))
        except ValueError:
            pass

    try:
        client = WebshareClient(
            api_key,
            mode=str(ws_cfg.get("mode", "direct")),
            backbone_host=str(ws_cfg.get("backbone_host", "p.webshare.io")),
            country=str(ws_cfg.get("country", "")),
        )
        px = client.get_current_proxy()
        quota = client.get_replacement_quota()
        return {
            "ip": px.get("proxy_address"),
            "port": int(px.get("port", 0)),
            "country": px.get("country_code"),
            "asn": px.get("asn_name"),
            "valid": px.get("valid"),
            "quota": quota,
        }
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"webshare 查询失败: {e}")


@router.post("/rotate-ip")
def rotate_ip(user: str = CurrentUser):
    """触发整池 IP 轮换。同步换 gost 上游。Team 同步默认沿用配置中的开关。

    返回新 proxy 元信息。失败:
      400 - 配置不全 / webshare.enabled=false
      402 - quota 耗尽
      502 - Webshare API 异常
    """
    cfg = _read_pay_config()
    ws_cfg = (cfg.get("webshare") or {})
    if not ws_cfg.get("enabled"):
        raise HTTPException(status_code=400, detail="webshare 未启用，先在配置里 enable")
    if not (ws_cfg.get("api_key") or "").strip():
        raise HTTPException(status_code=400, detail="webshare.api_key 为空")

    import sys
    sys.path.insert(0, str(s.ROOT))
    try:
        from pipeline import _rotate_webshare_ip, WebshareQuotaExhausted, WebshareClient
    finally:
        try:
            sys.path.remove(str(s.ROOT))
        except ValueError:
            pass

    # 拿当前 IP 作为 prev_ip 参考，让 wait_for_fresh_proxy 能正确识别新 IP
    prev_ip = ""
    try:
        cur = WebshareClient(
            ws_cfg["api_key"],
            mode=str(ws_cfg.get("mode", "direct")),
            backbone_host=str(ws_cfg.get("backbone_host", "p.webshare.io")),
            country=str(ws_cfg.get("country", "")),
        ).get_current_proxy()
        prev_ip = cur.get("proxy_address", "") or ""
    except Exception:
        pass

    try:
        # 用户手动按按钮 → 跳过 _rotate_webshare_ip 的冷却（明确意图覆盖节流）
        new_px = _rotate_webshare_ip(cfg, team_client=None, prev_ip=prev_ip, force=True)
    except WebshareQuotaExhausted as e:
        raise HTTPException(status_code=402, detail=f"Webshare 替换额度耗尽: {e}")
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"IP 轮换失败: {e}")

    return {
        "ok": True,
        "prev_ip": prev_ip,
        "new_ip": new_px.get("proxy_address"),
        "port": int(new_px.get("port", 0)),
        "country": new_px.get("country_code"),
        "asn": new_px.get("asn_name"),
        "valid": new_px.get("valid"),
    }


@router.get("/trojan/status")
def trojan_status(user: str = CurrentUser):
    return _trojan_status()


@router.get("/trojan/nodes")
def trojan_nodes(pool_file: str = "output/trojan_pool.txt", http_start_port: int = 18081,
                 user: str = CurrentUser):
    try:
        from proxy_bridge import load_trojan_pool
        nodes = load_trojan_pool(_resolve_project_path(pool_file), http_start_port=http_start_port)
        return {
            "ok": True,
            "nodes": [
                {
                    "region": n.region,
                    "name": n.name,
                    "port": n.local_http_port,
                    "url": n.local_http_url,
                    "index": n.index,
                }
                for n in nodes
            ],
            "regions": sorted({n.region for n in nodes}),
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"代理池解析失败: {e}")


@router.post("/trojan/start")
def trojan_start(body: TrojanBridgeRequest, user: str = CurrentUser):
    try:
        from proxy_bridge import TrojanBridgeManager
        manager = TrojanBridgeManager(
            str(_resolve_project_path(body.pool_file)),
            http_start_port=body.http_start_port,
            work_dir=_bridge_dir(),
            executable=body.bridge_bin or "sing-box",
            auto_start=body.auto_start,
        )
        manager.ensure_started()
        nodes = [
            {
                "region": n.region,
                "name": n.name,
                "port": n.local_http_port,
                "url": n.local_http_url,
                "index": n.index,
                "open": _port_open(n.local_http_port),
            }
            for n in manager.nodes
        ]
        return _trojan_status({
            "ok": all(n.get("open") for n in nodes),
            "nodes": nodes,
            "regions": manager.regions,
            "pool_file": str(_resolve_project_path(body.pool_file)),
        })
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Trojan bridge 启动失败: {e}")


@router.post("/trojan/stop")
def trojan_stop(user: str = CurrentUser):
    pid = _read_bridge_pid()
    if not _pid_alive(pid):
        return _trojan_status({"ok": True, "stopped": True, "message": "bridge 未运行"})
    try:
        os.kill(pid, signal.SIGTERM)
        deadline = time.time() + 5
        while time.time() < deadline:
            if not _pid_alive(pid):
                break
            time.sleep(0.2)
        if _pid_alive(pid):
            os.kill(pid, signal.SIGKILL)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Trojan bridge 停止失败: {e}")
    return _trojan_status({"ok": True, "stopped": True})
