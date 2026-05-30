#!/usr/bin/env python3
"""Import only sandbox/test payment cards into the PayPal card pool.

By default this refuses arbitrary PAN/CVV rows and only accepts a small built-in
sandbox allowlist. Use --allow-unlisted-test-cards only for cards exported from
PayPal's sandbox test-card generator.
"""

from __future__ import annotations

import argparse
from datetime import date
import json
import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = REPO_ROOT / "tem" / "tem_test_card"
DEFAULT_OUTPUT = REPO_ROOT / "output" / "paypal_test_cards.jsonl"


# Exact public sandbox/test card numbers only. Keep this deliberately small and
# explicit; do not add BIN/range rules. The unlisted-card flag below exists for
# rows exported by PayPal's sandbox test-card generator, which produces dynamic
# numbers that cannot be represented as a fixed allowlist.
SANDBOX_CARDS: dict[str, dict[str, str]] = {
    "4111111111111111": {
        "brand": "visa",
        "country": "US",
        "note": "PayPal sandbox generated success card",
    },
    "4012888888881881": {
        "brand": "visa",
        "country": "US",
        "note": "PayPal sandbox rejection-trigger test card",
    },
    "371449635398431": {
        "brand": "american_express",
        "country": "US",
        "note": "PayPal static sandbox test card",
    },
    "376680816376961": {
        "brand": "american_express",
        "country": "US",
        "note": "PayPal static sandbox test card",
    },
    "36461510000039": {
        "brand": "diners_club",
        "country": "US",
        "note": "PayPal static sandbox test card",
    },
    "36461510000013": {
        "brand": "diners_club",
        "country": "US",
        "note": "PayPal static sandbox test card",
    },
    "6304000000000000": {
        "brand": "maestro",
        "country": "US",
        "note": "PayPal static sandbox test card",
    },
}


def mask_pan(number: str) -> str:
    digits = re.sub(r"\D+", "", number or "")
    if len(digits) <= 10:
        return "*" * len(digits)
    return f"{digits[:6]}******{digits[-4:]}"


def normalize_year(year: str) -> str:
    year = re.sub(r"\D+", "", year or "")
    if len(year) == 2:
        return "20" + year
    return year


def resolve_path(path: str) -> Path:
    resolved = Path(path).expanduser()
    if not resolved.is_absolute():
        resolved = REPO_ROOT / resolved
    return resolved.resolve()


def split_expiry(expiry: str) -> tuple[str, str]:
    raw = str(expiry or "").strip()
    if not raw:
        return "", ""
    parts = [p for p in re.split(r"[\/\-\s]+", raw) if p]
    if len(parts) >= 2:
        return parts[0], parts[1]
    digits = re.sub(r"\D+", "", raw)
    if len(digits) == 4:
        return digits[:2], digits[2:]
    if len(digits) == 6:
        return digits[:2], digits[2:]
    return "", ""


def luhn_ok(number: str) -> bool:
    digits = [int(ch) for ch in re.sub(r"\D+", "", number or "")]
    if len(digits) < 12:
        return False
    total = 0
    parity = len(digits) % 2
    for index, digit in enumerate(digits):
        if index % 2 == parity:
            digit *= 2
            if digit > 9:
                digit -= 9
        total += digit
    return total % 10 == 0


def card_brand(number: str) -> str:
    digits = re.sub(r"\D+", "", number or "")
    if digits.startswith("4"):
        return "visa"
    if digits.startswith(("34", "37")):
        return "american_express"
    if digits.startswith(("36", "38", "39")) or 300 <= int((digits + "000")[:3]) <= 305:
        return "diners_club"
    if 51 <= int((digits + "00")[:2]) <= 55 or 2221 <= int((digits + "0000")[:4]) <= 2720:
        return "mastercard"
    if digits.startswith("6011") or digits.startswith("65") or 644 <= int((digits + "000")[:3]) <= 649:
        return "discover"
    if 3528 <= int((digits + "0000")[:4]) <= 3589:
        return "jcb"
    if digits.startswith(("50", "56", "57", "58", "59", "6")):
        return "maestro"
    return "unknown"


def validate_card(parsed: dict[str, str]) -> None:
    month = parsed["month"]
    year = parsed["year"]
    cvc = parsed["cvc"]
    if not luhn_ok(parsed["number"]):
        raise ValueError("card number failed Luhn check")
    if len(month) != 2 or not 1 <= int(month) <= 12:
        raise ValueError(f"invalid expiry month: {month}")
    if len(year) != 4:
        raise ValueError(f"invalid expiry year: {year}")
    exp_year = int(year)
    exp_month = int(month)
    today = date.today()
    if (exp_year, exp_month) < (today.year, today.month):
        raise ValueError(f"card is expired: {month}/{year}")
    if not re.fullmatch(r"\d{3,4}", cvc):
        raise ValueError("cvc must be 3 or 4 digits")


def parse_line(line: str) -> dict[str, str] | None:
    line = line.strip()
    if not line or line.startswith("#"):
        return None
    if line.startswith("{"):
        obj = json.loads(line)
        number = str(obj.get("number") or obj.get("card_number") or obj.get("cardNumber") or "")
        expiry = str(obj.get("expiry") or obj.get("cardExpiry") or "")
        month = str(obj.get("exp_month") or obj.get("month") or "")
        year = str(obj.get("exp_year") or obj.get("year") or "")
        cvc = str(
            obj.get("cvc")
            or obj.get("cvv")
            or obj.get("cardCvv")
            or obj.get("security_code")
            or obj.get("securityCode")
            or ""
        )
        if expiry and (not month or not year):
            month, year = split_expiry(expiry)
    else:
        parts = [p.strip() for p in re.split(r"[|,\t ]+", line) if p.strip()]
        if len(parts) == 3:
            number, expiry, cvc = parts
            month, year = split_expiry(expiry)
        elif len(parts) >= 4:
            cvc = parts[-1]
            year = parts[-2]
            month = parts[-3]
            number = "".join(parts[:-3])
        else:
            raise ValueError("expected number|month|year|cvv or number|expiry|cvv")

    number = re.sub(r"\D+", "", number)
    month = re.sub(r"\D+", "", month).zfill(2)
    year = normalize_year(year)
    cvc = re.sub(r"\D+", "", cvc)
    if not number or not month or not year or not cvc:
        raise ValueError("missing number/month/year/cvc")
    parsed = {"number": number, "month": month, "year": year, "cvc": cvc}
    validate_card(parsed)
    return parsed


def output_row(parsed: dict[str, str], *, allow_unlisted: bool = False) -> dict[str, str]:
    meta = SANDBOX_CARDS.get(parsed["number"])
    if not meta:
        if not allow_unlisted:
            raise ValueError("not in the built-in sandbox allowlist")
        meta = {
            "brand": card_brand(parsed["number"]),
            "country": "US",
            "note": "unlisted PayPal sandbox/generated test card",
        }
    return {
        "number": parsed["number"],
        "expiry": f"{parsed['month']}/{parsed['year'][-2:]}",
        "cvc": parsed["cvc"],
    }


def default_rows(month: str, year: str, cvc: str) -> list[dict[str, str]]:
    rows = []
    for number in SANDBOX_CARDS:
        parsed = {"number": number, "month": month, "year": year, "cvc": cvc}
        validate_card(parsed)
        rows.append(output_row(parsed))
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Import official sandbox cards into output/paypal_test_cards.jsonl",
    )
    parser.add_argument("--input", default=str(DEFAULT_INPUT), help="input text/jsonl file")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="output JSONL card pool")
    parser.add_argument("--append", action="store_true", help="append instead of overwrite")
    parser.add_argument("--dry-run", action="store_true", help="print rows without writing output")
    parser.add_argument(
        "--allow-unlisted-test-cards",
        action="store_true",
        help="accept Luhn-valid rows not in the built-in allowlist; only use with PayPal Sandbox generator exports",
    )
    parser.add_argument(
        "--include-defaults",
        action="store_true",
        help="write the built-in sandbox allowlist even if input has no allowed rows",
    )
    parser.add_argument("--default-month", default="12", help="expiry month for --include-defaults")
    parser.add_argument("--default-year", default="2030", help="expiry year for --include-defaults")
    parser.add_argument("--default-cvc", default="123", help="CVC for --include-defaults")
    args = parser.parse_args()

    input_path = resolve_path(args.input)
    output_path = resolve_path(args.output)

    accepted: list[dict[str, str]] = []
    rejected: list[str] = []
    parse_errors: list[str] = []

    if input_path.exists():
        for line_no, line in enumerate(input_path.read_text(encoding="utf-8").splitlines(), start=1):
            try:
                parsed = parse_line(line)
            except Exception as exc:
                parse_errors.append(f"line {line_no}: {exc}")
                continue
            if not parsed:
                continue
            try:
                accepted.append(output_row(parsed, allow_unlisted=args.allow_unlisted_test_cards))
            except Exception as exc:
                rejected.append(f"line {line_no}: {mask_pan(parsed['number'])}: {exc}")
    elif not args.include_defaults:
        raise SystemExit(f"input file not found: {input_path}")

    if args.include_defaults:
        accepted.extend(default_rows(args.default_month, normalize_year(args.default_year), args.default_cvc))

    deduped: list[dict[str, str]] = []
    seen: set[str] = set()
    for row in accepted:
        key = f"{row['number']}|{row['expiry']}|{row['cvc']}"
        if key in seen:
            continue
        seen.add(key)
        deduped.append(row)

    print(f"accepted sandbox rows: {len(deduped)}")
    print(f"rejected non-sandbox rows: {len(rejected)}")
    if rejected:
        print("rejected examples:")
        for item in rejected[:10]:
            print(f"  {item}")
    if parse_errors:
        print(f"parse errors: {len(parse_errors)}")
        for item in parse_errors[:10]:
            print(f"  {item}")

    if not deduped:
        raise SystemExit("no sandbox cards accepted; output not changed")

    body = "".join(
        json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n"
        for row in deduped
    )
    if args.dry_run:
        print(body, end="")
        return 0

    output_path.parent.mkdir(parents=True, exist_ok=True)
    mode = "a" if args.append else "w"
    with output_path.open(mode, encoding="utf-8") as f:
        f.write(body)
    print(f"wrote {len(deduped)} rows to {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
