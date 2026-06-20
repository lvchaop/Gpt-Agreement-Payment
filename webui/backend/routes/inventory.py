"""Local account inventory: list, validate, delete, push to CPA."""
from __future__ import annotations

import json
import base64
import hashlib
import io
import random
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from collections import deque
from datetime import datetime, timezone
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from pathlib import Path

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel, Field

from ..auth import CurrentUser
from ..account_inventory import build_accounts_inventory
from ..account_validator import validate_accounts
from ..db import get_db
from .. import runner
from .. import settings as s


router = APIRouter(prefix="/api/inventory", tags=["inventory"])

_DEFAULT_CODEX_CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"
_CHATGPT_CODEX_RESPONSES_URL = "https://chatgpt.com/backend-api/codex/responses"
_OPENAI_DEFAULT_TEST_MODEL = "gpt-5.5"
_OPENAI_CODEX_INSTRUCTIONS_PATH = Path(__file__).resolve().parents[1] / "assets" / "openai_codex_instructions.txt"
_HEARTBEAT_RESULTS_DIR = s.ROOT / "output" / "heartbeat_results"


class IdsRequest(BaseModel):
    ids: list[int] = Field(default_factory=list)


class CheckRequest(IdsRequest):
    timeout_s: float = 10.0
    max_workers: int = 3


class HeartbeatRequest(IdsRequest):
    attempts: int = 40
    model: str = ""
    timeout_s: float = 30.0
    max_workers: int = 3


class TeamInviteAcceptRequest(IdsRequest):
    team_account_id: str = ""
    max_workers: int = 20
    timeout_s: float = 30.0


class SaleClaimRequest(BaseModel):
    note: str = ""


class SaleToggleRequest(BaseModel):
    id: int
    note: str = ""


class AuthExportRequest(IdsRequest):
    format: str = Field(default="cpa", pattern="^(cpa|sub2api)$")


def _load_cpa_cfg() -> dict:
    try:
        cfg = json.loads(s.PAY_CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"读 PAY_CONFIG_PATH 失败: {e}")
    cpa = (cfg.get("cpa") or {})
    if not cpa.get("enabled"):
        raise HTTPException(status_code=400,
                            detail="CPA 未启用：请先在 wizard Step11 填 base_url + admin_key 并启用")
    if not (cpa.get("base_url") and cpa.get("admin_key")):
        raise HTTPException(status_code=400, detail="CPA 配置缺 base_url 或 admin_key")
    return cpa


def _do_cpa_push(account: dict, cpa_cfg: dict) -> dict:
    """Run the CPA push for one account using pipeline._cpa_import_after_team.
    Records outcome to pipeline_results so inventory reflects new state."""
    import sys
    from pathlib import Path
    repo_root = Path(__file__).resolve().parents[3]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    import pipeline  # type: ignore

    email = account.get("email", "")
    rt = (account.get("refresh_token") or "").strip()
    is_free = False  # caller will set via plan_tag if needed; default False == use plan_tag
    try:
        status = pipeline._cpa_import_after_team(
            email, "", cpa_cfg, refresh_token=rt, is_free=is_free,
        )
    except Exception as e:
        status = f"error: {type(e).__name__}: {str(e)[:120]}"

    # 记一条 pipeline_results 让 inventory 的 cpa_status 能反映本次推送
    try:
        get_db().add_pipeline_result({
            "ts": datetime.now(timezone.utc).isoformat(),
            "mode": "cpa_push_manual",
            "status": "ok" if status == "ok" else "fail",
            "registration": {"status": "reused", "email": email},
            "payment": {"status": "skipped", "email": email},
            "cpa_import": status,
        })
    except Exception:
        pass
    return {"id": account.get("id"), "email": email, "status": status}


def _decode_access_token_payload(access_token: str) -> dict:
    parts = (access_token or "").split(".")
    if len(parts) < 2:
        return {}
    payload = parts[1] + "=" * (-len(parts[1]) % 4)
    try:
        decoded = base64.urlsafe_b64decode(payload.encode()).decode()
        data = json.loads(decoded)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _account_id_from_access_token(access_token: str) -> str:
    payload = _decode_access_token_payload(access_token)
    auth = payload.get("https://api.openai.com/auth") if isinstance(payload.get("https://api.openai.com/auth"), dict) else {}
    return (
        auth.get("chatgpt_user_id")
        or auth.get("user_id")
        or payload.get("sub")
        or ""
    )


def _chatgpt_account_id_from_access_token(access_token: str) -> str:
    payload = _decode_access_token_payload(access_token)
    auth = payload.get("https://api.openai.com/auth") if isinstance(payload.get("https://api.openai.com/auth"), dict) else {}
    return str(auth.get("chatgpt_account_id") or "").strip()


def _openai_codex_instructions() -> str:
    try:
        return _OPENAI_CODEX_INSTRUCTIONS_PATH.read_text(encoding="utf-8")
    except Exception:
        return "You are a helpful coding assistant."


def _expired_from_access_token(access_token: str) -> str:
    payload = _decode_access_token_payload(access_token)
    try:
        exp = int(payload.get("exp") or 0)
    except Exception:
        exp = 0
    if not exp:
        return ""
    return datetime.fromtimestamp(exp, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _plan_type_from_token(token: str) -> str:
    payload = _decode_access_token_payload(token)
    auth = payload.get("https://api.openai.com/auth") if isinstance(payload.get("https://api.openai.com/auth"), dict) else {}
    raw = str(auth.get("chatgpt_plan_type") or "").strip().lower()
    if not raw:
        return ""
    if "team" in raw:
        return "team"
    if "pro" in raw and "plus" not in raw:
        return "pro"
    if "plus" in raw:
        return "plus"
    if "free" in raw:
        return "free"
    return raw[:80]


def _auth_file_name(email: str, plan_tag: str) -> str:
    tag = hashlib.md5(email.encode()).hexdigest()[:8]
    return f"codex-{tag}-{email}-{plan_tag}.json"


def _export_oauth_client_id() -> str:
    try:
        cfg = json.loads(s.PAY_CONFIG_PATH.read_text(encoding="utf-8"))
        cpa = cfg.get("cpa") if isinstance(cfg.get("cpa"), dict) else {}
        return str(cpa.get("oauth_client_id") or _DEFAULT_CODEX_CLIENT_ID).strip() or _DEFAULT_CODEX_CLIENT_ID
    except Exception:
        return _DEFAULT_CODEX_CLIENT_ID


def _resolve_repo_path(value: str | Path) -> Path:
    path = Path(value).expanduser()
    if path.is_absolute():
        return path
    return s.ROOT / path


def _heartbeat_proxy_controls() -> tuple[object | None, str, str]:
    """Build proxy controls matching selected session-OTP prepare flow.

    The selected OTP flow gets stage proxies from CTF-pay/config.paypal.json
    trojan_pool and uses the register-stage URL as the effective proxy.
    """
    try:
        cfg = json.loads(s.PAY_CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception as e:
        return None, "", f"read_proxy_config_failed: {type(e).__name__}: {str(e)[:120]}"

    trojan_cfg = cfg.get("trojan_pool") if isinstance(cfg.get("trojan_pool"), dict) else {}
    if trojan_cfg.get("enabled"):
        pool_file = str(trojan_cfg.get("pool_file") or "").strip()
        if not pool_file:
            return None, "", "trojan_pool_enabled_but_missing_pool_file"
        try:
            repo_root = Path(__file__).resolve().parents[3]
            if str(repo_root) not in sys.path:
                sys.path.insert(0, str(repo_root))
            from proxy_bridge import TrojanBridgeManager  # type: ignore

            manager = TrojanBridgeManager(
                str(_resolve_repo_path(pool_file)),
                http_start_port=int(trojan_cfg.get("http_start_port") or 18081),
                work_dir=s.ROOT / "output" / "proxy_bridge",
                executable=str(trojan_cfg.get("bridge_bin") or "sing-box"),
                auto_start=True,
            )
            allocator = manager.allocator(
                all_region=str(trojan_cfg.get("region_all") or ""),
                register_region=str(trojan_cfg.get("region_register") or ""),
                checkout_region=str(trojan_cfg.get("region_checkout") or ""),
                payment_region=str(trojan_cfg.get("region_payment") or ""),
            )
            manager.ensure_started()
            return allocator, "", ""
        except Exception as e:
            return None, "", f"trojan_pool_init_failed: {type(e).__name__}: {str(e)[:160]}"

    proxy_url = str(cfg.get("proxy") or "").strip()
    return None, proxy_url, ""


def _heartbeat_proxy_for_account(proxy_allocator: object | None, fallback_proxy_url: str) -> tuple[str, dict]:
    if proxy_allocator is None:
        return fallback_proxy_url, {"source": "config.proxy" if fallback_proxy_url else ""}
    plan = proxy_allocator.allocate()  # type: ignore[attr-defined]
    proxy_url = str(
        getattr(plan, "register", "")
        or getattr(plan, "payment", "")
        or getattr(plan, "checkout", "")
        or ""
    ).strip()
    meta = (
        getattr(plan, "register_meta", None)
        or getattr(plan, "payment_meta", None)
        or getattr(plan, "checkout_meta", None)
        or {}
    )
    if not isinstance(meta, dict):
        meta = {}
    return proxy_url, {
        "source": str(getattr(plan, "source", "") or ""),
        "register_region": str(getattr(plan, "register_region", "") or ""),
        "checkout_region": str(getattr(plan, "checkout_region", "") or ""),
        "payment_region": str(getattr(plan, "payment_region", "") or ""),
        "node": str(meta.get("name") or meta.get("label") or meta.get("server") or ""),
    }


def _heartbeat_log(line: str) -> None:
    try:
        runner.append_log(f"[heartbeat] {line}")
    except Exception:
        pass


def _team_accept_log(line: str) -> None:
    try:
        runner.append_log(f"[team-accept] {line}")
    except Exception:
        pass


def _heartbeat_proxy_label(result: dict) -> str:
    info = result.get("proxy_info") if isinstance(result.get("proxy_info"), dict) else {}
    node = str(info.get("node") or "").strip()
    region = str(info.get("register_region") or info.get("payment_region") or info.get("checkout_region") or "").strip()
    source = str(info.get("source") or "").strip()
    proxy = str(result.get("proxy") or "").strip()
    parts = []
    if source:
        parts.append(source)
    if region:
        parts.append(region)
    if node:
        parts.append(node)
    if not parts and proxy:
        try:
            parsed = urllib.parse.urlsplit(proxy)
            host = parsed.hostname or ""
            port = f":{parsed.port}" if parsed.port else ""
            parts.append(f"{parsed.scheme}://{host}{port}" if host else "proxy")
        except Exception:
            parts.append("proxy")
    return "/".join(parts) or "-"


def _write_heartbeat_results(payload: dict) -> str:
    _HEARTBEAT_RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    path = _HEARTBEAT_RESULTS_DIR / f"heartbeat-{ts}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(path)


def _mark_heartbeat_failed_rt_retryable(email: str, reason: str) -> None:
    email = str(email or "").strip().lower()
    if not email:
        return
    # rt_state=retryable requires oauth_status=transient_failed with cooldown elapsed.
    ts = datetime.fromtimestamp(time.time() - 7 * 3600, tz=timezone.utc).isoformat()
    get_db().set_oauth_status(email, "transient_failed", f"heartbeat_failed: {reason[:160]}", ts)


def _mark_heartbeat_success(account_id: int, email: str, attempts: int) -> None:
    try:
        get_db().update_account_check(
            int(account_id),
            "valid",
            f"heartbeat ok: {attempts} attempts",
        )
    except Exception:
        pass


def _mark_heartbeat_failed_check(account_id: int, reason: str) -> None:
    try:
        get_db().update_account_check(
            int(account_id),
            "unknown",
            f"heartbeat failed: {reason[:180]}",
        )
    except Exception:
        pass


def _exchange_refresh_token(refresh_token: str, client_id: str) -> dict:
    data = urllib.parse.urlencode({
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": client_id,
        "scope": "openid email profile offline_access",
    }).encode()
    req = urllib.request.Request(
        "https://auth.openai.com/oauth/token",
        data=data,
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
        },
        method="POST",
    )
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(req, timeout=20) as r:
        tok = json.loads(r.read().decode())
    return tok if isinstance(tok, dict) else {}


def _exchange_refresh_token_via_proxy(refresh_token: str, client_id: str,
                                      timeout_s: float, proxy_url: str = "") -> dict:
    try:
        import curl_cffi.requests as cr
    except Exception:
        return _exchange_refresh_token(refresh_token, client_id)
    session = cr.Session(impersonate="chrome136")
    proxy_url = str(proxy_url or "").strip()
    if proxy_url:
        pu = proxy_url.replace("socks5://", "socks5h://")
        session.proxies = {"http": pu, "https": pu}
    resp = session.post(
        "https://auth.openai.com/oauth/token",
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
        },
        data={
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": client_id,
            "scope": "openid email profile offline_access",
        },
        timeout=timeout_s,
    )
    if not (200 <= int(resp.status_code or 0) < 300):
        raise RuntimeError(f"refresh_failed http={resp.status_code} body={resp.text[:240]}")
    try:
        tok = resp.json()
    except Exception as e:
        raise RuntimeError(f"refresh_decode_failed: {type(e).__name__}: {str(e)[:120]}") from e
    return tok if isinstance(tok, dict) else {}


def _team_token_claims(access_token: str) -> dict:
    payload = _decode_access_token_payload(access_token)
    auth = payload.get("https://api.openai.com/auth") if isinstance(payload.get("https://api.openai.com/auth"), dict) else {}
    verified_ws_ids = auth.get("verified_ws_ids")
    if not isinstance(verified_ws_ids, list):
        verified_ws_ids = []
    return {
        "chatgpt_account_id": str(auth.get("chatgpt_account_id") or "").strip(),
        "chatgpt_account_user_id": str(auth.get("chatgpt_account_user_id") or "").strip(),
        "chatgpt_user_id": str(auth.get("chatgpt_user_id") or auth.get("user_id") or payload.get("sub") or "").strip(),
        "chatgpt_plan_type": str(auth.get("chatgpt_plan_type") or "").strip(),
        "verified_ws_ids": [str(x).strip() for x in verified_ws_ids if str(x).strip()],
    }


def _team_token_matches_account(access_token: str, team_account_id: str) -> tuple[bool, dict, str]:
    expected = str(team_account_id or "").strip()
    claims = _team_token_claims(access_token)
    account_id = claims.get("chatgpt_account_id") or ""
    account_user_id = claims.get("chatgpt_account_user_id") or ""
    verified_ws_ids = claims.get("verified_ws_ids") if isinstance(claims.get("verified_ws_ids"), list) else []
    matched = (
        bool(expected)
        and (
            account_id == expected
            or expected in verified_ws_ids
            or account_user_id.endswith(f"__{expected}")
        )
    )
    plan = claims.get("chatgpt_plan_type") or ""
    detail = (
        f"token_account={account_id or '-'} plan={plan or '-'} "
        f"verified_ws_ids={len(verified_ws_ids)}"
    )
    return matched, claims, detail


def _persist_account_tokens(account_id: int, body: dict) -> None:
    access_token = str(body.get("access_token") or "").strip()
    id_token = str(body.get("id_token") or "").strip()
    refresh_token = str(body.get("refresh_token") or "").strip()
    sets: list[str] = []
    args: list[str] = []
    if access_token:
        sets.append("access_token = ?")
        args.append(access_token)
    if id_token:
        sets.append("id_token = ?")
        args.append(id_token)
    if refresh_token:
        sets.append("refresh_token = ?")
        args.append(refresh_token)
    if not sets:
        return
    args.append(str(account_id))
    with get_db()._conn() as c:
        c.execute(
            f"UPDATE registered_accounts SET {', '.join(sets)} WHERE id = ?",
            args,
        )


def _fresh_access_token_for_account(account: dict, client_id: str) -> tuple[str, bool, str]:
    """Return stored access_token for model heartbeat; do not refresh RT here."""
    access_token = str(account.get("access_token") or "").strip()
    if access_token:
        return access_token, False, "stored_access_token"
    return "", False, "no_stored_access_token"


def _post_openai_heartbeat(
    access_token: str,
    model: str,
    timeout_s: float,
    chatgpt_account_id: str = "",
    proxy_url: str = "",
) -> tuple[bool, str, int]:
    """Probe selected OpenAI OAuth account the same way sub2api tests Codex accounts.

    Evidence from sub2api:
    - account_test_service.go uses https://chatgpt.com/backend-api/codex/responses
      for OAuth accounts, not https://api.openai.com/v1/responses.
    - processOpenAIStream only treats response.completed/response.done as success.
    """
    payload = json.dumps({
        "model": model,
        "input": [{
            "role": "user",
            "content": [{"type": "input_text", "text": "hi"}],
        }],
        "stream": True,
        "store": False,
        "instructions": _openai_codex_instructions(),
    }).encode()
    req = urllib.request.Request(
        _CHATGPT_CODEX_RESPONSES_URL,
        data=payload,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
            "Host": "chatgpt.com",
        },
        method="POST",
    )
    if chatgpt_account_id:
        req.add_header("chatgpt-account-id", chatgpt_account_id)
    proxy_url = str(proxy_url or "").strip()
    proxy_handler = (
        urllib.request.ProxyHandler({"http": proxy_url, "https": proxy_url})
        if proxy_url
        else urllib.request.ProxyHandler({})
    )
    opener = urllib.request.build_opener(proxy_handler)
    try:
        with opener.open(req, timeout=timeout_s) as r:
            code = int(getattr(r, "status", 0) or 0)
            if not (200 <= code < 300):
                body = r.read(4096).decode(errors="replace")
                return False, body[:240] or f"http {code}", code
            while True:
                raw = r.readline()
                if not raw:
                    return False, "Stream ended before response.completed", code
                line = raw.decode(errors="replace").strip()
                if not line.startswith("data:"):
                    continue
                data_s = line.split(":", 1)[1].strip()
                if data_s == "[DONE]":
                    return False, "Stream ended before response.completed", code
                try:
                    data = json.loads(data_s)
                except Exception:
                    continue
                event_type = str(data.get("type") or "")
                if event_type in ("response.completed", "response.done"):
                    return True, "ok", code
                if event_type == "response.failed":
                    error_msg = "OpenAI response failed"
                    response = data.get("response") if isinstance(data.get("response"), dict) else {}
                    error = response.get("error") if isinstance(response.get("error"), dict) else {}
                    if error.get("message"):
                        error_msg = str(error.get("message"))
                    return False, error_msg[:240], code
                if event_type == "error":
                    error = data.get("error") if isinstance(data.get("error"), dict) else {}
                    return False, str(error.get("message") or "Unknown error")[:240], code
    except urllib.error.HTTPError as e:
        try:
            body = e.read(4096).decode(errors="replace")
        except Exception:
            body = str(e)
        return False, body[:240] or str(e), int(getattr(e, "code", 0) or 0)
    except Exception as e:
        return False, f"{type(e).__name__}: {str(e)[:200]}", 0


def _post_team_invite_accept(access_token: str, team_account_id: str, device_id: str,
                             timeout_s: float, proxy_url: str = "") -> tuple[bool, str, int]:
    try:
        import curl_cffi.requests as cr
        session = cr.Session(impersonate="chrome136")
        proxy_url = str(proxy_url or "").strip()
        if proxy_url:
            pu = proxy_url.replace("socks5://", "socks5h://")
            session.proxies = {"http": pu, "https": pu}
        resp = session.post(
            f"https://chatgpt.com/backend-api/accounts/{team_account_id}/invites/accept",
            headers={
                "authorization": f"Bearer {access_token}",
                "content-type": "application/json",
                "accept": "*/*",
                "origin": "https://chatgpt.com",
                "referer": "https://chatgpt.com/",
                "oai-device-id": device_id or "",
            },
            data="",
            timeout=timeout_s,
        )
        return resp.status_code in (200, 201), resp.text[:500], int(resp.status_code or 0)
    except Exception as e:
        return False, f"request_failed: {type(e).__name__}: {str(e)[:180]}", 0


def _record_team_invite_accept_result(account_id: int, email: str, team_account_id: str,
                                      status: str, message: str, refresh_token: str = "") -> None:
    now = datetime.now(timezone.utc).isoformat()
    ok = status == "ok"
    try:
        get_db().update_account_check(
            int(account_id),
            "valid" if ok else "unknown",
            f"team invite accept {status}: {message[:180]}",
            "team" if ok else "",
        )
    except Exception:
        pass
    try:
        get_db().add_card_result({
            "ts": now,
            "status": "succeeded" if ok else "failed",
            "chatgpt_email": email,
            "email": email,
            "session_id": f"team-accept-{int(time.time())}",
            "channel": "manual_team_invite_accept",
            "error": "" if ok else message[:500],
            "refresh_token": refresh_token,
            "team_account_id": team_account_id if ok else "",
            "invite_permission": "accepted" if ok else f"accept_failed:{message[:160]}",
        })
    except Exception:
        pass


def _team_invite_prepare_account(account_id: int, client_id: str) -> tuple[dict | None, dict | None]:
    acc = get_db().get_registered_account(int(account_id))
    if not acc:
        return None, {
            "id": int(account_id),
            "email": "",
            "status": "missing",
            "ok": False,
            "http_status": 0,
            "message": "account not found",
        }
    email = str(acc.get("email") or "").strip().lower()
    rt = str(acc.get("refresh_token") or "").strip()
    if not rt and email:
        rt = get_db().latest_refresh_token_for_email(email)
    access_token = str(acc.get("access_token") or "").strip()
    refreshed = False
    token_msg = "stored_access_token"
    if rt:
        try:
            tok = _exchange_refresh_token(rt, client_id)
            new_access = str(tok.get("access_token") or "").strip()
            if new_access:
                access_token = new_access
                rt = str(tok.get("refresh_token") or "").strip() or rt
                refreshed = True
                token_msg = "refresh_token"
        except Exception as e:
            if not access_token:
                return None, {
                    "id": int(account_id),
                    "email": email,
                    "status": "prepare_failed",
                    "ok": False,
                    "http_status": 0,
                    "message": f"refresh_failed: {type(e).__name__}: {str(e)[:180]}",
                }
            token_msg = f"stored_access_token_after_refresh_failed: {type(e).__name__}"
    if not access_token:
        return None, {
            "id": int(account_id),
            "email": email,
            "status": "prepare_failed",
            "ok": False,
            "http_status": 0,
            "message": "no_access_token_or_refresh_token",
        }
    return {
        "id": int(account_id),
        "email": email,
        "access_token": access_token,
        "refresh_token": rt,
        "device_id": str(acc.get("device_id") or "").strip(),
        "refreshed": refreshed,
        "token_msg": token_msg,
    }, None


def _team_accept_proxy_controls() -> tuple[object | None, str, str]:
    try:
        cfg = json.loads(s.PAY_CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception as e:
        return None, "", f"read_proxy_config_failed: {type(e).__name__}: {str(e)[:120]}"

    trojan_cfg = cfg.get("trojan_pool") if isinstance(cfg.get("trojan_pool"), dict) else {}
    if not trojan_cfg.get("enabled"):
        return None, "", "trojan_pool_not_enabled"
    pool_file = str(trojan_cfg.get("pool_file") or "").strip()
    if not pool_file:
        return None, "", "trojan_pool_enabled_but_missing_pool_file"
    try:
        repo_root = Path(__file__).resolve().parents[3]
        if str(repo_root) not in sys.path:
            sys.path.insert(0, str(repo_root))
        from proxy_bridge import TrojanBridgeManager  # type: ignore

        manager = TrojanBridgeManager(
            str(_resolve_repo_path(pool_file)),
            http_start_port=int(trojan_cfg.get("http_start_port") or 18081),
            work_dir=s.ROOT / "output" / "proxy_bridge",
            executable=str(trojan_cfg.get("bridge_bin") or "sing-box"),
            auto_start=True,
        )
        manager.ensure_started()
        probe_timeout = float(trojan_cfg.get("probe_timeout_s") or 8.0)
        probe_url = str(trojan_cfg.get("probe_url") or "").strip()
        alive = manager.alive_nodes(timeout_s=probe_timeout, probe_url=probe_url)
        if not alive:
            return None, "", "trojan_pool_no_alive_nodes"
        random.shuffle(alive)
        allocator = manager.allocator(
            all_region=str(trojan_cfg.get("region_all") or ""),
            register_region=str(trojan_cfg.get("region_register") or ""),
            checkout_region=str(trojan_cfg.get("region_checkout") or ""),
            payment_region=str(trojan_cfg.get("region_payment") or ""),
            register_nodes=alive,
        )
        return allocator, "", f"trojan_alive_nodes={len(alive)}/{len(manager.nodes)}"
    except Exception as e:
        return None, "", f"trojan_pool_init_or_probe_failed: {type(e).__name__}: {str(e)[:160]}"


def _team_invite_accept_worker(state: dict, *, team_account_id: str, client_id: str, timeout_s: float,
                               barrier: threading.Barrier) -> dict:
    email = str(state.get("email") or "")
    try:
        _team_accept_log(f"ready {email}")
        barrier.wait()
    except threading.BrokenBarrierError:
        return {
            "id": int(state.get("id") or 0),
            "email": email,
            "status": "barrier_broken",
            "ok": False,
            "http_status": 0,
            "message": "sync barrier broken before accept",
        }
    sent_at = datetime.now(timezone.utc).isoformat()
    accept_ok, msg, http_status = _post_team_invite_accept(
        str(state.get("access_token") or ""),
        team_account_id,
        str(state.get("device_id") or ""),
        timeout_s,
        str(state.get("proxy") or ""),
    )
    verify_ok = False
    verify_msg = "accept_not_success"
    verify_claims: dict = {}
    refreshed_body: dict = {}
    if accept_ok:
        rt = str(state.get("refresh_token") or "").strip()
        if rt:
            for verify_attempt in range(1, 4):
                try:
                    refreshed_body = _exchange_refresh_token_via_proxy(
                        rt,
                        client_id,
                        max(5.0, float(timeout_s or 0)),
                        str(state.get("proxy") or ""),
                    )
                    rt = str(refreshed_body.get("refresh_token") or "").strip() or rt
                    new_access = str(refreshed_body.get("access_token") or "").strip()
                    if new_access:
                        verify_ok, verify_claims, verify_msg = _team_token_matches_account(new_access, team_account_id)
                        verify_msg = f"attempt={verify_attempt} {verify_msg}"
                        if verify_ok:
                            _persist_account_tokens(int(state.get("id") or 0), refreshed_body)
                            plan_type = _plan_type_from_token(new_access) or _plan_type_from_token(str(refreshed_body.get("id_token") or ""))
                            get_db().update_account_check(
                                int(state.get("id") or 0),
                                "valid",
                                f"team invite accept verified: {verify_msg}",
                                plan_type=plan_type or "team",
                            )
                            break
                        verify_msg = f"accept_http_success_but_token_not_in_team: {verify_msg}"
                    else:
                        verify_msg = f"attempt={verify_attempt} accept_http_success_but_refresh_returned_no_access_token"
                except Exception as e:
                    verify_msg = (
                        f"attempt={verify_attempt} accept_http_success_but_verify_refresh_failed: "
                        f"{type(e).__name__}: {str(e)[:180]}"
                    )
                if verify_ok:
                    break
                if verify_attempt < 3:
                    time.sleep(2.0)
        else:
            verify_ok, verify_claims, verify_msg = _team_token_matches_account(
                str(state.get("access_token") or ""),
                team_account_id,
            )
            if not verify_ok:
                verify_msg = f"accept_http_success_but_no_refresh_token_to_verify_fresh_state: {verify_msg}"
    final_ok = bool(accept_ok and verify_ok)
    status = "ok" if final_ok else ("accepted_unverified" if accept_ok else "failed")
    final_msg = str(msg or "")
    if accept_ok:
        final_msg = f"{final_msg[:220]} | verify={verify_msg}"
    return {
        "id": int(state.get("id") or 0),
        "email": email,
        "status": status,
        "ok": final_ok,
        "accept_ok": bool(accept_ok),
        "http_status": int(http_status or 0),
        "message": final_msg,
        "team_account_id": team_account_id,
        "refreshed": bool(state.get("refreshed")),
        "token_source": str(state.get("token_msg") or ""),
        "verify_claims": verify_claims,
        "verify_refreshed": bool(refreshed_body.get("access_token")),
        "sent_at": sent_at,
        "proxy": str(state.get("proxy") or ""),
        "proxy_info": state.get("proxy_info") if isinstance(state.get("proxy_info"), dict) else {},
    }


def _team_invite_accept_accounts(ids: list[int], *, team_account_id: str,
                                 max_workers: int, timeout_s: float) -> dict:
    started_at = datetime.now(timezone.utc).isoformat()
    client_id = _export_oauth_client_id()
    id_order = [int(i) for i in ids]
    workers = max(1, min(int(max_workers), len(id_order)))
    results: list[dict] = []
    states: list[dict] = []
    runner.begin_external_log_stream()
    _team_accept_log(
        f"start total={len(id_order)} team_account_id={team_account_id} "
        f"workers={workers} timeout={timeout_s}s"
    )
    try:
        proxy_allocator, fallback_proxy_url, proxy_init_message = _team_accept_proxy_controls()
        if proxy_init_message:
            _team_accept_log(f"proxy {proxy_init_message}")
        if proxy_allocator is None and not fallback_proxy_url:
            _team_accept_log("proxy unavailable; abort before accept")
            return {
                "results": [
                    {
                        "id": aid,
                        "email": "",
                        "status": "prepare_failed",
                        "ok": False,
                        "http_status": 0,
                        "message": proxy_init_message or "proxy unavailable",
                    }
                    for aid in id_order
                ],
                "summary": {
                    "total": len(id_order),
                    "ready": 0,
                    "ok": 0,
                    "failed": 0,
                    "prepare_failed": len(id_order),
                    "team_account_id": team_account_id,
                    "workers": workers,
                    "started_at": started_at,
                    "ended_at": datetime.now(timezone.utc).isoformat(),
                },
                "success_emails": [],
                "failed_emails": [],
            }
        with ThreadPoolExecutor(max_workers=workers) as ex:
            futures = {ex.submit(_team_invite_prepare_account, aid, client_id): aid for aid in id_order}
            prepared = 0
            for fut in futures:
                aid = futures[fut]
                try:
                    state, early = fut.result()
                except Exception as e:
                    state, early = None, {
                        "id": aid,
                        "email": "",
                        "status": "prepare_failed",
                        "ok": False,
                        "http_status": 0,
                        "message": f"prepare worker error: {type(e).__name__}: {str(e)[:180]}",
                    }
                if early is not None:
                    results.append(early)
                    _team_accept_log(
                        f"PREPARE_FAIL id={early.get('id')} email={early.get('email') or '-'} "
                        f"msg={str(early.get('message') or '')[:180]}"
                    )
                    continue
                if state is not None:
                    proxy_url, proxy_info = _heartbeat_proxy_for_account(proxy_allocator, fallback_proxy_url)
                    state["proxy"] = proxy_url
                    state["proxy_info"] = proxy_info
                    states.append(state)
                    prepared += 1
                    _team_accept_log(
                        f"prepared {prepared}/{len(id_order)} {state.get('email')} "
                        f"token={state.get('token_msg')} proxy={_heartbeat_proxy_label(state)}"
                    )

        _team_accept_log(
            f"prepared_done ready={len(states)} prepare_failed={len(results)} "
            f"sync_release_count={len(states)}"
        )
        if states:
            barrier = threading.Barrier(len(states))
            # accept 阶段必须让所有已准备账号同时进入 barrier；如果线程数小于
            # barrier parties，会有未调度任务导致已启动线程永久等待。
            accept_workers = len(states)
            _team_accept_log(f"sync_barrier parties={len(states)} accept_workers={accept_workers}")
            with ThreadPoolExecutor(max_workers=accept_workers) as ex:
                futures = {
                    ex.submit(
                        _team_invite_accept_worker,
                        state,
                        team_account_id=team_account_id,
                        client_id=client_id,
                        timeout_s=timeout_s,
                        barrier=barrier,
                    ): state
                    for state in states
                }
                for fut in futures:
                    state = futures[fut]
                    email = str(state.get("email") or "")
                    try:
                        result = fut.result()
                    except Exception as e:
                        result = {
                            "id": int(state.get("id") or 0),
                            "email": email,
                            "status": "failed",
                            "ok": False,
                            "http_status": 0,
                            "team_account_id": team_account_id,
                            "message": f"accept worker error: {type(e).__name__}: {str(e)[:180]}",
                        }
                    results.append(result)
                    _record_team_invite_accept_result(
                        int(result.get("id") or 0),
                        str(result.get("email") or ""),
                        team_account_id,
                        str(result.get("status") or ("ok" if result.get("ok") else "failed")),
                        str(result.get("message") or ""),
                        str(state.get("refresh_token") or ""),
                    )
                    _team_accept_log(
                        f"{'OK' if result.get('ok') else 'FAIL'} {result.get('email') or '-'} "
                        f"status={result.get('status')} http={result.get('http_status') or '-'} "
                        f"msg={str(result.get('message') or '')[:220]}"
                    )

        results.sort(
            key=lambda r: id_order.index(int(r.get("id") or 0))
            if int(r.get("id") or 0) in id_order else len(id_order)
        )
        failed = [r for r in results if not r.get("ok")]
        succeeded = [r for r in results if r.get("ok")]
        payload = {
            "results": results,
            "summary": {
                "total": len(results),
                "ready": len(states),
                "ok": len(succeeded),
                "failed": sum(1 for r in failed if r.get("status") != "prepare_failed"),
                "prepare_failed": sum(1 for r in results if r.get("status") in ("prepare_failed", "missing")),
                "team_account_id": team_account_id,
                "workers": workers,
                "started_at": started_at,
                "ended_at": datetime.now(timezone.utc).isoformat(),
            },
            "success_emails": [str(r.get("email") or "") for r in succeeded if r.get("email")],
            "failed_emails": [str(r.get("email") or "") for r in failed if r.get("email")],
        }
        _team_accept_log(
            f"done total={payload['summary']['total']} ok={payload['summary']['ok']} "
            f"failed={payload['summary']['failed']} prepare_failed={payload['summary']['prepare_failed']}"
        )
        return payload
    finally:
        runner.end_external_log_stream()


def _heartbeat_account(
    account_id: int,
    *,
    attempts: int,
    model: str,
    timeout_s: float,
    client_id: str,
    proxy_allocator: object | None = None,
    fallback_proxy_url: str = "",
    proxy_init_message: str = "",
    progress_log=None,
) -> dict:
    db = get_db()
    acc = db.get_registered_account(int(account_id))
    if not acc:
        return {
            "id": int(account_id),
            "email": "",
            "status": "missing",
            "ok": False,
            "failed_attempt": 0,
            "message": "account not found",
        }

    email = str(acc.get("email") or "").strip().lower()
    access_token, refreshed, token_msg = _fresh_access_token_for_account(acc, client_id)
    proxy_url, proxy_info = _heartbeat_proxy_for_account(proxy_allocator, fallback_proxy_url)
    proxy_label = _heartbeat_proxy_label({"proxy": proxy_url, "proxy_info": proxy_info})
    if not access_token:
        return {
            "id": int(account_id),
            "email": email,
            "status": "failed",
            "ok": False,
            "attempts": 0,
            "failed_attempt": 0,
            "refreshed": refreshed,
            "proxy": proxy_url,
            "proxy_info": proxy_info,
            "message": token_msg,
        }

    chatgpt_account_id = _chatgpt_account_id_from_access_token(access_token)
    if proxy_init_message and not proxy_url:
        return {
            "id": int(account_id),
            "email": email,
            "status": "failed",
            "ok": False,
            "attempts": 0,
            "failed_attempt": 0,
            "refreshed": refreshed,
            "chatgpt_account_id": chatgpt_account_id,
            "proxy": proxy_url,
            "proxy_info": proxy_info,
            "message": proxy_init_message,
        }
    account_started = time.time()
    if progress_log:
        progress_log(f"RUN {email} start attempts={attempts} proxy={proxy_label}")
    for i in range(1, attempts + 1):
        should_log_attempt = i == 1 or i % 5 == 0 or i == attempts
        if progress_log and should_log_attempt:
            progress_log(f"TRY {email} attempt={i}/{attempts} proxy={proxy_label}")
        ok, msg, http_status = _post_openai_heartbeat(
            access_token,
            model,
            timeout_s,
            chatgpt_account_id,
            proxy_url,
        )
        if not ok:
            if progress_log:
                progress_log(
                    f"FAIL {email} attempt={i}/{attempts} http={http_status or '-'} "
                    f"elapsed={time.time() - account_started:.1f}s msg={str(msg or '')[:160]}"
                )
            return {
                "id": int(account_id),
                "email": email,
                "status": "failed",
                "ok": False,
                "attempts": i,
                "failed_attempt": i,
                "http_status": http_status,
                "refreshed": refreshed,
                "chatgpt_account_id": chatgpt_account_id,
                "proxy": proxy_url,
                "proxy_info": proxy_info,
                "message": msg,
            }
        if progress_log and should_log_attempt:
            progress_log(
                f"PASS {email} attempt={i}/{attempts} http={http_status or '-'} "
                f"elapsed={time.time() - account_started:.1f}s"
            )

    return {
        "id": int(account_id),
        "email": email,
        "status": "ok",
        "ok": True,
        "attempts": attempts,
        "failed_attempt": 0,
        "http_status": 200,
        "refreshed": refreshed,
        "chatgpt_account_id": chatgpt_account_id,
        "proxy": proxy_url,
        "proxy_info": proxy_info,
        "message": token_msg or "ok",
    }


def _heartbeat_prepare_account(
    account_id: int,
    *,
    client_id: str,
    proxy_allocator: object | None = None,
    fallback_proxy_url: str = "",
    proxy_init_message: str = "",
) -> tuple[dict | None, dict | None]:
    db = get_db()
    acc = db.get_registered_account(int(account_id))
    if not acc:
        return None, {
            "id": int(account_id),
            "email": "",
            "status": "missing",
            "ok": False,
            "attempts": 0,
            "failed_attempt": 0,
            "message": "account not found",
        }

    email = str(acc.get("email") or "").strip().lower()
    access_token, refreshed, token_msg = _fresh_access_token_for_account(acc, client_id)
    proxy_url, proxy_info = _heartbeat_proxy_for_account(proxy_allocator, fallback_proxy_url)
    chatgpt_account_id = _chatgpt_account_id_from_access_token(access_token) if access_token else ""
    base = {
        "id": int(account_id),
        "email": email,
        "refreshed": refreshed,
        "chatgpt_account_id": chatgpt_account_id,
        "proxy": proxy_url,
        "proxy_info": proxy_info,
        "token_msg": token_msg,
    }
    if not access_token:
        return None, {
            **base,
            "status": "failed",
            "ok": False,
            "attempts": 0,
            "failed_attempt": 0,
            "message": token_msg,
        }
    if proxy_init_message and not proxy_url:
        return None, {
            **base,
            "status": "failed",
            "ok": False,
            "attempts": 0,
            "failed_attempt": 0,
            "message": proxy_init_message,
        }
    return {
        **base,
        "access_token": access_token,
        "started_at": time.time(),
    }, None


def _heartbeat_one_attempt(account_state: dict, attempt_no: int, *, model: str, timeout_s: float) -> dict:
    ok, msg, http_status = _post_openai_heartbeat(
        str(account_state.get("access_token") or ""),
        model,
        timeout_s,
        str(account_state.get("chatgpt_account_id") or ""),
        str(account_state.get("proxy") or ""),
    )
    return {
        "id": int(account_state.get("id") or 0),
        "email": str(account_state.get("email") or ""),
        "attempt": int(attempt_no),
        "ok": bool(ok),
        "http_status": int(http_status or 0),
        "message": str(msg or ""),
    }


def _heartbeat_accounts(ids: list[int], *, attempts: int, model: str, timeout_s: float, max_workers: int) -> dict:
    started_at = datetime.now(timezone.utc).isoformat()
    client_id = _export_oauth_client_id()
    proxy_allocator, fallback_proxy_url, proxy_init_message = _heartbeat_proxy_controls()
    results: list[dict] = []
    workers = max(1, min(int(max_workers), len(ids)))
    total_requests_estimate = len(ids) * attempts
    total_requests = total_requests_estimate
    progress = {"requests": 0, "finished": 0, "ok": 0, "failed": 0}
    runner.begin_external_log_stream()
    _heartbeat_log(
        f"start total={len(ids)} attempts={attempts} requests_estimate={total_requests_estimate} "
        f"model={model} timeout={timeout_s}s workers={workers} scheduler=request-level"
    )
    try:
        if proxy_init_message:
            _heartbeat_log(f"proxy init warning: {proxy_init_message}")
        account_states: dict[int, dict] = {}
        next_attempt: dict[int, int] = {}
        completed_ids: set[int] = set()
        id_order = [int(i) for i in ids]

        for aid in id_order:
            state, early_result = _heartbeat_prepare_account(
                aid,
                client_id=client_id,
                proxy_allocator=proxy_allocator,
                fallback_proxy_url=fallback_proxy_url,
                proxy_init_message=proxy_init_message,
            )
            if early_result is not None:
                results.append(early_result)
                completed_ids.add(aid)
                progress["finished"] += 1
                progress["failed"] += 1
                _mark_heartbeat_failed_rt_retryable(
                    str(early_result.get("email") or ""),
                    str(early_result.get("message") or "early_failed"),
                )
                _mark_heartbeat_failed_check(
                    int(early_result.get("id") or 0),
                    str(early_result.get("message") or "early_failed"),
                )
                _heartbeat_log(
                    f"FAIL [{progress['finished']}/{len(ids)}] "
                    f"{early_result.get('email') or 'id=' + str(early_result.get('id'))} "
                    f"failed_attempt=0 http=- proxy={_heartbeat_proxy_label(early_result)} "
                    f"msg={str(early_result.get('message') or '')[:180]}"
                )
                continue
            if state is not None:
                account_states[aid] = state
                next_attempt[aid] = 1
                _heartbeat_log(
                    f"RUN {state.get('email')} start attempts={attempts} "
                    f"proxy={_heartbeat_proxy_label(state)}"
                )
        total_requests = len(account_states) * attempts
        _heartbeat_log(
            f"prepared runnable_accounts={len(account_states)} early_failed={len(completed_ids)} "
            f"requests={total_requests}"
        )

        with ThreadPoolExecutor(max_workers=workers) as ex:
            futures = {}
            ready_queue = deque(
                aid for aid in id_order if aid in account_states and aid not in completed_ids
            )

            def submit_attempt(aid: int) -> None:
                attempt_no = next_attempt.get(aid, 1)
                state = account_states[aid]
                _heartbeat_log(
                    f"TRY {state.get('email')} attempt={attempt_no}/{attempts} "
                    f"request={progress['requests'] + len(futures) + 1}/{total_requests} "
                    f"proxy={_heartbeat_proxy_label(state)}"
                )
                fut = ex.submit(
                    _heartbeat_one_attempt,
                    state,
                    attempt_no,
                    model=model,
                    timeout_s=timeout_s,
                )
                futures[fut] = (aid, attempt_no)

            while ready_queue and len(futures) < workers:
                submit_attempt(ready_queue.popleft())

            while futures:
                done, _pending = wait(set(futures.keys()), return_when=FIRST_COMPLETED)
                for fut in done:
                    aid, attempt_no = futures.pop(fut)
                    state = account_states[aid]
                    email = str(state.get("email") or "")
                    try:
                        attempt_result = fut.result()
                    except Exception as e:
                        attempt_result = {
                            "id": aid,
                            "email": email,
                            "attempt": attempt_no,
                            "ok": False,
                            "http_status": 0,
                            "message": f"worker error: {type(e).__name__}: {str(e)[:180]}",
                        }

                    progress["requests"] += 1
                    elapsed = time.time() - float(state.get("started_at") or time.time())
                    if not attempt_result.get("ok"):
                        result = {
                            "id": aid,
                            "email": email,
                            "status": "failed",
                            "ok": False,
                            "attempts": attempt_no,
                            "failed_attempt": attempt_no,
                            "http_status": attempt_result.get("http_status") or 0,
                            "refreshed": bool(state.get("refreshed")),
                            "chatgpt_account_id": str(state.get("chatgpt_account_id") or ""),
                            "proxy": str(state.get("proxy") or ""),
                            "proxy_info": state.get("proxy_info") if isinstance(state.get("proxy_info"), dict) else {},
                            "message": str(attempt_result.get("message") or ""),
                        }
                        results.append(result)
                        completed_ids.add(aid)
                        progress["finished"] += 1
                        progress["failed"] += 1
                        _mark_heartbeat_failed_rt_retryable(email, str(result.get("message") or "attempt_failed"))
                        _mark_heartbeat_failed_check(aid, str(result.get("message") or "attempt_failed"))
                        _heartbeat_log(
                            f"FAIL [{progress['finished']}/{len(ids)}] {email} "
                            f"attempt={attempt_no}/{attempts} http={result['http_status'] or '-'} "
                            f"requests={progress['requests']}/{total_requests} "
                            f"elapsed={elapsed:.1f}s msg={str(result.get('message') or '')[:160]}"
                        )
                    elif attempt_no >= attempts:
                        result = {
                            "id": aid,
                            "email": email,
                            "status": "ok",
                            "ok": True,
                            "attempts": attempts,
                            "failed_attempt": 0,
                            "http_status": attempt_result.get("http_status") or 200,
                            "refreshed": bool(state.get("refreshed")),
                            "chatgpt_account_id": str(state.get("chatgpt_account_id") or ""),
                            "proxy": str(state.get("proxy") or ""),
                            "proxy_info": state.get("proxy_info") if isinstance(state.get("proxy_info"), dict) else {},
                            "message": str(state.get("token_msg") or "ok"),
                        }
                        results.append(result)
                        completed_ids.add(aid)
                        progress["finished"] += 1
                        progress["ok"] += 1
                        _mark_heartbeat_success(aid, email, attempts)
                        _heartbeat_log(
                            f"OK [{progress['finished']}/{len(ids)}] {email} "
                            f"attempts={attempts} requests={progress['requests']}/{total_requests} "
                            f"elapsed={elapsed:.1f}s proxy={_heartbeat_proxy_label(result)}"
                        )
                    else:
                        next_attempt[aid] = attempt_no + 1
                        ready_queue.append(aid)
                        if attempt_no == 1 or attempt_no % 5 == 0:
                            _heartbeat_log(
                                f"PASS {email} attempt={attempt_no}/{attempts} "
                                f"http={attempt_result.get('http_status') or '-'} "
                                f"requests={progress['requests']}/{total_requests} elapsed={elapsed:.1f}s"
                            )

                while ready_queue and len(futures) < workers:
                    submit_attempt(ready_queue.popleft())

                _heartbeat_log(
                    f"progress accounts={progress['finished']}/{len(ids)} "
                    f"requests={progress['requests']}/{total_requests} "
                    f"ok={progress['ok']} failed={progress['failed']} "
                    f"inflight={len(futures)} queued={len(ready_queue)} "
                    f"remaining_accounts={max(0, len(ids) - progress['finished'])}"
                )

        results.sort(key=lambda r: ids.index(int(r.get("id") or 0)) if int(r.get("id") or 0) in ids else len(ids))
        failed = [r for r in results if not r.get("ok")]
        succeeded = [r for r in results if r.get("ok")]
        payload = {
            "results": results,
            "summary": {
                "total": len(results),
                "ok": sum(1 for r in results if r.get("ok")),
                "failed": len(failed),
                "attempts_per_account": attempts,
                "model": model,
            },
            "success_emails": [str(r.get("email") or "") for r in succeeded if r.get("email")],
            "failed_emails": [str(r.get("email") or "") for r in failed if r.get("email")],
        }
        ended_at = datetime.now(timezone.utc).isoformat()
        payload["summary"]["started_at"] = started_at
        payload["summary"]["ended_at"] = ended_at
        try:
            result_path = _write_heartbeat_results(payload)
            payload["summary"]["result_path"] = result_path
            _heartbeat_log(
                f"done total={len(results)} ok={payload['summary']['ok']} failed={len(failed)} result={result_path}"
            )
        except Exception as e:
            _heartbeat_log(f"write result failed: {type(e).__name__}: {str(e)[:160]}")
        return payload
    finally:
        runner.end_external_log_stream()


def _refresh_auth_body(body: dict, client_id: str) -> tuple[dict, bool, str]:
    rt = str(body.get("refresh_token") or "").strip()
    if not rt:
        return body, False, "no_refresh_token"
    try:
        tok = _exchange_refresh_token(rt, client_id)
    except Exception as e:
        return body, False, f"refresh_failed: {type(e).__name__}: {str(e)[:160]}"

    access_token = str(tok.get("access_token") or "").strip()
    if not access_token:
        return body, False, "refresh_failed: missing_access_token"
    refreshed = dict(body)
    refreshed["access_token"] = access_token
    refreshed["id_token"] = str(tok.get("id_token") or "").strip() or access_token
    refreshed["refresh_token"] = str(tok.get("refresh_token") or "").strip() or rt
    refreshed["account_id"] = _account_id_from_access_token(access_token)
    refreshed["expired"] = _expired_from_access_token(access_token)
    refreshed["last_refresh"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return refreshed, True, ""


def _sync_plan_for_account(account: dict, client_id: str) -> dict:
    aid = int(account.get("id") or 0)
    email = str(account.get("email") or "").strip().lower()
    rt = str(account.get("refresh_token") or "").strip()
    if not rt and email:
        rt = get_db().latest_refresh_token_for_email(email)

    access_token = str(account.get("access_token") or "").strip()
    id_token = str(account.get("id_token") or "").strip()
    refreshed = False
    message = ""

    if rt:
        try:
            tok = _exchange_refresh_token(rt, client_id)
            new_access = str(tok.get("access_token") or "").strip()
            if new_access:
                access_token = new_access
                id_token = str(tok.get("id_token") or "").strip() or new_access
                rt = str(tok.get("refresh_token") or "").strip() or rt
                refreshed = True
            else:
                message = "refresh_failed: missing_access_token"
        except Exception as e:
            message = f"refresh_failed: {type(e).__name__}: {str(e)[:160]}"

    plan_type = _plan_type_from_token(access_token) or _plan_type_from_token(id_token)
    if not plan_type:
        return {
            "id": aid,
            "email": email,
            "status": "unknown",
            "message": message or "no_plan_type_in_token",
            "plan_type": "",
            "refreshed": refreshed,
        }

    try:
        sets: list[str] = []
        args: list[str] = []
        if refreshed and access_token:
            sets.append("access_token = ?")
            args.append(access_token)
        if refreshed and id_token:
            sets.append("id_token = ?")
            args.append(id_token)
        if refreshed and rt:
            sets.append("refresh_token = ?")
            args.append(rt)
        if sets:
            args.append(str(aid))
            with get_db()._conn() as c:
                c.execute(
                    f"UPDATE registered_accounts SET {', '.join(sets)} WHERE id = ?",
                    args,
                )
        get_db().update_account_check(
            aid,
            "valid",
            "plan sync via refresh_token" if refreshed else "plan sync via stored token",
            plan_type=plan_type,
        )
    except Exception as e:
        return {
            "id": aid,
            "email": email,
            "status": "error",
            "message": f"db_update_failed: {type(e).__name__}: {str(e)[:160]}",
            "plan_type": plan_type,
            "refreshed": refreshed,
        }

    return {
        "id": aid,
        "email": email,
        "status": "ok",
        "message": "refreshed" if refreshed else "stored_token",
        "plan_type": plan_type,
        "refreshed": refreshed,
    }


def _persist_refreshed_auth_body(account_id: int, body: dict, message: str) -> None:
    access_token = str(body.get("access_token") or "").strip()
    id_token = str(body.get("id_token") or "").strip()
    refresh_token = str(body.get("refresh_token") or "").strip()
    sets: list[str] = []
    args: list[str] = []
    if access_token:
        sets.append("access_token = ?")
        args.append(access_token)
    if id_token:
        sets.append("id_token = ?")
        args.append(id_token)
    if refresh_token:
        sets.append("refresh_token = ?")
        args.append(refresh_token)
    if sets:
        args.append(str(account_id))
        with get_db()._conn() as c:
            c.execute(
                f"UPDATE registered_accounts SET {', '.join(sets)} WHERE id = ?",
                args,
            )
    plan_type = _plan_type_from_token(access_token) or _plan_type_from_token(id_token)
    get_db().update_account_check(account_id, "valid", message, plan_type=plan_type)


def _latest_inventory_plan_by_id() -> dict[int, str]:
    inv = build_accounts_inventory()
    out: dict[int, str] = {}
    for item in inv.get("accounts") or []:
        try:
            out[int(item.get("id"))] = str(item.get("plan_tag") or "free").strip() or "free"
        except Exception:
            continue
    return out


def _auth_body_for_account(account: dict, plan_tag: str) -> tuple[str, dict]:
    email = str(account.get("email") or "").strip().lower()
    access_token = str(account.get("access_token") or "").strip()
    id_token = str(account.get("id_token") or "").strip() or access_token
    refresh_token = str(account.get("refresh_token") or "").strip()
    if not refresh_token:
        refresh_token = get_db().latest_refresh_token_for_email(email)
    account_id = _account_id_from_access_token(access_token)
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    body = {
        "id_token": id_token,
        "access_token": access_token,
        "refresh_token": refresh_token,
        "account_id": account_id,
        "email": email,
        "last_refresh": now_iso,
        "expired": _expired_from_access_token(access_token),
        "type": "codex",
        "plan_tag": plan_tag,
    }
    return _auth_file_name(email, plan_tag), body


def _cpa_json_from_body(body: dict, plan_tag: str) -> dict:
    return {
        "type": "codex",
        "email": body.get("email") or "",
        "token_source": f"ChatGPT_{plan_tag}",
        "refresh_token": body.get("refresh_token") or "",
        "access_token": body.get("access_token") or "",
        "id_token": body.get("id_token") or "",
        "saved_at": datetime.now(timezone.utc).isoformat(),
    }


def _sub2api_account_from_body(name: str, body: dict) -> dict:
    credentials = dict(body)
    account_id = str(credentials.get("account_id") or "")
    credentials.setdefault("chatgpt_account_id", account_id)
    credentials.setdefault("chatgpt_user_id", account_id)
    credentials.setdefault("client_id", "app_EMoamEEZ73f0CkXaXp7hrann")
    credentials.setdefault("expires_at", credentials.get("expired") or "")
    credentials.setdefault("plan_type", credentials.get("plan_tag") or "")
    return {
        "name": name,
        "platform": "openai",
        "type": "oauth",
        "credentials": credentials,
    }


def _build_auth_export(ids: list[int], fmt: str) -> dict:
    if not ids:
        raise HTTPException(status_code=400, detail="ids 不能为空")
    if len(ids) > 500:
        raise HTTPException(status_code=400, detail="单次最多 500 个")

    db = get_db()
    client_id = _export_oauth_client_id()
    plan_by_id = _latest_inventory_plan_by_id()
    skipped: list[dict] = []
    warnings: list[dict] = []
    cpa_items: list[dict] = []
    cpa_files: list[dict] = []
    sub2api_accounts: list[dict] = []
    refreshed_count = 0
    for raw_id in ids:
        aid = int(raw_id)
        acc = db.get_registered_account(aid)
        if not acc:
            skipped.append({"id": aid, "email": "", "reason": "missing"})
            continue
        email = str(acc.get("email") or "").strip().lower()
        plan_tag = plan_by_id.get(aid) or str(acc.get("last_plan_type") or "free").strip() or "free"
        name, body = _auth_body_for_account(acc, plan_tag)
        if not (body.get("access_token") or body.get("refresh_token") or body.get("id_token")):
            skipped.append({"id": aid, "email": email, "reason": "no_token"})
            continue
        body, refreshed, refresh_warning = _refresh_auth_body(body, client_id)
        if refreshed:
            refreshed_count += 1
            try:
                _persist_refreshed_auth_body(aid, body, "auth export refresh token sync ok")
            except Exception:
                pass
            name = _auth_file_name(email, plan_tag)
        elif refresh_warning:
            warnings.append({"id": aid, "email": email, "reason": refresh_warning})
        cpa_json = _cpa_json_from_body(body, plan_tag)
        cpa_items.append(cpa_json)
        cpa_files.append({"filename": name, "payload": cpa_json})
        sub2api_accounts.append(_sub2api_account_from_body(name, body))

    ts = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    if fmt == "sub2api":
        payload = {
            "exported_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "proxies": [],
            "accounts": sub2api_accounts,
        }
        filename = f"sub2api-accounts-{ts}.json"
    else:
        if len(cpa_files) > 1:
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
                for item in cpa_files:
                    zf.writestr(
                        str(item["filename"]),
                        json.dumps(item["payload"], ensure_ascii=False, indent=2) + "\n",
                    )
            payload = None
            filename = f"cpa-auth-files-{ts}.zip"
            archive_base64 = base64.b64encode(buf.getvalue()).decode()
            archive_mime = "application/zip"
        else:
            payload = cpa_items[0] if cpa_items else []
            filename = cpa_files[0]["filename"] if cpa_files else f"cpa-auth-files-{ts}.json"
            archive_base64 = ""
            archive_mime = ""
    return {
        "format": fmt,
        "filename": filename,
        "count": len(cpa_items),
        "refreshed": refreshed_count,
        "skipped": skipped,
        "warnings": warnings,
        "payload": payload,
        "archive_base64": archive_base64 if fmt == "cpa" else "",
        "archive_mime": archive_mime if fmt == "cpa" else "",
    }


def _build_file_csv_export(ids: list[int]) -> tuple[str, str, dict]:
    if not ids:
        raise HTTPException(status_code=400, detail="ids 不能为空")
    if len(ids) > 500:
        raise HTTPException(status_code=400, detail="单次最多 500 个")

    db = get_db()
    plan_by_id = _latest_inventory_plan_by_id()
    rows: list[str] = []
    skipped: list[dict] = []
    for raw_id in ids:
        aid = int(raw_id)
        acc = db.get_registered_account(aid)
        if not acc:
            skipped.append({"id": aid, "email": "", "reason": "missing"})
            continue
        email = str(acc.get("email") or "").strip().lower()
        plan_tag = plan_by_id.get(aid) or str(acc.get("last_plan_type") or "free").strip() or "free"
        name, body = _auth_body_for_account(acc, plan_tag)
        if not (body.get("access_token") or body.get("refresh_token") or body.get("id_token")):
            skipped.append({"id": aid, "email": email, "reason": "no_token"})
            continue

        cpa_json = _cpa_json_from_body(body, plan_tag)
        sub2api_json = {
            "exported_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "proxies": [],
            "accounts": [_sub2api_account_from_body(name, body)],
        }
        file_json = {
            "type": "file",
            "sub2api": json.dumps(sub2api_json, ensure_ascii=False, separators=(",", ":")),
            "cpa": json.dumps(cpa_json, ensure_ascii=False, separators=(",", ":")),
        }
        rows.append(
            "\t".join([
                json.dumps(file_json, ensure_ascii=False, separators=(",", ":")),
                "",
                email,
                "",
            ])
        )

    ts = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    text = "\n".join(rows) + ("\n" if rows else "")
    filename = f"file-sub2api-cpa-{ts}.csv"
    meta = {
        "count": len(rows),
        "skipped": skipped,
    }
    return filename, text, meta


@router.get("/accounts")
def get_accounts(user: str = CurrentUser):
    return build_accounts_inventory()


@router.post("/accounts/export-auth")
def export_auth(req: AuthExportRequest, user: str = CurrentUser):
    """Build local auth JSON for selected accounts.

    `format=cpa` matches the CPA auth body shape used by local imports:
    {type,email,token_source,refresh_token,access_token,id_token,saved_at}.
    `format=sub2api` matches the repository's Sub2API account-export shape:
    {exported_at, proxies, accounts:[{name, platform, type, credentials}]}.
    """
    return _build_auth_export(req.ids, req.format)


@router.post("/accounts/export-file-csv")
def export_file_csv(req: IdsRequest, user: str = CurrentUser):
    """Export selected accounts as tab-separated CSV text.

    Columns:
    1. {"type":"file","sub2api":"<sub2api json string>","cpa":"<cpa json string>"}
    2. remark (empty)
    3. email
    4. phone (empty)

    This export intentionally uses stored local tokens only and does not refresh
    access_token/refresh_token.
    """
    filename, text, meta = _build_file_csv_export(req.ids)
    return Response(
        content=text,
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-Export-Count": str(meta["count"]),
            "X-Export-Skipped": str(len(meta["skipped"])),
        },
    )


@router.post("/accounts/check")
def check_accounts(req: CheckRequest, user: str = CurrentUser):
    """Probe each account's session and live plan via OpenAI APIs.
    Body: {ids: [account_id, ...], timeout_s?, max_workers?}.
    Returns per-account {id, email, status, message, plan_type}.
    """
    if not req.ids:
        raise HTTPException(status_code=400, detail="ids 不能为空")
    if len(req.ids) > 500:
        raise HTTPException(status_code=400, detail="单次最多 500 个")
    workers = max(1, min(int(req.max_workers), 8))
    timeout = max(2.0, min(float(req.timeout_s), 30.0))
    results = validate_accounts(req.ids, max_workers=workers, timeout_s=timeout)
    summary = {
        "total": len(results),
        "valid": sum(1 for r in results if r.get("status") == "valid"),
        "invalid": sum(1 for r in results if r.get("status") == "invalid"),
        "unknown": sum(1 for r in results if r.get("status") == "unknown"),
        "free": sum(1 for r in results if r.get("plan_type") == "free"),
        "plus": sum(1 for r in results if r.get("plan_type") == "plus"),
        "team": sum(1 for r in results if r.get("plan_type") == "team"),
        "pro": sum(1 for r in results if r.get("plan_type") == "pro"),
    }
    return {"results": results, "summary": summary}


@router.post("/accounts/heartbeat")
def heartbeat_accounts(req: HeartbeatRequest, user: str = CurrentUser):
    """For selected accounts, call ChatGPT Codex Responses with input "hi" repeatedly.

    Any failed request marks that email as failed and is returned in failed_emails.
    """
    if not req.ids:
        raise HTTPException(status_code=400, detail="ids 不能为空")
    attempts = max(1, min(int(req.attempts or 40), 200))
    timeout = max(2.0, min(float(req.timeout_s or 30.0), 120.0))
    workers = max(1, min(int(req.max_workers or 3), 50))
    model = str(req.model or "").strip() or _OPENAI_DEFAULT_TEST_MODEL
    return _heartbeat_accounts(
        [int(i) for i in req.ids],
        attempts=attempts,
        model=model,
        timeout_s=timeout,
        max_workers=workers,
    )


@router.post("/accounts/team-invite-accept")
def team_invite_accept(req: TeamInviteAcceptRequest, user: str = CurrentUser):
    if not req.ids:
        raise HTTPException(status_code=400, detail="ids 不能为空")
    team_account_id = str(req.team_account_id or "").strip()
    if not team_account_id:
        raise HTTPException(status_code=400, detail="team_account_id 不能为空")
    workers = max(1, min(int(req.max_workers or 20), 100))
    timeout = max(5.0, min(float(req.timeout_s or 30.0), 120.0))
    return _team_invite_accept_accounts(
        [int(i) for i in req.ids],
        team_account_id=team_account_id,
        max_workers=workers,
        timeout_s=timeout,
    )


@router.post("/accounts/sync-plan")
def sync_plan(req: IdsRequest, user: str = CurrentUser):
    """Refresh selected accounts' OAuth tokens and persist JWT plan_type."""
    if not req.ids:
        raise HTTPException(status_code=400, detail="ids 不能为空")
    if len(req.ids) > 100:
        raise HTTPException(status_code=400, detail="单次最多 100 个")
    db = get_db()
    client_id = _export_oauth_client_id()
    results: list[dict] = []
    for aid in req.ids:
        acc = db.get_registered_account(int(aid))
        if not acc:
            results.append({"id": aid, "email": "", "status": "missing", "message": "account not found", "plan_type": ""})
            continue
        results.append(_sync_plan_for_account(acc, client_id))
    summary = {
        "total": len(results),
        "ok": sum(1 for r in results if r.get("status") == "ok"),
        "unknown": sum(1 for r in results if r.get("status") == "unknown"),
        "error": sum(1 for r in results if r.get("status") == "error"),
        "refreshed": sum(1 for r in results if r.get("refreshed")),
    }
    return {"results": results, "summary": summary}


@router.post("/accounts/delete")
def delete_accounts(req: IdsRequest, user: str = CurrentUser):
    """Hard-delete accounts by id. Associated pipeline_results / card_results /
    oauth_status rows are kept (audit trail; lookup by email still works)."""
    if not req.ids:
        raise HTTPException(status_code=400, detail="ids 不能为空")
    n = get_db().delete_registered_accounts(req.ids)
    return {"deleted": n, "requested": len(req.ids)}


@router.post("/accounts/sale/claim")
def claim_sale_account(req: SaleClaimRequest, user: str = CurrentUser):
    """Return one available Plus email/mail-password/GPT-password bundle and mark sold."""
    acc = get_db().claim_account_for_sale(req.note)
    if not acc:
        raise HTTPException(status_code=404, detail="没有可售且带密码的 Plus 账号")
    return acc


@router.post("/accounts/sale/toggle")
def toggle_sale_account(req: SaleToggleRequest, user: str = CurrentUser):
    """Toggle one account between available and sold."""
    acc = get_db().toggle_account_sale_status(req.id, req.note)
    if not acc:
        raise HTTPException(status_code=404, detail="账号不存在")
    return acc


@router.post("/accounts/cpa-push")
def cpa_push(req: IdsRequest, user: str = CurrentUser):
    """Push selected accounts to CPA (CLIProxyAPI). Reuses
    pipeline._cpa_import_after_team. Each row's stored refresh_token (or
    fallback access_token) is used; records outcome to pipeline_results."""
    if not req.ids:
        raise HTTPException(status_code=400, detail="ids 不能为空")
    if len(req.ids) > 100:
        raise HTTPException(status_code=400, detail="单次最多 100 个")
    cpa_cfg = _load_cpa_cfg()
    db = get_db()
    results: list[dict] = []
    for aid in req.ids:
        acc = db.get_registered_account(int(aid))
        if not acc:
            results.append({"id": aid, "email": "", "status": "missing"})
            continue
        results.append(_do_cpa_push(acc, cpa_cfg))
    summary = {
        "total": len(results),
        "ok": sum(1 for r in results if r.get("status") == "ok"),
        "no_rt": sum(1 for r in results if r.get("status") == "no_rt"),
        "fail": sum(1 for r in results if r.get("status") not in ("ok", "no_rt", "skipped", "missing")),
    }
    return {"results": results, "summary": summary}
