#!/usr/bin/env python3
"""Probe WebUI mail_accounts with IMAP and mark unusable mailboxes.

Examples:
  .venv/bin/python scripts/check_mail_accounts_imap.py --dry-run --limit 20
  .venv/bin/python scripts/check_mail_accounts_imap.py --workers 8 --status unused
  .venv/bin/python scripts/check_mail_accounts_imap.py --email user@example.com --include-bad
"""

from __future__ import annotations

import argparse
import concurrent.futures
import re
import socket
import sqlite3
import sys
import time
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CTF_REG = ROOT / "CTF-reg"
if str(CTF_REG) not in sys.path:
    sys.path.insert(0, str(CTF_REG))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from email_account_pool import account_from_row  # noqa: E402
from imap_otp_provider import ImapOtpProvider  # noqa: E402
from webui.backend.db import get_db  # noqa: E402


BAD_STATUS_PREFIX = "imap_"
LOCKED_PATTERNS = (
    "account is locked",
    "account locked",
    "temporarily locked",
    "blocked",
    "disabled",
    "suspended",
    "security",
    "unusual activity",
    "suspicious",
    "verify your account",
    "verify account",
    "login to your account via a web browser",
    "web browser",
    "not allowed",
    "too many login failures",
    "auth failed: user is authenticated but not connected",
)
AUTH_PATTERNS = (
    "authenticationfailed",
    "authentication failed",
    "invalid credentials",
    "invalid login",
    "login failed",
    "bad username or password",
    "username and password not accepted",
    "application-specific password required",
    "app password",
    "password",
    "xoauth2",
    "invalid_grant",
    "invalid token",
)
CONFIG_PATTERNS = (
    "缺 imap_host",
    "缺邮箱密码",
    "缺 client_id",
    "missing",
    "no such host",
    "name or service not known",
)
CONN_PATTERNS = (
    "timed out",
    "timeout",
    "connection refused",
    "connection reset",
    "network is unreachable",
    "nodename nor servname",
    "ssl",
    "certificate",
)


@dataclass
class ProbeResult:
    email: str
    old_status: str
    ok: bool
    status: str
    reason: str
    elapsed_s: float
    wrote: bool = False


def _clean_status(value: str) -> str:
    return (value or "").strip().lower()


def _matches(text: str, patterns: tuple[str, ...]) -> bool:
    low = text.lower()
    return any(p.lower() in low for p in patterns)


def classify_error(error: Exception) -> tuple[str, str]:
    text = re.sub(r"\s+", " ", str(error) or "").strip()
    low = text.lower()
    if _matches(low, LOCKED_PATTERNS):
        return "imap_locked", text
    if _matches(low, CONFIG_PATTERNS):
        return "imap_config_error", text
    if _matches(low, CONN_PATTERNS):
        return "imap_conn_error", text
    if _matches(low, AUTH_PATTERNS):
        return "imap_auth_failed", text
    return "imap_failed", text


def probe_account(row: dict) -> ProbeResult:
    account = account_from_row(row)
    started = time.time()
    imap = None
    try:
        provider = ImapOtpProvider(account)
        imap = provider._connect()
        return ProbeResult(
            email=account.email,
            old_status=_clean_status(row.get("status", "")),
            ok=True,
            status="ok",
            reason="imap login ok",
            elapsed_s=time.time() - started,
        )
    except Exception as e:
        status, reason = classify_error(e)
        return ProbeResult(
            email=account.email,
            old_status=_clean_status(row.get("status", "")),
            ok=False,
            status=status,
            reason=reason[:500],
            elapsed_s=time.time() - started,
        )
    finally:
        if imap is not None:
            try:
                imap.logout()
            except Exception:
                pass


def _parse_status_filter(raw: str) -> set[str]:
    return {
        part.strip().lower()
        for part in (raw or "").split(",")
        if part.strip()
    }


def select_rows(rows: list[dict], *, email: str, statuses: set[str],
                include_bad: bool, limit: int) -> list[dict]:
    out: list[dict] = []
    target = (email or "").strip().lower()
    for row in rows:
        row_email = (row.get("email") or "").strip().lower()
        status = _clean_status(row.get("status", ""))
        if target and row_email != target:
            continue
        if statuses and status not in statuses:
            continue
        if not include_bad and status.startswith(BAD_STATUS_PREFIX):
            continue
        out.append(row)
        if limit > 0 and len(out) >= limit:
            break
    return out


def clear_fail_reason(email: str) -> bool:
    db = get_db()
    with sqlite3.connect(db.path) as conn:
        cur = conn.execute(
            """
            UPDATE mail_accounts
            SET fail_reason = '', updated_at = ?
            WHERE lower(email) = lower(?)
            """,
            (time.time(), email),
        )
    return cur.rowcount > 0


def write_result(result: ProbeResult, *, dry_run: bool,
                 clear_fail_reason_on_ok: bool) -> ProbeResult:
    if dry_run:
        return result
    if result.ok:
        if clear_fail_reason_on_ok:
            result.wrote = clear_fail_reason(result.email)
        return result
    result.wrote = get_db().mark_mail_account(
        result.email,
        result.status,
        result.reason,
    )
    return result


def _short_reason(reason: str, limit: int = 180) -> str:
    reason = re.sub(r"\s+", " ", reason or "").strip()
    return reason if len(reason) <= limit else reason[:limit - 3] + "..."


def print_result(result: ProbeResult) -> None:
    flag = "OK" if result.ok else "BAD"
    wrote = " write=yes" if result.wrote else ""
    print(
        f"[{flag}] {result.email} old={result.old_status or '-'} "
        f"status={result.status} elapsed={result.elapsed_s:.1f}s{wrote} "
        f"reason={_short_reason(result.reason)}",
        flush=True,
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Probe all WebUI mail_accounts via IMAP and mark failed mailboxes.",
    )
    parser.add_argument("--workers", type=int, default=5, help="parallel probes, default 5")
    parser.add_argument("--limit", type=int, default=0, help="check only first N selected rows")
    parser.add_argument("--email", default="", help="check one mailbox only")
    parser.add_argument(
        "--status",
        default="",
        help="comma-separated statuses to include, default all non-imap_* rows",
    )
    parser.add_argument(
        "--include-bad",
        action="store_true",
        help="also re-check rows whose status already starts with imap_",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="print results without updating mail_accounts",
    )
    parser.add_argument(
        "--clear-fail-reason-on-ok",
        action="store_true",
        help="on successful login, clear fail_reason while preserving status",
    )
    parser.add_argument("--timeout", type=float, default=25.0, help="socket timeout seconds")
    args = parser.parse_args()

    socket.setdefaulttimeout(max(3.0, float(args.timeout or 25.0)))
    workers = max(1, min(int(args.workers or 1), 32))
    statuses = _parse_status_filter(args.status)

    db = get_db()
    rows = select_rows(
        db.iter_mail_accounts(),
        email=args.email,
        statuses=statuses,
        include_bad=bool(args.include_bad),
        limit=max(0, int(args.limit or 0)),
    )
    if not rows:
        print(f"no mail accounts selected db={db.path}")
        return 1

    print(
        f"selected={len(rows)} workers={workers} dry_run={bool(args.dry_run)} "
        f"db={db.path}",
        flush=True,
    )

    results: list[ProbeResult] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
        future_map = {executor.submit(probe_account, row): row for row in rows}
        for future in concurrent.futures.as_completed(future_map):
            result = future.result()
            result = write_result(
                result,
                dry_run=bool(args.dry_run),
                clear_fail_reason_on_ok=bool(args.clear_fail_reason_on_ok),
            )
            results.append(result)
            print_result(result)

    counts: dict[str, int] = {}
    for result in results:
        key = result.status if not result.ok else "ok"
        counts[key] = counts.get(key, 0) + 1
    ok = counts.get("ok", 0)
    bad = len(results) - ok
    print("\nsummary:")
    print(f"  total={len(results)} ok={ok} bad={bad}")
    for key in sorted(k for k in counts if k != "ok"):
        print(f"  {key}={counts[key]}")
    return 0 if bad == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
