#!/usr/bin/env python3
"""Import IMAP mailbox accounts from CSV/text into WebUI SQLite."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CTF_REG = ROOT / "CTF-reg"
if str(CTF_REG) not in sys.path:
    sys.path.insert(0, str(CTF_REG))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from email_account_pool import parse_accounts_text  # noqa: E402
from webui.backend.db import get_db  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Append email account pool into SQLite mail_accounts.")
    parser.add_argument(
        "--input",
        default=str(ROOT / "output" / "email_accounts.csv"),
        help="CSV/text source, default output/email_accounts.csv",
    )
    args = parser.parse_args()

    path = Path(args.input).expanduser()
    if not path.is_absolute():
        path = ROOT / path
    if not path.exists():
        raise SystemExit(f"source not found: {path}")

    rows = parse_accounts_text(path.read_text(encoding="utf-8"))
    if not rows:
        raise SystemExit(f"no email accounts parsed from: {path}")

    db = get_db()
    before = len(db.iter_mail_accounts())
    inserted = db.append_mail_accounts(rows)
    after = len(db.iter_mail_accounts())
    skipped = len(rows) - inserted
    print(
        f"parsed={len(rows)} inserted={inserted} skipped_existing={skipped} "
        f"before={before} after={after} db={db.path}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
