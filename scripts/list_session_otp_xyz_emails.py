#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SNAPSHOT_DIR = ROOT / "output" / "session_otp_snapshots"


def _email_from_snapshot(path: Path) -> str:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            email = str(data.get("email") or "").strip()
            if email:
                return email
            session = data.get("oai-client-auth-session")
            if isinstance(session, dict):
                email = str(session.get("email") or "").strip()
                if email:
                    return email
    except Exception:
        pass
    return path.stem.strip()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="输出 output/session_otp_snapshots 下域名后缀匹配的邮箱，默认 .xyz"
    )
    parser.add_argument(
        "--dir",
        default=str(DEFAULT_SNAPSHOT_DIR),
        help=f"快照目录，默认 {DEFAULT_SNAPSHOT_DIR}",
    )
    parser.add_argument(
        "--suffix",
        default=".xyz",
        help="邮箱域名后缀，默认 .xyz",
    )
    args = parser.parse_args()

    snapshot_dir = Path(args.dir).expanduser()
    suffix = str(args.suffix or ".xyz").strip().lower()
    suffix = suffix[1:] if suffix.startswith("@") else suffix

    emails: list[str] = []
    for path in sorted(snapshot_dir.glob("*.json")):
        email = _email_from_snapshot(path)
        domain = email.rsplit("@", 1)[-1].lower() if "@" in email else ""
        if suffix.startswith("."):
            matched = domain.endswith(suffix)
        elif "." in suffix:
            matched = domain == suffix or domain.endswith("." + suffix)
        else:
            matched = domain.endswith("." + suffix)
        if matched:
            emails.append(email)

    for email in sorted(set(emails)):
        print(email)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
