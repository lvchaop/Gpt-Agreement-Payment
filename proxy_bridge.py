#!/usr/bin/env python3
"""Trojan pool -> local HTTP proxy bridge helpers.

The pipeline needs stable per-stage proxy URLs while existing code only accepts
ordinary HTTP/SOCKS proxy strings.  This module keeps that boundary explicit:
Trojan nodes are bridged by sing-box to local HTTP ports, then the rest of the
project consumes those local HTTP URLs.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import threading
import time
import urllib.parse
from typing import Any


PAYMENT_STAGE_PROXY_KEYS = (
    "fingerprint",
    "fetch_publishable_key",
    "stripe_init",
    "telemetry_init",
    "elements",
    "link_lookup",
    "address",
    "telemetry_address",
    "telemetry_card_input",
    "payment_method",
    "telemetry_confirm",
    "confirm",
    "verify_challenge_browser",
    "verify_challenge",
    "three_ds_authenticate",
    "setup_intent_poll",
    "manual_approval_redirect",
    "telemetry_poll",
    "poll",
)


class TrojanBridgeError(RuntimeError):
    pass


@dataclass(frozen=True)
class TrojanNode:
    region: str
    url: str
    name: str
    local_http_port: int
    index: int

    @property
    def local_http_url(self) -> str:
        return f"http://127.0.0.1:{self.local_http_port}"


@dataclass
class ProxyStagePlan:
    register: str = ""
    checkout: str = ""
    payment: str = ""
    source: str = ""
    register_region: str = ""
    checkout_region: str = ""
    payment_region: str = ""

    @classmethod
    def from_obj(cls, value: Any) -> "ProxyStagePlan":
        if isinstance(value, cls):
            return cls(**value.to_dict())
        if isinstance(value, dict):
            return cls(
                register=str(value.get("register") or ""),
                checkout=str(value.get("checkout") or ""),
                payment=str(value.get("payment") or ""),
                source=str(value.get("source") or ""),
                register_region=str(value.get("register_region") or ""),
                checkout_region=str(value.get("checkout_region") or ""),
                payment_region=str(value.get("payment_region") or ""),
            )
        return cls()

    def to_dict(self) -> dict:
        return {
            "register": self.register,
            "checkout": self.checkout,
            "payment": self.payment,
            "source": self.source,
            "register_region": self.register_region,
            "checkout_region": self.checkout_region,
            "payment_region": self.payment_region,
        }

    def has_any(self) -> bool:
        return bool(self.register or self.checkout or self.payment)


def _truthy(value: str) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _first_query(query: dict[str, list[str]], *keys: str) -> str:
    for key in keys:
        values = query.get(key)
        if values:
            return urllib.parse.unquote(str(values[0] or ""))
    return ""


def _region_key(value: str) -> str:
    return str(value or "").strip().upper()


def _name_from_trojan_url(url: str, fallback: str) -> str:
    try:
        parsed = urllib.parse.urlsplit(url)
        if parsed.fragment:
            return urllib.parse.unquote(parsed.fragment).strip() or fallback
    except Exception:
        pass
    return fallback


def _region_from_trojan_url(url: str) -> str:
    try:
        parsed = urllib.parse.urlsplit(url)
        query = urllib.parse.parse_qs(parsed.query)
        return _region_key(_first_query(query, "region", "country", "group"))
    except Exception:
        return ""


def _parse_pool_line(line: str, index: int) -> tuple[str, str, str]:
    text = line.strip()
    if not text or text.startswith("#"):
        raise ValueError("empty")

    if text.startswith("{"):
        item = json.loads(text)
        return _parse_pool_item(item, index)

    if text.startswith("trojan://"):
        region = _region_from_trojan_url(text) or "default"
        return region, text, _name_from_trojan_url(text, f"{region}-{index + 1}")

    for sep in (",", "\t", " "):
        if sep in text:
            left, right = text.split(sep, 1)
            region = left.strip()
            url = right.strip()
            if url.startswith("trojan://"):
                return region, url, _name_from_trojan_url(url, f"{region}-{index + 1}")

    if "=" in text:
        region, url = text.split("=", 1)
        if url.strip().startswith("trojan://"):
            return region.strip(), url.strip(), _name_from_trojan_url(url.strip(), f"{region.strip()}-{index + 1}")

    raise ValueError(f"无法解析 Trojan 池行: {line[:80]}")


def _parse_pool_item(item: Any, index: int) -> tuple[str, str, str]:
    if isinstance(item, str):
        return _parse_pool_line(item, index)
    if not isinstance(item, dict):
        raise ValueError("Trojan 池 JSON 项必须是对象或字符串")

    url = str(item.get("url") or item.get("trojan") or "").strip()
    if not url.startswith("trojan://"):
        raise ValueError("Trojan 池项缺少 trojan:// url")
    region = (
        str(item.get("region") or item.get("country") or item.get("group") or "").strip()
        or _region_from_trojan_url(url)
        or "default"
    )
    name = str(item.get("name") or item.get("tag") or "").strip()
    if not name:
        name = _name_from_trojan_url(url, f"{region}-{index + 1}")
    return region, url, name


def load_trojan_pool(path: str | os.PathLike[str], *, http_start_port: int = 18081) -> list[TrojanNode]:
    pool_path = Path(path).expanduser()
    if not pool_path.exists():
        raise TrojanBridgeError(f"Trojan 池文件不存在: {pool_path}")

    raw = pool_path.read_text(encoding="utf-8").strip()
    if not raw:
        raise TrojanBridgeError(f"Trojan 池文件为空: {pool_path}")

    parsed_items: list[Any]
    if raw[0] in "[{":
        data = json.loads(raw)
        if isinstance(data, dict):
            parsed_items = data.get("nodes") or data.get("proxies") or []
        else:
            parsed_items = data
    else:
        parsed_items = [line for line in raw.splitlines() if line.strip() and not line.strip().startswith("#")]

    nodes: list[TrojanNode] = []
    for raw_index, item in enumerate(parsed_items):
        try:
            region, url, name = _parse_pool_item(item, raw_index)
        except ValueError as e:
            raise TrojanBridgeError(str(e)) from e
        nodes.append(
            TrojanNode(
                region=_region_key(region) or "DEFAULT",
                url=url,
                name=name,
                local_http_port=int(http_start_port) + len(nodes),
                index=len(nodes),
            )
        )

    if not nodes:
        raise TrojanBridgeError(f"Trojan 池没有可用节点: {pool_path}")
    return nodes


def _trojan_outbound(node: TrojanNode) -> dict:
    parsed = urllib.parse.urlsplit(node.url)
    if parsed.scheme != "trojan":
        raise TrojanBridgeError(f"非 trojan URL: {node.url[:80]}")
    host = parsed.hostname or ""
    if not host:
        raise TrojanBridgeError(f"Trojan URL 缺 host: {node.url[:80]}")
    password = urllib.parse.unquote(parsed.username or "")
    if not password:
        raise TrojanBridgeError(f"Trojan URL 缺 password: {node.name}")

    query = urllib.parse.parse_qs(parsed.query)
    outbound = {
        "type": "trojan",
        "tag": f"trojan-{node.index}",
        "server": host,
        "server_port": int(parsed.port or 443),
        "password": password,
    }

    security = _first_query(query, "security", "tls")
    if str(security or "tls").lower() not in {"none", "false", "0"}:
        tls = {"enabled": True}
        server_name = _first_query(query, "sni", "peer", "servername", "serverName")
        if server_name:
            tls["server_name"] = server_name
        insecure = _first_query(query, "allowInsecure", "insecure", "skip-cert-verify", "skip_cert_verify")
        if _truthy(insecure):
            tls["insecure"] = True
        alpn = _first_query(query, "alpn")
        if alpn:
            tls["alpn"] = [p.strip() for p in alpn.split(",") if p.strip()]
        outbound["tls"] = tls

    transport_type = _first_query(query, "type", "transport")
    if transport_type.lower() in {"ws", "websocket"}:
        transport = {
            "type": "ws",
            "path": _first_query(query, "path") or "/",
        }
        host_header = _first_query(query, "host")
        if host_header:
            transport["headers"] = {"Host": host_header}
        outbound["transport"] = transport

    return outbound


def build_sing_box_config(nodes: list[TrojanNode]) -> dict:
    inbounds = []
    outbounds = [{"type": "direct", "tag": "direct"}]
    rules = []

    for node in nodes:
        in_tag = f"http-{node.index}"
        out_tag = f"trojan-{node.index}"
        inbounds.append(
            {
                "type": "http",
                "tag": in_tag,
                "listen": "127.0.0.1",
                "listen_port": node.local_http_port,
            }
        )
        outbounds.append(_trojan_outbound(node))
        rules.append({"inbound": [in_tag], "outbound": out_tag})

    return {
        "log": {"level": "warn"},
        "inbounds": inbounds,
        "outbounds": outbounds,
        "route": {"rules": rules, "final": "direct"},
    }


def _port_open(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", int(port)), timeout=0.2):
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


class TrojanBridgeManager:
    def __init__(
        self,
        pool_file: str,
        *,
        http_start_port: int = 18081,
        work_dir: str | os.PathLike[str] = "output/proxy_bridge",
        executable: str = "sing-box",
        auto_start: bool = True,
    ):
        self.pool_file = str(pool_file)
        self.http_start_port = int(http_start_port)
        self.work_dir = Path(work_dir)
        self.executable = executable
        self.auto_start = auto_start
        self.nodes = load_trojan_pool(pool_file, http_start_port=http_start_port)
        self._lock = threading.Lock()
        self._counters: dict[str, int] = {}

    @property
    def regions(self) -> list[str]:
        return sorted({node.region for node in self.nodes})

    def ensure_started(self) -> None:
        self.work_dir.mkdir(parents=True, exist_ok=True)
        config_path = self.work_dir / "sing-box.trojan-pool.json"
        pid_path = self.work_dir / "sing-box.pid"
        log_path = self.work_dir / "sing-box.log"

        config = build_sing_box_config(self.nodes)
        config_path.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")

        if all(_port_open(node.local_http_port) for node in self.nodes):
            print("[trojan] 本地 HTTP 端口已全部可用，复用现有 bridge")
            return

        if pid_path.exists():
            try:
                pid = int(pid_path.read_text(encoding="utf-8").strip() or "0")
            except Exception:
                pid = 0
            if _pid_alive(pid):
                print(f"[trojan] sing-box 已在运行 pid={pid}")
                return

        if not self.auto_start:
            raise TrojanBridgeError(
                "Trojan bridge 未启动；请先启动 sing-box，或去掉 --trojan-no-start"
            )

        exe = shutil.which(self.executable) or self.executable
        if not shutil.which(exe) and not Path(exe).exists():
            raise TrojanBridgeError(
                f"找不到 {self.executable}。请安装 sing-box，或用 --trojan-bridge-bin 指定路径"
            )

        with log_path.open("ab") as log_f:
            proc = subprocess.Popen(
                [exe, "run", "-c", str(config_path)],
                stdout=log_f,
                stderr=subprocess.STDOUT,
                cwd=str(self.work_dir),
                start_new_session=True,
            )
        pid_path.write_text(str(proc.pid), encoding="utf-8")
        time.sleep(0.8)
        if proc.poll() is not None:
            tail = ""
            try:
                tail = log_path.read_text(encoding="utf-8", errors="replace")[-1200:]
            except Exception:
                pass
            raise TrojanBridgeError(f"sing-box 启动失败 exit={proc.returncode}: {tail}")

        print(
            f"[trojan] sing-box bridge 已启动 pid={proc.pid} "
            f"nodes={len(self.nodes)} regions={','.join(self.regions)}"
        )

    def _pick_node(self, region: str) -> TrojanNode:
        wanted = _region_key(region) or "DEFAULT"
        candidates = [node for node in self.nodes if node.region == wanted]
        if not candidates and wanted == "DEFAULT":
            candidates = self.nodes
        if not candidates:
            raise TrojanBridgeError(
                f"Trojan 池没有 region={wanted} 的节点；可用 region={','.join(self.regions)}"
            )
        with self._lock:
            cursor = self._counters.get(wanted, 0)
            node = candidates[cursor % len(candidates)]
            self._counters[wanted] = cursor + 1
        return node

    def allocate_plan(
        self,
        *,
        all_region: str = "",
        register_region: str = "",
        checkout_region: str = "",
        payment_region: str = "",
    ) -> ProxyStagePlan:
        self.ensure_started()

        reg_region = _region_key(register_region or all_region or "default")
        chk_region = _region_key(checkout_region or register_region or all_region or reg_region)
        pay_region = _region_key(payment_region or checkout_region or register_region or all_region or chk_region)

        picked_by_region: dict[str, TrojanNode] = {}

        def pick(region: str) -> TrojanNode:
            key = _region_key(region) or "DEFAULT"
            if key not in picked_by_region:
                picked_by_region[key] = self._pick_node(key)
            return picked_by_region[key]

        reg_node = pick(reg_region)
        chk_node = pick(chk_region)
        pay_node = pick(pay_region)
        return ProxyStagePlan(
            register=reg_node.local_http_url,
            checkout=chk_node.local_http_url,
            payment=pay_node.local_http_url,
            source="trojan-pool",
            register_region=reg_node.region,
            checkout_region=chk_node.region,
            payment_region=pay_node.region,
        )

    def allocator(
        self,
        *,
        all_region: str = "",
        register_region: str = "",
        checkout_region: str = "",
        payment_region: str = "",
    ) -> "TrojanProxyStageAllocator":
        return TrojanProxyStageAllocator(
            self,
            all_region=all_region,
            register_region=register_region,
            checkout_region=checkout_region,
            payment_region=payment_region,
        )


class TrojanProxyStageAllocator:
    def __init__(
        self,
        manager: TrojanBridgeManager,
        *,
        all_region: str = "",
        register_region: str = "",
        checkout_region: str = "",
        payment_region: str = "",
    ):
        self.manager = manager
        self.all_region = all_region
        self.register_region = register_region
        self.checkout_region = checkout_region
        self.payment_region = payment_region

    def allocate(self) -> ProxyStagePlan:
        return self.manager.allocate_plan(
            all_region=self.all_region,
            register_region=self.register_region,
            checkout_region=self.checkout_region,
            payment_region=self.payment_region,
        )


def apply_payment_proxy_plan(
    cfg: dict,
    plan: ProxyStagePlan | dict | None = None,
    *,
    proxy_url: str = "",
    fresh_checkout_proxy_url: str = "",
    override_stage_proxies: bool = True,
    override_browser_challenge: bool = True,
) -> dict:
    """Apply stage proxies to a CTF-pay config dict in-place."""
    stage_plan = ProxyStagePlan.from_obj(plan)
    payment_proxy = stage_plan.payment or str(proxy_url or "").strip()
    checkout_proxy = (
        stage_plan.checkout
        or str(fresh_checkout_proxy_url or "").strip()
        or payment_proxy
    )

    if payment_proxy:
        cfg["proxy"] = payment_proxy

    if checkout_proxy:
        fresh_cfg = cfg.setdefault("fresh_checkout", {})
        fresh_cfg["proxy"] = checkout_proxy

    if payment_proxy and override_stage_proxies:
        stage_proxies = cfg.setdefault("stage_proxies", {})
        for stage in PAYMENT_STAGE_PROXY_KEYS:
            stage_proxies[stage] = payment_proxy

    if payment_proxy and override_browser_challenge:
        browser_cfg = cfg.setdefault("browser_challenge", {})
        browser_cfg["proxy_url"] = payment_proxy

    return cfg
