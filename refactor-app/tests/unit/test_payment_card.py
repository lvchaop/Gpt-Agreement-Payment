from __future__ import annotations

import pytest

from refactor_app.plugins.payment_card import (
    PaymentCardDataError,
    normalize_card_cvc,
    normalize_card_number,
    payment_card_fingerprint,
)


def test_payment_card_data_normalizes_plaintext_values() -> None:
    assert normalize_card_number("4242 4242-4242 4242") == "4242424242424242"
    assert normalize_card_cvc(" 123 ") == "123"


def test_payment_card_fingerprint_is_stable_for_same_number() -> None:
    assert payment_card_fingerprint("4242-4242-4242-4242") == payment_card_fingerprint(
        "4242424242424242"
    )


@pytest.mark.parametrize(
    ("number", "cvc", "message"),
    [
        ("4242424242424241", "123", "checksum"),
        ("4242424242424242", "12", "cvc"),
    ],
)
def test_payment_card_data_rejects_invalid_values(
    number: str,
    cvc: str,
    message: str,
) -> None:
    with pytest.raises(PaymentCardDataError, match=message):
        normalize_card_number(number)
        normalize_card_cvc(cvc)
