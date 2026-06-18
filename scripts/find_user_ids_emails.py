#!/usr/bin/env python3
"""Map quoted OpenAI user ids to emails from local SQLite token inventory."""

from __future__ import annotations

import argparse
import base64
import csv
import json
import re
import sqlite3
from pathlib import Path
from typing import Any


def decode_jwt_payload(token: str) -> dict[str, Any]:
    parts = (token or "").strip().split(".")
    if len(parts) < 2:
        return {}
    data = parts[1] + "=" * (-len(parts[1]) % 4)
    try:
        parsed = json.loads(base64.urlsafe_b64decode(data.encode("ascii")).decode("utf-8", errors="replace"))
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        return {}


def extract_identity(payload: dict[str, Any]) -> dict[str, str]:
    auth = payload.get("https://api.openai.com/auth")
    if not isinstance(auth, dict):
        auth = {}
    profile = payload.get("https://api.openai.com/profile")
    if not isinstance(profile, dict):
        profile = {}
    return {
        "user_id": str(auth.get("user_id") or ""),
        "chatgpt_user_id": str(auth.get("chatgpt_user_id") or ""),
        "chatgpt_account_user_id": str(auth.get("chatgpt_account_user_id") or ""),
        "chatgpt_account_id": str(auth.get("chatgpt_account_id") or ""),
        "sub": str(payload.get("sub") or ""),
        "token_email": str(profile.get("email") or payload.get("email") or ""),
    }


def read_targets(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8", errors="replace")
    # User explicitly said to pay attention to single quotes.
    quoted = re.findall(r"'(user-[^']+)'", text)
    if quoted:
        return list(dict.fromkeys(item.strip() for item in quoted if item.strip()))
    fallback = re.findall(r"\buser-[A-Za-z0-9_-]+\b", text)
    return list(dict.fromkeys(item.strip() for item in fallback if item.strip()))


def scan_db(db_path: Path) -> dict[str, list[dict[str, Any]]]:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    found: dict[str, list[dict[str, Any]]] = {}

    specs = [
        ("registered_accounts", ["id", "email", "access_token", "id_token"], ["access_token", "id_token"]),
        ("mail_accounts", ["id", "email", "account_id", "access_token"], ["access_token"]),
    ]
    for table, cols, token_cols in specs:
        sql = f"SELECT {', '.join(cols)} FROM {table}"
        for row in conn.execute(sql):
            row_map = dict(row)
            for token_col in token_cols:
                payload = decode_jwt_payload(str(row_map.get(token_col) or ""))
                if not payload:
                    continue
                ident = extract_identity(payload)
                user_ids = {
                    ident.get("user_id", ""),
                    ident.get("chatgpt_user_id", ""),
                    ident.get("chatgpt_account_user_id", ""),
                }
                for uid in [u for u in user_ids if u]:
                    found.setdefault(uid, []).append(
                        {
                            "email": row_map.get("email") or ident.get("token_email") or "",
                            "table": table,
                            "row_id": row_map.get("id"),
                            "token_column": token_col,
                            "sub": ident.get("sub", ""),
                            "token_email": ident.get("token_email", ""),
                            "chatgpt_account_id": ident.get("chatgpt_account_id", ""),
                            "mail_account_id": row_map.get("account_id", "") if table == "mail_accounts" else "",
                        }
                    )
    return found


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("input_file")
    parser.add_argument("--db", default="output/webui.db")
    parser.add_argument("--out", default="output/user_ids_emails.csv")
    parser.add_argument("--json-out", default="output/user_ids_emails.json")
    args = parser.parse_args()

    targets = read_targets(Path(args.input_file).expanduser())
    found = scan_db(Path(args.db).expanduser())

    rows: list[dict[str, Any]] = []
    for uid in targets:
        matches = found.get(uid) or []
        if not matches:
            rows.append(
                {
                    "user_id": uid,
                    "email": "",
                    "status": "missing",
                    "table": "",
                    "row_id": "",
                    "token_column": "",
                    "sub": "",
                    "token_email": "",
                    "chatgpt_account_id": "",
                    "mail_account_id": "",
                }
            )
            continue
        seen = set()
        for match in matches:
            key = (match.get("email"), match.get("table"), match.get("row_id"), match.get("token_column"))
            if key in seen:
                continue
            seen.add(key)
            rows.append({"user_id": uid, "status": "found", **match})

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "user_id",
        "email",
        "status",
        "table",
        "row_id",
        "token_column",
        "sub",
        "token_email",
        "chatgpt_account_id",
        "mail_account_id",
    ]
    with out_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    json_path = Path(args.json_out)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(
        json.dumps(
            {
                "input_file": str(Path(args.input_file).expanduser()),
                "db": args.db,
                "target_count": len(targets),
                "found_target_count": len({row["user_id"] for row in rows if row["status"] == "found"}),
                "missing_target_count": len({row["user_id"] for row in rows if row["status"] == "missing"}),
                "rows": rows,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print(
        json.dumps(
            {
                "target_count": len(targets),
                "found_target_count": len({row["user_id"] for row in rows if row["status"] == "found"}),
                "missing_target_count": len({row["user_id"] for row in rows if row["status"] == "missing"}),
                "row_count": len(rows),
                "csv": str(out_path),
                "json": str(json_path),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
