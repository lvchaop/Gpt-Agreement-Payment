#!/usr/bin/env python3
"""Report normal vs session-backfill-needed registered accounts.

Normal session rule:
  - session_token is present
  - access_token is present
  - cookie_header does NOT duplicate __Secure-next-auth.session-token

Everything else is reported as needing session backfill.
"""

from __future__ import annotations

import argparse
import csv
import sys
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from webui.backend.db import get_db  # noqa: E402


SESSION_COOKIE_NAME = "__Secure-next-auth.session-token="


def classify(row: dict) -> str:
    session_token = (row.get("session_token") or "").strip()
    access_token = (row.get("access_token") or "").strip()
    cookie_header = row.get("cookie_header") or ""
    if session_token and access_token and SESSION_COOKIE_NAME not in cookie_header:
        return "normal"
    if not session_token and not access_token:
        return "missing_session_and_access"
    if not session_token:
        return "missing_session_token"
    if not access_token:
        return "missing_access_token"
    if SESSION_COOKIE_NAME in cookie_header:
        return "cookie_header_duplicates_session_token"
    return "unknown"


def _selected(rows: list[dict], only: str) -> list[dict]:
    if only == "all":
        return rows
    if only == "normal":
        return [r for r in rows if classify(r) == "normal"]
    if only == "needs-session":
        return [r for r in rows if classify(r) != "normal"]
    return [r for r in rows if classify(r) == only]


def _row_summary(row: dict) -> dict:
    cookie_header = row.get("cookie_header") or ""
    return {
        "id": row.get("id", ""),
        "email": row.get("email", ""),
        "class": classify(row),
        "session_token_len": len(row.get("session_token") or ""),
        "access_token_len": len(row.get("access_token") or ""),
        "cookie_header_len": len(cookie_header),
        "cookie_has_session_token": "yes" if SESSION_COOKIE_NAME in cookie_header else "no",
        "refresh_token_len": len(row.get("refresh_token") or ""),
        "last_check_status": row.get("last_check_status") or "",
        "last_plan_type": row.get("last_plan_type") or "",
        "sale_status": row.get("sale_status") or "",
        "ts": row.get("ts") or "",
    }


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "id",
        "email",
        "class",
        "session_token_len",
        "access_token_len",
        "cookie_header_len",
        "cookie_has_session_token",
        "refresh_token_len",
        "last_check_status",
        "last_plan_type",
        "sale_status",
        "ts",
    ]
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow(_row_summary(row))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Report registered_accounts session health.",
    )
    parser.add_argument(
        "--only",
        default="all",
        help=(
            "which rows to print/export: all, normal, needs-session, "
            "or a concrete class name"
        ),
    )
    parser.add_argument("--limit", type=int, default=30, help="print first N selected rows")
    parser.add_argument("--emails-only", action="store_true", help="print only selected emails")
    parser.add_argument("--csv", default="", help="write selected rows to CSV")
    args = parser.parse_args()

    rows = get_db().iter_registered_accounts()
    counts = Counter(classify(r) for r in rows)
    normal = counts.get("normal", 0)
    needs = len(rows) - normal

    print(f"total={len(rows)}")
    print(f"normal={normal}")
    print(f"needs_session={needs}")
    print("\nclasses:")
    for key, value in counts.most_common():
        print(f"  {key}={value}")

    selected = _selected(rows, args.only)
    print(f"\nselected={len(selected)} only={args.only}")

    if args.csv:
        out = Path(args.csv).expanduser()
        if not out.is_absolute():
            out = ROOT / out
        write_csv(out, selected)
        print(f"csv={out}")

    limit = max(0, int(args.limit or 0))
    if limit:
        print("\nrows:")
        for row in selected[:limit]:
            summary = _row_summary(row)
            if args.emails_only:
                print(summary["email"])
            else:
                print(
                    f"{summary['id']} {summary['email']} class={summary['class']} "
                    f"session={summary['session_token_len']} access={summary['access_token_len']} "
                    f"cookie={summary['cookie_header_len']} "
                    f"cookie_has_session={summary['cookie_has_session_token']} "
                    f"rt={summary['refresh_token_len']}"
                )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
