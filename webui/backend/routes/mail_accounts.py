from __future__ import annotations

import logging
import sys
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from .. import settings as s
from ..auth import CurrentUser


_CTF_REG_DIR = s.CTF_REG_DIR
if str(_CTF_REG_DIR) not in sys.path:
    sys.path.insert(0, str(_CTF_REG_DIR))

from email_account_pool import EmailAccountPool, parse_accounts_text, account_from_row  # noqa: E402
from imap_otp_provider import ImapOtpProvider  # noqa: E402


router = APIRouter(prefix="/api/mail/accounts", tags=["mail_accounts"])
logger = logging.getLogger(__name__)


def _default_path() -> Path:
    return s.get_data_dir() / "email_accounts.csv"


def _resolve_path(path: str = "") -> Path:
    raw = (path or "").strip()
    p = Path(raw).expanduser() if raw else _default_path()
    if not p.is_absolute():
        p = (s.ROOT / p).resolve()
    return p


def _mask_email(email: str = "") -> str:
    email = (email or "").strip()
    if "@" not in email:
        return "***" if email else ""
    local, domain = email.split("@", 1)
    if len(local) <= 2:
        local = local[:1] + "***"
    else:
        local = local[:2] + "***" + local[-1:]
    return f"{local}@{domain}"


def _safe_account(account) -> dict:
    return {
        "email": _mask_email(getattr(account, "email", "")),
        "provider": getattr(account, "provider", ""),
        "imap_host": getattr(account, "imap_host", ""),
        "imap_port": getattr(account, "imap_port", ""),
        "imap_ssl": getattr(account, "imap_ssl", ""),
        "status": getattr(account, "status", ""),
        "has_mail_password": bool(getattr(account, "mail_password", "")),
        "has_access_token": bool(getattr(account, "access_token", "")),
        "has_refresh_token": bool(getattr(account, "refresh_token", "")),
    }


def _safe_error(error: Exception, account=None) -> str:
    text = str(error)
    email = getattr(account, "email", "") if account is not None else ""
    if email:
        text = text.replace(email, _mask_email(email))
    return text


def _accounts_text_diagnostics(text: str) -> dict:
    raw_lines = [ln for ln in (text or "").splitlines() if ln.strip()]
    previews: list[str] = []
    for line in raw_lines[:8]:
        raw = line.strip()
        masked = raw
        if "----" in raw:
            email_part, rest = raw.split("----", 1)
            masked = f"{_mask_email(email_part.strip())}----***({len(rest.strip())})"
        elif "," in raw:
            email_part, rest = raw.split(",", 1)
            masked = f"{_mask_email(email_part.strip())},***(len={len(rest.strip())})"
        elif "\t" in raw:
            email_part, rest = raw.split("\t", 1)
            masked = f"{_mask_email(email_part.strip())}\t***(len={len(rest.strip())})"
        elif "@" in raw:
            email_part = raw.split(None, 1)[0].strip()
            masked = raw.replace(email_part, _mask_email(email_part), 1)
        if len(masked) > 80:
            masked = masked[:77] + "..."
        previews.append(masked)
    return {
        "text_len": len(text or ""),
        "nonempty_lines": len(raw_lines),
        "line_previews": previews,
    }


class SaveRequest(BaseModel):
    accounts_text: str = ""
    path: str = ""


class ListRequest(BaseModel):
    path: str = ""
    accounts_text: str = ""
    email: str = ""
    limit: int = Field(default=10, ge=1, le=30)


@router.get("/status")
def status(path: str = "", user: str = CurrentUser):
    pool = EmailAccountPool(_resolve_path(path))
    rows = [a.sanitized() for a in pool.load_accounts()]
    logger.warning(
        "mail.accounts.status in path=%s -> count=%s",
        pool.path,
        len(rows),
    )
    return {"path": str(pool.path), "count": len(rows), "accounts": rows}


@router.post("/save")
def save(req: SaveRequest, user: str = CurrentUser):
    pool = EmailAccountPool(_resolve_path(req.path))
    logger.warning(
        "mail.accounts.save in path=%s body=%s",
        pool.path,
        {"path": req.path, **_accounts_text_diagnostics(req.accounts_text)},
    )
    if not req.accounts_text.strip():
        logger.warning("mail.accounts.save empty_text path=%s", pool.path)
        raise HTTPException(
            status_code=400,
            detail="邮箱列表为空；请先填写 email----password，一行一个",
        )
    rows = parse_accounts_text(req.accounts_text)
    if not rows:
        logger.warning("mail.accounts.save parse_failed path=%s", pool.path)
        raise HTTPException(
            status_code=400,
            detail="没有解析到邮箱账号；支持 email----password，也兼容 email_password，一行一个",
        )
    pool.write_rows(rows)
    accounts = [account_from_row(r) for r in rows]
    resp = {
        "path": str(pool.path),
        "count": len(accounts),
        "accounts": [a.sanitized() for a in accounts],
    }
    logger.warning(
        "mail.accounts.save out path=%s count=%s accounts=%s",
        pool.path,
        len(accounts),
        [_safe_account(a) for a in accounts[:5]],
    )
    return resp


@router.post("/list")
def list_messages(req: ListRequest, user: str = CurrentUser):
    resolved_path = _resolve_path(req.path)
    logger.warning(
        "mail.accounts.list in path=%s body=%s",
        resolved_path,
        {
            "path": req.path,
            "email": _mask_email(req.email),
            "limit": req.limit,
            **_accounts_text_diagnostics(req.accounts_text),
        },
    )
    try:
        if req.accounts_text.strip():
            rows = parse_accounts_text(req.accounts_text)
            if not rows:
                logger.warning(
                    "mail.accounts.list parse_failed path=%s text_len=%s",
                    resolved_path,
                    len(req.accounts_text or ""),
                )
                raise HTTPException(
                    status_code=400,
                    detail="没有解析到邮箱账号；支持 email----password，也兼容 email_password，一行一个",
                )
            accounts = [account_from_row(r) for r in rows]
        else:
            pool = EmailAccountPool(resolved_path)
            accounts = pool.load_accounts()
        logger.warning(
            "mail.accounts.list parsed source=%s count=%s accounts=%s",
            "text" if req.accounts_text.strip() else "file",
            len(accounts),
            [_safe_account(a) for a in accounts[:5]],
        )
        if not accounts:
            logger.warning("mail.accounts.list empty path=%s", resolved_path)
            raise HTTPException(
                status_code=400,
                detail=f"邮箱列表为空；请先保存邮箱列表，当前路径: {resolved_path}",
            )
        target = (req.email or "").strip().lower()
        if target:
            selected = [a for a in accounts if a.email == target]
            if not selected:
                raise HTTPException(
                    status_code=400,
                    detail=f"邮箱列表里找不到指定账号: {_mask_email(target)}",
                )
        else:
            selected = list(accounts)

        failures: list[str] = []
        for account in selected:
            logger.warning("mail.accounts.list selected account=%s", _safe_account(account))
            try:
                provider = ImapOtpProvider(account)
                messages = provider.list_messages(limit=req.limit)
                resp = {
                    "email": account.email,
                    "provider": account.provider,
                    "count": len(messages),
                    "messages": messages,
                }
                logger.warning(
                    "mail.accounts.list out email=%s provider=%s count=%s",
                    _mask_email(account.email),
                    account.provider,
                    len(messages),
                )
                return resp
            except Exception as e:
                detail = _safe_error(e, account)
                failures.append(f"{_mask_email(account.email)}: {detail}")
                logger.warning(
                    "mail.accounts.list account_failed account=%s error=%s",
                    _safe_account(account),
                    detail,
                )

        raise HTTPException(
            status_code=502,
            detail="所有邮箱登录/拉信都失败: " + " || ".join(failures[:8]),
        )
    except HTTPException as e:
        logger.warning(
            "mail.accounts.list http_error status=%s detail=%s path=%s",
            e.status_code,
            e.detail,
            resolved_path,
        )
        raise
    except Exception as e:
        account = locals().get("account")
        detail = _safe_error(e, account)
        if account is not None:
            logger.warning(
                "mail.accounts.list failed account=%s error=%s",
                _safe_account(account),
                detail,
            )
        else:
            logger.warning(
                "mail.accounts.list failed before account selection path=%s error=%s",
                resolved_path,
                detail,
            )
        raise HTTPException(status_code=400, detail=detail)
