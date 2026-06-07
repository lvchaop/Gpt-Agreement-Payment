#!/usr/bin/env python3
"""Authorize existing Outlook mailboxes with a real Camoufox browser.

This is standalone and intentionally not wired into pipeline.py.
It uses a fresh dynamic profile per account, drives the Microsoft OAuth flow in
Camoufox, exchanges the authorization code, and can write tokens to
output/webui.db:mail_accounts.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import re
import shutil
import sqlite3
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

from config import Config
from browser_register import _camoufox_headless, _parse_proxy
from outlook_browser_register import _camoufox_geoip_enabled, _camoufox_locale_for_cfg, _camoufox_os_for_cfg
from outlook_oauth import authorize_outlook_mailbox_browser


logger = logging.getLogger(__name__)


def _project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _parse_account(value: str) -> tuple[str, str]:
    raw = (value or "").strip()
    for sep in ("----", "-----", ":", ","):
        if sep in raw:
            email, password = raw.split(sep, 1)
            return email.strip(), password.strip()
    raise ValueError("account must be email----password")


def _load_accounts(args: argparse.Namespace, db_path: Path) -> list[tuple[str, str]]:
    accounts: list[tuple[str, str]] = []
    if args.account:
        accounts.append(_parse_account(args.account))
    if args.email:
        if not args.password:
            raise ValueError("--email requires --password")
        accounts.append((args.email.strip(), args.password))
    if args.accounts_file:
        for line in Path(args.accounts_file).expanduser().read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            accounts.append(_parse_account(line))
    if args.from_db:
        sql = """
            SELECT email, mail_password
            FROM mail_accounts
            WHERE COALESCE(refresh_token, '') = ''
              AND COALESCE(mail_password, '') != ''
            ORDER BY id DESC
        """
        if args.limit > 0:
            sql += f" LIMIT {int(args.limit)}"
        with sqlite3.connect(str(db_path)) as conn:
            accounts.extend((str(e), str(p)) for e, p in conn.execute(sql).fetchall())
    dedup: list[tuple[str, str]] = []
    seen: set[str] = set()
    for email, password in accounts:
        key = email.lower()
        if key and key not in seen:
            dedup.append((email, password))
            seen.add(key)
    if not dedup:
        raise ValueError("no accounts provided")
    return dedup


def _ensure_mail_tables(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS mail_accounts (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          email TEXT NOT NULL UNIQUE,
          mail_password TEXT DEFAULT '',
          provider TEXT DEFAULT '',
          imap_host TEXT DEFAULT '',
          imap_port INTEGER DEFAULT 993,
          imap_ssl INTEGER DEFAULT 1,
          account_id TEXT DEFAULT '',
          access_token TEXT DEFAULT '',
          refresh_token TEXT DEFAULT '',
          openai_password TEXT DEFAULT '',
          first TEXT DEFAULT '',
          last TEXT DEFAULT '',
          status TEXT DEFAULT 'unused',
          fail_reason TEXT DEFAULT '',
          created_at REAL NOT NULL,
          updated_at REAL NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS oauth_status (
          email TEXT PRIMARY KEY,
          status TEXT NOT NULL,
          ts TEXT NOT NULL,
          fail_reason TEXT DEFAULT ''
        )
        """
    )


def _write_success(db_path: Path, *, email: str, password: str, result: Any) -> None:
    now = time.time()
    ts = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    with sqlite3.connect(str(db_path)) as conn:
        _ensure_mail_tables(conn)
        conn.execute(
            """
            INSERT INTO mail_accounts(
              email, mail_password, provider, imap_host, imap_port, imap_ssl,
              account_id, access_token, refresh_token, status, fail_reason, created_at, updated_at
            ) VALUES (?, ?, 'outlook', 'outlook.office365.com', 993, 1, ?, ?, ?, 'unused', '', ?, ?)
            ON CONFLICT(email) DO UPDATE SET
              mail_password=CASE
                WHEN COALESCE(mail_accounts.mail_password, '') = '' THEN excluded.mail_password
                ELSE mail_accounts.mail_password
              END,
              provider='outlook',
              imap_host='outlook.office365.com',
              imap_port=993,
              imap_ssl=1,
              account_id=excluded.account_id,
              access_token=excluded.access_token,
              refresh_token=excluded.refresh_token,
              status='unused',
              fail_reason='',
              updated_at=excluded.updated_at
            """,
            (email.lower(), password, result.client_id, result.access_token, result.refresh_token, now, now),
        )
        conn.execute(
            """
            INSERT INTO oauth_status(email, status, ts, fail_reason)
            VALUES (?, 'succeeded', ?, '')
            ON CONFLICT(email) DO UPDATE SET status=excluded.status, ts=excluded.ts, fail_reason=''
            """,
            (email.lower(), ts),
        )


def _write_failure(db_path: Path, *, email: str, password: str, reason: str) -> None:
    now = time.time()
    ts = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    with sqlite3.connect(str(db_path)) as conn:
        _ensure_mail_tables(conn)
        conn.execute(
            """
            INSERT INTO mail_accounts(
              email, mail_password, provider, imap_host, imap_port, imap_ssl,
              status, fail_reason, created_at, updated_at
            ) VALUES (?, ?, 'outlook', 'outlook.office365.com', 993, 1, 'oauth_failed', ?, ?, ?)
            ON CONFLICT(email) DO UPDATE SET
              mail_password=CASE
                WHEN COALESCE(mail_accounts.mail_password, '') = '' THEN excluded.mail_password
                ELSE mail_accounts.mail_password
              END,
              status='oauth_failed',
              fail_reason=excluded.fail_reason,
              updated_at=excluded.updated_at
            """,
            (email.lower(), password, reason[:500], now, now),
        )
        conn.execute(
            """
            INSERT INTO oauth_status(email, status, ts, fail_reason)
            VALUES (?, 'failed', ?, ?)
            ON CONFLICT(email) DO UPDATE SET status=excluded.status, ts=excluded.ts, fail_reason=excluded.fail_reason
            """,
            (email.lower(), ts, reason[:500]),
        )


def _browser_context(cfg: Config, *, profile: str, proxy_url: str, headless: bool | None) -> Any:
    if headless is not None:
        os.environ["CAMOUFOX_HEADLESS"] = "1" if headless else "0"
    proxy = _parse_proxy(proxy_url) if proxy_url else None
    geoip = _camoufox_geoip_enabled(proxy)
    from camoufox.sync_api import Camoufox

    try:
        from browserforge.fingerprints import Screen
    except ModuleNotFoundError:
        Screen = None
        logger.warning("[outlook-mail-oauth-browser] browserforge missing; Camoufox default screen will be used")

    kwargs: dict[str, Any] = {
        "headless": _camoufox_headless(),
        "humanize": True,
        "persistent_context": True,
        "user_data_dir": profile,
        "os": _camoufox_os_for_cfg(cfg),
        "proxy": proxy,
        "geoip": geoip,
        "locale": _camoufox_locale_for_cfg(cfg),
    }
    if Screen is not None:
        kwargs["screen"] = Screen(max_width=1920, max_height=1080)
    logger.info(
        "[outlook-mail-oauth-browser] Camoufox headless=%s profile=%s proxy=%s geoip=%s os=%s locale=%s",
        kwargs["headless"],
        profile,
        bool(proxy),
        geoip,
        kwargs["os"],
        kwargs["locale"],
    )
    return Camoufox(**kwargs)


def _run_one(cfg: Config, *, email: str, password: str, proxy_url: str, headless: bool | None, keep_profile: bool) -> dict[str, Any]:
    profile = tempfile.mkdtemp(prefix="outlook_mail_oauth_")
    success = False
    try:
        with _browser_context(cfg, profile=profile, proxy_url=proxy_url, headless=headless) as ctx:
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            try:
                page.context.set_default_timeout(max(int(getattr(cfg.portal_protocol, "timeout_s", 30) or 30), 45) * 1000)
            except Exception:
                pass
            result = authorize_outlook_mailbox_browser(cfg, page, email=email, password=password)
            success = True
            return {
                "ok": True,
                "email": email,
                "profile": profile,
                "mail_oauth_client_id": result.client_id,
                "mail_account_id": result.client_id,
                "mail_access_token": result.access_token,
                "mail_refresh_token": result.refresh_token,
                "mail_oauth_scope": result.scope,
                "expires_in": result.expires_in,
                "token_type": result.token_type,
            }
    finally:
        if not keep_profile and (success or not os.getenv("OUTLOOK_KEEP_BROWSER_PROFILE")):
            shutil.rmtree(profile, ignore_errors=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Pure browser Outlook mailbox OAuth authorizer using Camoufox.")
    parser.add_argument("--config", required=True)
    parser.add_argument("--email", default="")
    parser.add_argument("--password", default="")
    parser.add_argument("--account", default="", help="email----password")
    parser.add_argument("--accounts-file", default="")
    parser.add_argument("--from-db", action="store_true")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--proxy", default="")
    parser.add_argument("--no-proxy", action="store_true")
    parser.add_argument("--write-mail-accounts", action="store_true")
    parser.add_argument("--db", default="")
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--headed", action="store_true")
    parser.add_argument("--keep-profile", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    cfg = Config.from_file(str(Path(args.config).expanduser().resolve()))
    setattr(
        cfg.portal_protocol,
        "user_agent",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36",
    )
    if args.no_proxy:
        cfg.proxy = ""
    elif args.proxy:
        cfg.proxy = args.proxy
    proxy_url = "" if args.no_proxy else str(args.proxy or getattr(cfg, "proxy", "") or "")
    db_path = Path(args.db).expanduser().resolve() if args.db else _project_root() / "output" / "webui.db"
    accounts = _load_accounts(args, db_path)

    headless: bool | None = None
    if args.headless:
        headless = True
    if args.headed:
        headless = False

    outputs: list[dict[str, Any]] = []
    ok = True
    for email, password in accounts:
        try:
            item = _run_one(
                cfg,
                email=email,
                password=password,
                proxy_url=proxy_url,
                headless=headless,
                keep_profile=args.keep_profile,
            )
            outputs.append(item)
            if args.write_mail_accounts:
                _write_success(db_path, email=email, password=password, result=type("R", (), {
                    "client_id": item["mail_oauth_client_id"],
                    "access_token": item["mail_access_token"],
                    "refresh_token": item["mail_refresh_token"],
                })())
        except Exception as e:
            ok = False
            reason = str(e)
            outputs.append({"ok": False, "email": email, "error": reason})
            logger.exception("[outlook-mail-oauth-browser] failed email=%s", email)
            if args.write_mail_accounts:
                _write_failure(db_path, email=email, password=password, reason=reason)

    if args.json:
        print(json.dumps(outputs, ensure_ascii=False, indent=2))
    else:
        for item in outputs:
            if item.get("ok"):
                print(f"OK {item['email']} refresh_token_len={len(item.get('mail_refresh_token') or '')}")
            else:
                print(f"FAIL {item.get('email')} {item.get('error')}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
