#!/usr/bin/env python3
"""Read Outlook messages through Microsoft Graph using stored OAuth tokens."""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, build_opener


ROOT = Path(__file__).resolve().parents[1]
CTF_REG = ROOT / "CTF-reg"
if str(CTF_REG) not in sys.path:
    sys.path.insert(0, str(CTF_REG))

from imap_otp_provider import extract_otp  # noqa: E402


TOKEN_URL = "https://login.microsoftonline.com/consumers/oauth2/v2.0/token"
GRAPH_MESSAGES_URL = "https://graph.microsoft.com/v1.0/me/messages"
GRAPH_SCOPE = "https://graph.microsoft.com/Mail.Read offline_access"


def _load_account(db_path: Path, email: str) -> dict:
    with sqlite3.connect(str(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            """
            SELECT email, account_id, access_token, refresh_token
            FROM mail_accounts
            WHERE lower(email)=lower(?)
            """,
            (email,),
        ).fetchone()
    if not row:
        raise SystemExit(f"mail_accounts 找不到账号: {email}")
    data = dict(row)
    if not data.get("account_id"):
        raise SystemExit(f"{email} 缺 account_id/client_id")
    if not data.get("refresh_token"):
        raise SystemExit(f"{email} 缺 refresh_token")
    return data


def _json_request(method: str, url: str, *, headers: dict | None = None, data: bytes | None = None) -> dict:
    opener = build_opener()
    req = Request(url, data=data, method=method, headers=headers or {})
    try:
        with opener.open(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            return json.loads(raw) if raw else {}
    except HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        try:
            body = json.loads(raw)
        except Exception:
            body = raw[:500]
        raise RuntimeError(f"{method} {url} HTTP {e.code}: {body}") from e


def _refresh_graph_token(client_id: str, refresh_token: str) -> dict:
    body = urlencode(
        {
            "client_id": client_id,
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "scope": GRAPH_SCOPE,
        }
    ).encode("utf-8")
    data = _json_request(
        "POST",
        TOKEN_URL,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data=body,
    )
    if not data.get("access_token"):
        raise RuntimeError(f"Graph refresh_token 未换出 access_token: {data}")
    return data


def _list_messages(access_token: str, *, limit: int) -> list[dict]:
    top = max(1, min(int(limit or 10), 50))
    query = urlencode(
        {
            "$top": str(top),
            "$orderby": "receivedDateTime desc",
            "$select": "id,receivedDateTime,from,subject,bodyPreview",
        }
    )
    data = _json_request(
        "GET",
        f"{GRAPH_MESSAGES_URL}?{query}",
        headers={"Authorization": f"Bearer {access_token}", "Accept": "application/json"},
    )
    messages = data.get("value") or []
    if not isinstance(messages, list):
        raise RuntimeError(f"Graph messages 返回异常: {data}")
    return messages


def _format_message(item: dict) -> dict:
    sender = ""
    try:
        sender = str((((item.get("from") or {}).get("emailAddress") or {}).get("address")) or "")
    except Exception:
        sender = ""
    subject = str(item.get("subject") or "")
    body = str(item.get("bodyPreview") or "")
    return {
        "id": item.get("id") or "",
        "date": item.get("receivedDateTime") or "",
        "from": sender,
        "subject": subject,
        "otp": extract_otp(subject, body, sender),
        "bodyPreview": body[:500],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Query Outlook mail through Microsoft Graph.")
    parser.add_argument("--email", required=True, help="mail_accounts 中的 Outlook 邮箱")
    parser.add_argument("--db", default=str(ROOT / "output" / "webui.db"), help="SQLite DB path")
    parser.add_argument("--limit", type=int, default=10, help="最多读取多少封邮件")
    parser.add_argument("--json", action="store_true", help="输出 JSON")
    args = parser.parse_args()

    account = _load_account(Path(args.db), args.email)
    token = _refresh_graph_token(account["account_id"], account["refresh_token"])
    messages = [_format_message(m) for m in _list_messages(token["access_token"], limit=args.limit)]
    result = {
        "email": account["email"],
        "provider": "graph",
        "scope": token.get("scope") or GRAPH_SCOPE,
        "message_count": len(messages),
        "otp": next((m["otp"] for m in messages if m.get("otp")), ""),
        "messages": messages,
    }
    if args.json:
        print(json.dumps([result], ensure_ascii=False, indent=2))
    else:
        print(f"email: {result['email']}")
        print(f"provider: {result['provider']}")
        print(f"scope: {result['scope']}")
        print(f"messages: {result['message_count']}")
        for item in messages:
            print("-" * 72)
            print(f"date: {item['date']}")
            print(f"from: {item['from']}")
            print(f"subject: {item['subject']}")
            print(f"otp: {item['otp'] or '-'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
