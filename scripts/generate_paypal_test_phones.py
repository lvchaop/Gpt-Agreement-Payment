#!/usr/bin/env python3
"""Generate a separate PayPal test-phone pool."""

from __future__ import annotations

import argparse
import json
import random
import re
import string
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = ROOT / "output" / "paypal_test_phones.jsonl"
DEFAULT_PHONE = "7633138658"


def _resolve_path(path: str) -> Path:
    resolved = Path(path).expanduser()
    if not resolved.is_absolute():
        resolved = ROOT / resolved
    return resolved.resolve()


def _normalize_phone(raw: str) -> str:
    phone = re.sub(r"\D+", "", raw)
    if len(phone) != 10:
        raise ValueError(f"Phone must be a 10-digit US test number: {raw}")
    return phone


def _split_phones(raw: str) -> list[str]:
    phones = [_normalize_phone(item) for item in raw.split(",") if item.strip()]
    if not phones:
        raise ValueError("--phone/--phones must contain at least one phone")
    return phones


def _token(rng: random.Random, alphabet: str, length: int) -> str:
    return "".join(rng.choice(alphabet) for _ in range(length))


def _make_phone(rng: random.Random, prefix: str) -> str:
    prefix = re.sub(r"\D+", "", prefix)
    if prefix:
        if len(prefix) >= 10:
            raise ValueError("--phone-prefix must be shorter than 10 digits")
        return prefix + _token(rng, string.digits, 10 - len(prefix))

    area = rng.randrange(201, 990)
    exchange = rng.randrange(201, 990)
    line = rng.randrange(0, 10000)
    return f"{area:03d}{exchange:03d}{line:04d}"


def _unique_phone(rng: random.Random, prefix: str, seen: set[str]) -> str:
    for _ in range(10000):
        phone = _make_phone(rng, prefix)
        if phone not in seen:
            seen.add(phone)
            return phone
    raise RuntimeError("Unable to generate unique phone numbers; relax --phone-prefix")


def generate_phones(
    *,
    count: int,
    phones: list[str],
    phone_mode: str,
    phone_prefix: str,
    rng: random.Random,
) -> list[dict[str, str]]:
    if phone_mode == "unique":
        seen: set[str] = set()
        return [{"phone": _unique_phone(rng, phone_prefix, seen)} for _ in range(count)]
    if phone_mode == "round_robin":
        return [{"phone": phones[index % len(phones)]} for index in range(count)]
    if phone_mode == "random":
        return [{"phone": rng.choice(phones)} for _ in range(count)]
    return [{"phone": phones[0]} for _ in range(count)]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--count", type=int, default=20)
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    parser.add_argument("--phone", default=DEFAULT_PHONE)
    parser.add_argument("--phones", default="", help="Comma-separated small test-phone pool")
    parser.add_argument(
        "--phone-mode",
        choices=("fixed", "round_robin", "random", "unique"),
        default="unique",
    )
    parser.add_argument("--phone-prefix", default="763313", help="Used only by --phone-mode unique")
    parser.add_argument("--seed", default="", help="Optional seed for reproducible output")
    parser.add_argument("--append", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if args.count < 1:
        raise SystemExit("--count must be >= 1")
    phones = [] if args.phone_mode == "unique" else _split_phones(args.phones or args.phone)
    rng: random.Random
    rng = random.Random(args.seed) if args.seed else random.SystemRandom()
    rows = generate_phones(
        count=args.count,
        phones=phones,
        phone_mode=args.phone_mode,
        phone_prefix=args.phone_prefix,
        rng=rng,
    )
    body = "".join(
        json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n"
        for row in rows
    )

    out = _resolve_path(args.out)
    if args.dry_run:
        print(body, end="")
    else:
        out.parent.mkdir(parents=True, exist_ok=True)
        mode = "a" if args.append else "w"
        with out.open(mode, encoding="utf-8") as f:
            f.write(body)
        print(json.dumps({
            "written": len(rows),
            "path": str(out),
            "append": bool(args.append),
            "phone_mode": args.phone_mode,
            "unique_phones": len({row["phone"] for row in rows}),
            "phone_prefix": re.sub(r"\D+", "", args.phone_prefix) if args.phone_mode == "unique" else "",
        }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
