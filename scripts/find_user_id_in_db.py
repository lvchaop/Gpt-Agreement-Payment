#!/usr/bin/env python3
"""Find an OpenAI user id inside local SQLite tokens.

Scans registered_accounts and mail_accounts token columns, decodes JWT payloads
without verifying signatures, and prints rows whose payload contains the target
user id.
"""

from __future__ import annotations

import argparse
import base64
import json
import sqlite3
from pathlib import Path
from typing import Any


def _b64url_json(part: str) -> dict[str, Any]:
    raw = (part or "").strip()
    if not raw:
        return {}
    raw += "=" * (-len(raw) % 4)
    try:
        data = base64.urlsafe_b64decode(raw.encode("ascii"))
        parsed = json.loads(data.decode("utf-8", errors="replace"))
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        return {}


def decode_jwt_payload(token: str) -> dict[str, Any]:
    token = (token or "").strip()
    parts = token.split(".")
    if len(parts) < 2:
        return {}
    return _b64url_json(parts[1])


def iter_values(obj: Any):
    if isinstance(obj, dict):
        for value in obj.values():
            yield from iter_values(value)
    elif isinstance(obj, list):
        for value in obj:
            yield from iter_values(value)
    else:
        yield obj


def payload_contains(payload: dict[str, Any], target: str) -> bool:
    return any(str(value) == target for value in iter_values(payload))


def pick_identity(payload: dict[str, Any]) -> dict[str, str]:
    auth = payload.get("https://api.openai.com/auth")
    if not isinstance(auth, dict):
        auth = {}
    profile = payload.get("https://api.openai.com/profile")
    if not isinstance(profile, dict):
        profile = {}
    return {
        "sub": str(payload.get("sub") or ""),
        "user_id": str(auth.get("user_id") or ""),
        "chatgpt_user_id": str(auth.get("chatgpt_user_id") or ""),
        "chatgpt_account_user_id": str(auth.get("chatgpt_account_user_id") or ""),
        "chatgpt_account_id": str(auth.get("chatgpt_account_id") or ""),
        "email": str(profile.get("email") or payload.get("email") or ""),
    }


def scan_table(conn: sqlite3.Connection, table: str, token_columns: list[str], target: str) -> list[dict[str, Any]]:
    cols = ["id", "email", *token_columns]
    sql = f"SELECT {', '.join(cols)} FROM {table}"
    out: list[dict[str, Any]] = []
    for row in conn.execute(sql):
        row_map = dict(zip(cols, row))
        for col in token_columns:
            token = str(row_map.get(col) or "")
            if not token:
                continue
            payload = decode_jwt_payload(token)
            if not payload:
                continue
            if payload_contains(payload, target):
                out.append(
                    {
                        "table": table,
                        "id": row_map.get("id"),
                        "email": row_map.get("email"),
                        "token_column": col,
                        "identity": pick_identity(payload),
                    }
                )
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("user_id", help="exact user id to find, e.g. user-...")
    parser.add_argument("--db", default="output/webui.db")
    args = parser.parse_args()

    db_path = Path(args.db).expanduser()
    if not db_path.exists():
        raise SystemExit(f"DB 不存在: {db_path}")

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    matches: list[dict[str, Any]] = []
    matches.extend(scan_table(conn, "registered_accounts", ["access_token", "id_token"], args.user_id))
    matches.extend(scan_table(conn, "mail_accounts", ["access_token"], args.user_id))

    print(json.dumps({
        "db": str(db_path),
        "user_id": args.user_id,
        "match_count": len(matches),
        "matches": matches,
    }, ensure_ascii=False, indent=2))
    return 0 if matches else 1


if __name__ == "__main__":
    raise SystemExit(main())
