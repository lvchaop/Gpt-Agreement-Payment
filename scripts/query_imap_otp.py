#!/usr/bin/env python3
"""Offline IMAP OTP lookup for Outlook/Gmail mailbox accounts.

This script only reads existing mailbox messages. It does not run registration,
does not write Cloudflare KV, and does not mark messages as seen by default.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CTF_REG = ROOT / "CTF-reg"
if str(CTF_REG) not in sys.path:
    sys.path.insert(0, str(CTF_REG))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from email_account_pool import account_from_row, email_account_pool_from_path, parse_accounts_text  # noqa: E402
from imap_otp_provider import ImapOtpProvider, extract_otp  # noqa: E402


def _mask_email(email: str) -> str:
    email = (email or "").strip()
    if "@" not in email:
        return "***" if email else ""
    local, domain = email.split("@", 1)
    if len(local) <= 2:
        return f"{local[:1]}***@{domain}"
    return f"{local[:2]}***{local[-1:]}@{domain}"


def _account_from_inline(text: str):
    rows = parse_accounts_text(text)
    if not rows:
        raise SystemExit("无法解析 --account；格式: email----password 或 email----password----client_id----refresh_token")
    return account_from_row(rows[0])


def _load_accounts(args) -> list:
    if args.account:
        return [_account_from_inline(args.account)]

    pool = email_account_pool_from_path(args.pool)
    if args.email:
        acc = pool.find(args.email)
        if not acc:
            raise SystemExit(f"账号池里找不到: {args.email}")
        return [acc]

    if args.all:
        accounts = pool.load_accounts()
        if not accounts:
            raise SystemExit(f"账号池为空: {args.pool}")
        return accounts

    raise SystemExit("请指定 --email、--all，或 --account")


def _query_account(account, *, limit: int, mark_seen: bool) -> dict:
    provider = ImapOtpProvider(account, mark_seen=mark_seen)
    messages = provider._recent_openai_messages(limit=limit)
    matches = []
    for msg in messages:
        otp = extract_otp(
            msg.get("subject", ""),
            msg.get("body", ""),
            msg.get("from", ""),
        )
        matches.append(
            {
                "uid": msg.get("uid", ""),
                "date": msg.get("datetime", ""),
                "from": msg.get("from", ""),
                "subject": msg.get("subject", ""),
                "otp": otp,
            }
        )
    first_otp = next((m["otp"] for m in matches if m.get("otp")), "")
    return {
        "email": account.email,
        "provider": account.provider,
        "imap_host": account.imap_host,
        "message_count": len(matches),
        "otp": first_otp,
        "messages": matches,
    }


def _print_text(results: list[dict], *, reveal_email: bool) -> None:
    for result in results:
        email = result["email"] if reveal_email else _mask_email(result["email"])
        print(f"email: {email}")
        print(f"provider: {result.get('provider') or '-'}")
        print(f"imap_host: {result.get('imap_host') or '-'}")
        print(f"latest_otp: {result.get('otp') or '-'}")
        print(f"messages: {result.get('message_count', 0)}")
        for item in result.get("messages", []):
            print("-" * 72)
            print(f"uid: {item.get('uid') or '-'}")
            print(f"date: {item.get('date') or '-'}")
            print(f"from: {item.get('from') or '-'}")
            print(f"subject: {item.get('subject') or '-'}")
            print(f"otp: {item.get('otp') or '-'}")
        print("=" * 72)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Offline lookup of OpenAI/ChatGPT OTP codes from IMAP mailboxes.",
    )
    parser.add_argument(
        "--pool",
        default="sqlite:mail_accounts",
        help="邮箱账号池，固定为 sqlite:mail_accounts",
    )
    parser.add_argument("--email", default="", help="只查询账号池里的指定邮箱")
    parser.add_argument("--all", action="store_true", help="查询账号池里的全部邮箱")
    parser.add_argument(
        "--account",
        default="",
        help="直接传入单个账号，格式 email----password 或 email----password----client_id----refresh_token",
    )
    parser.add_argument("--limit", type=int, default=20, help="每个邮箱最多扫描最近多少封 OpenAI/ChatGPT 邮件")
    parser.add_argument("--mark-seen", action="store_true", help="读取时允许 IMAP 标记已读；默认只读")
    parser.add_argument("--json", action="store_true", help="输出 JSON")
    parser.add_argument("--reveal-email", action="store_true", help="文本输出时显示完整邮箱；默认脱敏")
    args = parser.parse_args()

    accounts = _load_accounts(args)
    results = []
    for account in accounts:
        try:
            results.append(_query_account(account, limit=max(1, args.limit), mark_seen=args.mark_seen))
        except Exception as e:
            results.append(
                {
                    "email": account.email,
                    "provider": account.provider,
                    "imap_host": account.imap_host,
                    "error": str(e),
                    "message_count": 0,
                    "otp": "",
                    "messages": [],
                }
            )

    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
    else:
        _print_text(results, reveal_email=args.reveal_email)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
