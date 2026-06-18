#!/usr/bin/env python3
"""List OpenAI user ids for registered accounts under an email domain."""

from __future__ import annotations

import argparse
import base64
import csv
import json
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


def identity_from_payload(payload: dict[str, Any]) -> dict[str, str]:
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


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("domain")
    parser.add_argument("--db", default="output/webui.db")
    parser.add_argument("--out", default="")
    parser.add_argument("--json-out", default="")
    args = parser.parse_args()

    domain = args.domain.strip().lower().lstrip("@")
    db_path = Path(args.db)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    rows = conn.execute(
        """
        SELECT id, email, access_token, id_token
        FROM registered_accounts
        WHERE lower(email) LIKE ?
        ORDER BY id
        """,
        ("%@" + domain,),
    ).fetchall()

    items: list[dict[str, Any]] = []
    for row in rows:
        source = ""
        identity = {}
        for col in ("access_token", "id_token"):
            payload = decode_jwt_payload(row[col] or "")
            ident = identity_from_payload(payload)
            if any(ident.values()):
                source = col
                identity = ident
                break
        items.append(
            {
                "id": row["id"],
                "email": row["email"],
                "token_source": source,
                **identity,
            }
        )

    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with out_path.open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(
                f,
                fieldnames=[
                    "id",
                    "email",
                    "token_source",
                    "user_id",
                    "chatgpt_user_id",
                    "chatgpt_account_user_id",
                    "chatgpt_account_id",
                    "sub",
                    "token_email",
                ],
            )
            writer.writeheader()
            writer.writerows(items)

    if args.json_out:
        json_path = Path(args.json_out)
        json_path.parent.mkdir(parents=True, exist_ok=True)
        json_path.write_text(
            json.dumps({"domain": domain, "count": len(items), "items": items}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    with_user_id = sum(1 for item in items if item.get("user_id"))
    print(
        json.dumps(
            {
                "db": str(db_path),
                "domain": domain,
                "count": len(items),
                "with_user_id": with_user_id,
                "csv": args.out,
                "json": args.json_out,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
