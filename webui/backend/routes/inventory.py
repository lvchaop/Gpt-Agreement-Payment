"""Local account inventory: list, validate, delete, push to CPA."""
from __future__ import annotations

import json
import base64
import hashlib
import io
import time
import urllib.parse
import urllib.request
import zipfile
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..auth import CurrentUser
from ..account_inventory import build_accounts_inventory
from ..account_validator import validate_accounts
from ..db import get_db
from .. import settings as s


router = APIRouter(prefix="/api/inventory", tags=["inventory"])

_DEFAULT_CODEX_CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"


class IdsRequest(BaseModel):
    ids: list[int] = Field(default_factory=list)


class CheckRequest(IdsRequest):
    timeout_s: float = 10.0
    max_workers: int = 3


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


def _expired_from_access_token(access_token: str) -> str:
    payload = _decode_access_token_payload(access_token)
    try:
        exp = int(payload.get("exp") or 0)
    except Exception:
        exp = 0
    if not exp:
        return ""
    return datetime.fromtimestamp(exp, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


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
