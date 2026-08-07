from __future__ import annotations

import hashlib
import re


class PaymentCardDataError(RuntimeError):
    pass


def normalize_card_number(value: str) -> str:
    number = re.sub(r"[\s-]+", "", str(value or ""))
    if not re.fullmatch(r"\d{12,19}", number):
        raise PaymentCardDataError("card number must contain 12 to 19 digits")
    if not _passes_luhn(number):
        raise PaymentCardDataError("card number failed checksum validation")
    return number


def normalize_card_cvc(value: str) -> str:
    cvc = str(value or "").strip()
    if not re.fullmatch(r"\d{3,4}", cvc):
        raise PaymentCardDataError("card cvc must contain 3 or 4 digits")
    return cvc


def payment_card_fingerprint(number: str) -> str:
    normalized = normalize_card_number(number)
    return hashlib.sha256(normalized.encode("ascii")).hexdigest()


def _passes_luhn(number: str) -> bool:
    total = 0
    parity = len(number) % 2
    for index, character in enumerate(number):
        digit = int(character)
        if index % 2 == parity:
            digit *= 2
            if digit > 9:
                digit -= 9
        total += digit
    return total % 10 == 0
