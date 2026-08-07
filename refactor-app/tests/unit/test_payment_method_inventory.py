from __future__ import annotations

import pytest

from refactor_app.application.workflows.payment_method_inventory import (
    PaymentMethodInventoryError,
    _normalize_address,
    _normalize_card,
    _normalize_name,
    parse_payment_address_line,
    parse_payment_card_line,
)


def test_payment_inventory_normalizes_name_address_and_card() -> None:
    name_key, name = _normalize_name("  Ada   Lovelace ")
    address_key, address = _normalize_address(
        {
            "line1": " 123  Test Street ",
            "city": " New York ",
            "state": " ny ",
            "postal_code": "10001",
            "country": "us",
        }
    )
    card_key, card = _normalize_card(
        {
            "card_number": "4242 4242 4242 4242",
            "cvc": "123",
            "exp_month": 12,
            "exp_year": 2030,
        }
    )

    assert name_key == "ada lovelace"
    assert name["full_name"] == "Ada Lovelace"
    assert len(address_key) == 64
    assert address["country"] == "US"
    assert len(card_key) == 64
    assert card["card_number"] == "4242424242424242"
    assert card["cvc"] == "123"
    assert card["last4"] == "4242"


@pytest.mark.parametrize(
    "value",
    [
        {"line1": "", "city": "Paris", "postal_code": "75001", "country": "FR"},
        {"line1": "1 Main", "city": "Paris", "postal_code": "75001", "country": "France"},
    ],
)
def test_payment_inventory_rejects_invalid_address(value: dict) -> None:
    with pytest.raises(PaymentMethodInventoryError):
        _normalize_address(value)


def test_payment_inventory_accepts_two_digit_expiration_year() -> None:
    _key, card = _normalize_card(
        {
            "card_number": "4242424242424242",
            "cvc": "123",
            "exp_month": 12,
            "exp_year": 30,
        }
    )

    assert card["exp_year"] == 2030


def test_payment_inventory_parses_plain_address_line() -> None:
    parsed = parse_payment_address_line(
        "310 Jefferson Street, Middletown, Delaware 19709, United States"
    )

    assert parsed == {
        "line1": "310 Jefferson Street",
        "line2": "",
        "city": "Middletown",
        "state": "Delaware",
        "postal_code": "19709",
        "country": "US",
        "phone": "",
    }


def test_payment_inventory_parses_checker_card_line() -> None:
    parsed = parse_payment_card_line(
        "Live | 4242424242424242|01|2030|123 | [BIN: US - visa - debit] | Charge OK."
    )

    assert parsed == {
        "card_number": "4242424242424242",
        "cvc": "123",
        "exp_month": 1,
        "exp_year": 2030,
    }


def test_payment_inventory_keeps_json_line_compatibility() -> None:
    _key, address = _normalize_address(
        '{"line1":"123 Main St","city":"New York","postal_code":"10001","country":"US"}'
    )
    _card_key, card = _normalize_card(
        '{"card_number":"4242424242424242","cvc":"123","exp_month":12,"exp_year":2030}'
    )

    assert address["line1"] == "123 Main St"
    assert card["last4"] == "4242"
