from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable, Mapping, Sequence
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from refactor_app.infrastructure.db.models import (
    PaymentAddressPoolModel,
    PaymentCardPoolModel,
    PaymentNamePoolModel,
    SpaceModel,
)
from refactor_app.plugins.payment_card import (
    PaymentCardDataError,
    normalize_card_cvc,
    normalize_card_number,
    payment_card_fingerprint,
)


class PaymentMethodInventoryError(RuntimeError):
    pass


PAYMENT_METHOD_MAX_ATTEMPTS = 3
PAYMENT_METHOD_COOLDOWN_HOURS = 6

_PAYMENT_COUNTRY_ALIASES = {
    "us": "US",
    "usa": "US",
    "united states": "US",
    "united states of america": "US",
    "ca": "CA",
    "canada": "CA",
    "gb": "GB",
    "uk": "GB",
    "united kingdom": "GB",
    "au": "AU",
    "australia": "AU",
    "de": "DE",
    "germany": "DE",
    "fr": "FR",
    "france": "FR",
    "jp": "JP",
    "japan": "JP",
}
_PAYMENT_CARD_LINE_RE = re.compile(
    r"(?:^|\|)\s*(?P<card_number>\d{12,19})\s*\|\s*"
    r"(?P<exp_month>\d{1,2})\s*\|\s*(?P<exp_year>\d{2,4})\s*\|\s*"
    r"(?P<cvc>\d{3,4})(?=\s*(?:\||$))"
)


def import_payment_method_inventory(
    *,
    session: Session,
    names: Sequence[str],
    addresses: Sequence[Mapping[str, Any] | str],
    cards: Sequence[Mapping[str, Any] | str],
) -> dict[str, Any]:
    normalized_names = _unique_by_key(_normalize_name(item) for item in names)
    normalized_addresses = _unique_by_key(
        _normalize_import_items(addresses, _normalize_address, kind="address")
    )
    normalized_cards = _unique_by_key(
        _normalize_import_items(cards, _normalize_card, kind="card")
    )
    if not normalized_names and not normalized_addresses and not normalized_cards:
        raise PaymentMethodInventoryError("payment method inventory import is empty")

    now = datetime.now(UTC)
    name_result = _insert_names(session, normalized_names, now=now)
    address_result = _insert_addresses(session, normalized_addresses, now=now)
    card_result = _insert_cards(session, normalized_cards, now=now)
    session.flush()
    return {
        "names": name_result,
        "addresses": address_result,
        "cards": card_result,
        "inserted_count": sum(
            int(item["inserted_count"])
            for item in (name_result, address_result, card_result)
        ),
        "existing_count": sum(
            int(item["existing_count"])
            for item in (name_result, address_result, card_result)
        ),
        "summary": payment_method_inventory_summary(session),
    }


def payment_method_inventory_summary(session: Session) -> dict[str, Any]:
    name_status_counts = _status_counts(
        session,
        model=PaymentNamePoolModel,
        column=PaymentNamePoolModel.name_status,
    )
    address_status_counts = _status_counts(
        session,
        model=PaymentAddressPoolModel,
        column=PaymentAddressPoolModel.address_status,
    )
    card_status_counts = _status_counts(
        session,
        model=PaymentCardPoolModel,
        column=PaymentCardPoolModel.card_status,
    )
    pending_personal_space_count = int(
        session.scalar(
            select(func.count())
            .select_from(SpaceModel)
            .where(
                SpaceModel.space_type == "personal",
                SpaceModel.space_status == "active",
                SpaceModel.has_promotion.is_(True),
                SpaceModel.promotion_id != "",
                SpaceModel.has_payment_method.is_(False),
                SpaceModel.payment_method_status != "binding",
                or_(
                    SpaceModel.payment_method_attempt_count < PAYMENT_METHOD_MAX_ATTEMPTS,
                    (
                        SpaceModel.payment_method_cooldown_until.is_not(None)
                        & (SpaceModel.payment_method_cooldown_until <= datetime.now(UTC))
                    ),
                ),
            )
        )
        or 0
    )
    return {
        "name_count": sum(name_status_counts.values()),
        "active_name_count": name_status_counts.get("active", 0),
        "name_status_counts": name_status_counts,
        "address_count": sum(address_status_counts.values()),
        "active_address_count": address_status_counts.get("active", 0),
        "address_status_counts": address_status_counts,
        "card_count": sum(card_status_counts.values()),
        "available_card_count": card_status_counts.get("available", 0),
        "card_status_counts": card_status_counts,
        "pending_personal_space_count": pending_personal_space_count,
    }


def _normalize_name(value: str) -> tuple[str, dict[str, Any]]:
    full_name = " ".join(str(value or "").split())
    if len(full_name) < 2 or len(full_name) > 200:
        raise PaymentMethodInventoryError("payment name must contain 2 to 200 characters")
    normalized_name = full_name.casefold()
    return normalized_name, {
        "full_name": full_name,
        "normalized_name": normalized_name,
    }


def parse_payment_address_line(value: str) -> dict[str, Any]:
    text = _strip_payment_import_label(value, "地址")
    if not text:
        raise PaymentMethodInventoryError("payment address line is empty")
    if text.startswith("{"):
        return _parse_payment_import_object(text, "address")

    parts = [part.strip() for part in text.split(",")]
    if len(parts) < 4 or any(not part for part in parts[-4:]):
        raise PaymentMethodInventoryError(
            "payment address line must be 'street, city, state postal_code, country'"
        )
    line1 = ", ".join(parts[:-3])
    city = parts[-3]
    region_postal = parts[-2]
    country = _normalize_import_country(parts[-1])
    state, postal_code = _split_region_postal(region_postal, country)
    return {
        "line1": line1,
        "line2": "",
        "city": city,
        "state": state,
        "postal_code": postal_code,
        "country": country,
        "phone": "",
    }


def parse_payment_card_line(value: str) -> dict[str, Any]:
    text = _strip_payment_import_label(value, "卡片")
    if not text:
        raise PaymentMethodInventoryError("payment card line is empty")
    if text.startswith("{"):
        return _parse_payment_import_object(text, "card")
    match = _PAYMENT_CARD_LINE_RE.search(text)
    if match is None:
        raise PaymentMethodInventoryError(
            "payment card line must contain card_number|MM|YYYY|CVC"
        )
    return {
        "card_number": match.group("card_number"),
        "cvc": match.group("cvc"),
        "exp_month": int(match.group("exp_month")),
        "exp_year": int(match.group("exp_year")),
    }


def _normalize_address(value: Mapping[str, Any] | str) -> tuple[str, dict[str, Any]]:
    if isinstance(value, str):
        value = parse_payment_address_line(value)
    data = {
        "line1": _required_text(value, "line1", maximum=300),
        "line2": _optional_text(value, "line2", maximum=300),
        "city": _required_text(value, "city", maximum=120),
        "state": _optional_text(value, "state", maximum=120),
        "postal_code": _required_text(value, "postal_code", maximum=40),
        "country": _required_text(value, "country", maximum=2).upper(),
        "phone": _optional_text(value, "phone", maximum=40),
    }
    if not re.fullmatch(r"[A-Z]{2}", data["country"]):
        raise PaymentMethodInventoryError("payment address country must be a two-letter code")
    address_key = hashlib.sha256(
        json.dumps(data, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode(
            "utf-8"
        )
    ).hexdigest()
    return address_key, {"address_key": address_key, **data}


def _normalize_card(value: Mapping[str, Any] | str) -> tuple[str, dict[str, Any]]:
    if isinstance(value, str):
        value = parse_payment_card_line(value)
    try:
        card_number = normalize_card_number(str(value.get("card_number") or ""))
        cvc = normalize_card_cvc(str(value.get("cvc") or ""))
    except PaymentCardDataError as exc:
        raise PaymentMethodInventoryError(str(exc)) from exc
    try:
        exp_month = int(value.get("exp_month") or 0)
        exp_year = int(value.get("exp_year") or 0)
    except (TypeError, ValueError) as exc:
        raise PaymentMethodInventoryError("card expiration must be numeric") from exc
    if 0 <= exp_year < 100:
        exp_year += 2000
    now = datetime.now(UTC)
    if exp_month < 1 or exp_month > 12:
        raise PaymentMethodInventoryError("card expiration month must be between 1 and 12")
    if (exp_year, exp_month) < (now.year, now.month):
        raise PaymentMethodInventoryError("card is expired")
    fingerprint = payment_card_fingerprint(card_number)
    return fingerprint, {
        "card_fingerprint": fingerprint,
        "card_number": card_number,
        "cvc": cvc,
        "last4": card_number[-4:],
        "exp_month": exp_month,
        "exp_year": exp_year,
    }


def _normalize_import_items(
    values: Sequence[Mapping[str, Any] | str],
    normalizer: Any,
    *,
    kind: str,
) -> list[tuple[str, dict[str, Any]]]:
    normalized: list[tuple[str, dict[str, Any]]] = []
    for index, value in enumerate(values, start=1):
        try:
            normalized.append(normalizer(value))
        except PaymentMethodInventoryError as exc:
            raise PaymentMethodInventoryError(f"{kind} line {index}: {exc}") from exc
    return normalized


def _strip_payment_import_label(value: str, label: str) -> str:
    text = " ".join(str(value or "").split())
    return re.sub(rf"^{re.escape(label)}\s*[:：]\s*", "", text, flags=re.IGNORECASE)


def _parse_payment_import_object(value: str, kind: str) -> dict[str, Any]:
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        raise PaymentMethodInventoryError(
            f"payment {kind} import line is not valid JSON"
        ) from exc
    if not isinstance(parsed, dict):
        raise PaymentMethodInventoryError(f"payment {kind} import line must be an object")
    return parsed


def _normalize_import_country(value: str) -> str:
    normalized = " ".join(str(value or "").split()).strip(" .").casefold()
    if len(normalized) == 2 and normalized.isascii() and normalized.isalpha():
        return normalized.upper()
    country = _PAYMENT_COUNTRY_ALIASES.get(normalized)
    if country:
        return country
    raise PaymentMethodInventoryError(
        f"unsupported payment address country '{value}'; use a two-letter ISO code"
    )


def _split_region_postal(value: str, country: str) -> tuple[str, str]:
    normalized = " ".join(str(value or "").split())
    if country == "US":
        if re.fullmatch(r"\d{5}(?:-\d{4})?", normalized):
            return "", normalized
        match = re.fullmatch(
            r"(?P<state>.+?)\s+(?P<postal>\d{5}(?:-\d{4})?)",
            normalized,
        )
    else:
        pieces = normalized.rsplit(" ", 1)
        match = (
            re.match(r"(?P<state>.+)$", pieces[0])
            if len(pieces) == 2 and pieces[0] and pieces[1]
            else None
        )
        if match is not None:
            return match.group("state"), pieces[1]
    if match is None:
        raise PaymentMethodInventoryError(
            "payment address line must include state/region and postal code"
        )
    return match.group("state").strip(), match.group("postal").strip()


def _insert_names(
    session: Session,
    values: list[tuple[str, dict[str, Any]]],
    *,
    now: datetime,
) -> dict[str, int]:
    existing = _existing_values(
        session,
        column=PaymentNamePoolModel.normalized_name,
        keys=[key for key, _data in values],
    )
    for key, data in values:
        if key in existing:
            continue
        session.add(
            PaymentNamePoolModel(
                id=str(uuid4()),
                **data,
                name_status="active",
                use_count=0,
                created_at=now,
                updated_at=now,
            )
        )
    return _insert_result(values, existing)


def _insert_addresses(
    session: Session,
    values: list[tuple[str, dict[str, Any]]],
    *,
    now: datetime,
) -> dict[str, int]:
    existing = _existing_values(
        session,
        column=PaymentAddressPoolModel.address_key,
        keys=[key for key, _data in values],
    )
    for key, data in values:
        if key in existing:
            continue
        session.add(
            PaymentAddressPoolModel(
                id=str(uuid4()),
                **data,
                address_status="active",
                use_count=0,
                created_at=now,
                updated_at=now,
            )
        )
    return _insert_result(values, existing)


def _insert_cards(
    session: Session,
    values: list[tuple[str, dict[str, Any]]],
    *,
    now: datetime,
) -> dict[str, int]:
    existing = _existing_values(
        session,
        column=PaymentCardPoolModel.card_fingerprint,
        keys=[key for key, _data in values],
    )
    for key, data in values:
        if key in existing:
            continue
        session.add(
            PaymentCardPoolModel(
                id=str(uuid4()),
                **data,
                card_status="available",
                use_count=0,
                last_error_code="",
                last_error_message="",
                created_at=now,
                updated_at=now,
            )
        )
    return _insert_result(values, existing)


def _unique_by_key(
    values: Iterable[tuple[str, dict[str, Any]]],
) -> list[tuple[str, dict[str, Any]]]:
    unique: dict[str, dict[str, Any]] = {}
    for key, data in values:
        unique.setdefault(key, data)
    return list(unique.items())


def _existing_values(session: Session, *, column: Any, keys: list[str]) -> set[str]:
    if not keys:
        return set()
    return set(session.scalars(select(column).where(column.in_(keys))).all())


def _insert_result(
    values: list[tuple[str, dict[str, Any]]],
    existing: set[str],
) -> dict[str, int]:
    inserted_count = sum(1 for key, _data in values if key not in existing)
    return {
        "requested_count": len(values),
        "inserted_count": inserted_count,
        "existing_count": len(values) - inserted_count,
    }


def _status_counts(session: Session, *, model: Any, column: Any) -> dict[str, int]:
    return {
        str(status): int(count)
        for status, count in session.execute(
            select(column, func.count()).select_from(model).group_by(column)
        ).all()
    }


def _required_text(value: Mapping[str, Any], key: str, *, maximum: int) -> str:
    normalized = _optional_text(value, key, maximum=maximum)
    if not normalized:
        raise PaymentMethodInventoryError(f"payment address {key} is required")
    return normalized


def _optional_text(value: Mapping[str, Any], key: str, *, maximum: int) -> str:
    normalized = " ".join(str(value.get(key) or "").split())
    if len(normalized) > maximum:
        raise PaymentMethodInventoryError(f"payment address {key} is too long")
    return normalized
