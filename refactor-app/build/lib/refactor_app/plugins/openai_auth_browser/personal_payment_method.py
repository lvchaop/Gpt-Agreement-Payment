from __future__ import annotations

import json
import logging
import re
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from refactor_app.plugins.openai_auth_browser.personal_plus_checkout import (
    CREATE_PLUS_CHECKOUT_SCRIPT,
    create_plus_checkout_with_script,
)

logger = logging.getLogger(__name__)
PaymentHttpTraceEmitter = Callable[[str, dict[str, Any], str], None]
PaymentMethodCardProvider = Callable[[int], tuple[Any, Any]]
PaymentMethodSuccessCallback = Callable[[Any, int, Any], None]
PaymentMethodFailureCallback = Callable[[Any, int, Exception], None]
PAYMENT_METHOD_CARD_RETRY_DELAY_S = 3.0
PAYMENT_METHOD_CHECKOUT_RETRY_ATTEMPTS = 3
PAYMENT_METHOD_CHECKOUT_RETRY_DELAY_S = 5.0


class BrowserPersonalPaymentMethodError(RuntimeError):
    pass


class BrowserPaymentMethodConfirmError(BrowserPersonalPaymentMethodError):
    def __init__(
        self,
        error_code: str,
        error_message: str = "",
        *,
        diagnostics: dict[str, str] | None = None,
    ) -> None:
        self.error_code = str(error_code or "payment_method_confirm_failed")
        self.error_message = str(error_message or "")
        self.diagnostics = _sanitize_stripe_confirm_diagnostics(diagnostics)
        super().__init__(f"{self.error_code}: {self.error_message}".rstrip(": "))


_MAIN_WORLD_PREFIX = "mw:"
_PAYMENT_METHOD_FORM_SCRIPT_PATH = Path(__file__).with_name("personal_payment_method_form.js")
PAYMENT_METHOD_FORM_SCRIPT = _PAYMENT_METHOD_FORM_SCRIPT_PATH.read_text(encoding="utf-8")
_PAYMENT_METHOD_FORM_READY_EXPRESSION = r"""() => {
    const button = document.querySelector('#__card_submit__');
    return Boolean(button && button.disabled === false);
}"""
_PAYMENT_METHOD_FORM_RESULT_EXPRESSION = r"""() => {
    const result = window.__personalPaymentMethodBind || null;
    const button = document.querySelector('#__card_submit__');
    const message = document.querySelector('#__card_message__');
    const paymentMethod = result?.paymentMethod || {};
    return JSON.stringify({
        ok: Boolean(result?.paymentMethodId),
        payment_method_id: String(result?.paymentMethodId || ''),
        last4: String(paymentMethod?.card?.last4 || ''),
        brand: String(paymentMethod?.card?.brand || ''),
        button_disabled: button?.disabled === true,
        button_text: String(button?.textContent || '').trim(),
        message: String(message?.textContent || '').trim(),
    });
}"""


@dataclass(frozen=True)
class BrowserPaymentCard:
    number: str
    cvc: str
    exp_month: int
    exp_year: int


@dataclass(frozen=True)
class BrowserBillingDetails:
    name: str
    email: str
    phone: str
    line1: str
    line2: str
    city: str
    state: str
    postal_code: str
    country: str


@dataclass(frozen=True)
class BrowserPaymentMethodResult:
    personal_account_id: str
    payment_method_id: str
    last4: str
    brand: str


PAYMENT_METHOD_CHECKOUT_SCRIPT = CREATE_PLUS_CHECKOUT_SCRIPT


def bind_personal_payment_card(
    page: Any,
    *,
    expected_personal_account_id: str,
    card: BrowserPaymentCard,
    billing: BrowserBillingDetails,
    timeout_s: int = 120,
    http_trace_emitter: PaymentHttpTraceEmitter | None = None,
) -> BrowserPaymentMethodResult:
    _validate_input(card=card, billing=billing)
    remove_http_trace = _install_payment_http_trace(
        page,
        emitter=http_trace_emitter,
    )
    try:
        checkout_url = _open_payment_method_checkout(
            page,
            expected_personal_account_id=expected_personal_account_id,
        )
        return _bind_personal_payment_card_on_page(
            page,
            expected_personal_account_id=expected_personal_account_id,
            card=card,
            billing=billing,
            checkout_url=checkout_url,
            timeout_s=timeout_s,
        )
    finally:
        remove_http_trace()


def bind_personal_payment_cards(
    page: Any,
    *,
    expected_personal_account_id: str,
    cards: Sequence[tuple[BrowserPaymentCard, BrowserBillingDetails]] | None = None,
    card_provider: PaymentMethodCardProvider | None = None,
    max_attempts: int = 3,
    timeout_s: int = 120,
    http_trace_emitter: PaymentHttpTraceEmitter | None = None,
    on_success: PaymentMethodSuccessCallback | None = None,
    on_failure: PaymentMethodFailureCallback | None = None,
) -> list[BrowserPaymentMethodResult]:
    """Bind multiple cards in one authenticated browser and checkout page.

    The browser, hosted Checkout URL, Stripe.js page, and SetupIntent are
    reused across the batch. Stripe keeps a declined SetupIntent in
    ``requires_payment_method`` so the next card can be confirmed against the
    same client secret. A successful confirmation ends the batch immediately.
    """
    pairs = list(cards or [])
    if not pairs and card_provider is None:
        raise BrowserPersonalPaymentMethodError("payment_method_batch_empty")
    max_attempts = max(1, int(max_attempts or 1))
    remove_http_trace = _install_payment_http_trace(page, emitter=http_trace_emitter)
    try:
        checkout_url = _open_payment_method_checkout(
            page,
            expected_personal_account_id=expected_personal_account_id,
        )
        results: list[BrowserPaymentMethodResult] = []
        for index in range(1, max_attempts + 1):
            if card_provider is not None:
                card, billing = card_provider(index)
            elif index <= len(pairs):
                card, billing = pairs[index - 1]
            else:
                break
            _validate_input(card=card, billing=billing)
            if index > 1:
                page.evaluate(
                    f"{_MAIN_WORLD_PREFIX}() => {{ window.__personalPaymentMethodBind = null; }}"
                )
            try:
                result = _bind_personal_payment_card_on_page(
                    page,
                    expected_personal_account_id=expected_personal_account_id,
                    card=card,
                    billing=billing,
                    checkout_url=checkout_url,
                    timeout_s=timeout_s,
                    initialize_form=index == 1,
                )
            except BrowserPaymentMethodConfirmError as exc:
                if on_failure is not None:
                    on_failure(page, index, exc)
                has_next = index < max_attempts and (
                    card_provider is not None or index < len(pairs)
                )
                if not has_next:
                    raise
                time.sleep(PAYMENT_METHOD_CARD_RETRY_DELAY_S)
                continue
            results.append(result)
            if on_success is not None:
                on_success(page, index, result)
            break
        return results
    finally:
        remove_http_trace()


def _open_payment_method_checkout(page: Any, *, expected_personal_account_id: str) -> str:
    checkout = None
    for attempt in range(1, PAYMENT_METHOD_CHECKOUT_RETRY_ATTEMPTS + 1):
        try:
            checkout = create_plus_checkout_with_script(
                page,
                expected_account_id=str(expected_personal_account_id or "").strip(),
            )
            break
        except Exception as exc:
            retryable = _is_retryable_checkout_error(exc)
            if not retryable or attempt >= PAYMENT_METHOD_CHECKOUT_RETRY_ATTEMPTS:
                raise
            time.sleep(PAYMENT_METHOD_CHECKOUT_RETRY_DELAY_S * attempt)
    checkout_url = _validated_checkout_url(checkout)
    page.goto(checkout_url, wait_until="load", timeout=120_000)
    return checkout_url


def _is_retryable_checkout_error(exc: BaseException) -> bool:
    text = " ".join(str(exc or "").split()).casefold()
    return any(
        marker in text
        for marker in (
            "-> 429",
            "-> 503",
            "http 429",
            "http 503",
            "reached concurrency limit",
            "too many requests",
            "service unavailable",
        )
    )


def _bind_personal_payment_card_on_page(
    page: Any,
    *,
    expected_personal_account_id: str,
    card: BrowserPaymentCard,
    billing: BrowserBillingDetails,
    checkout_url: str,
    timeout_s: int,
    initialize_form: bool = True,
) -> BrowserPaymentMethodResult:
    if initialize_form:
        _run_payment_method_form_script(page)
        if not _wait_for_main_world_condition(
            page,
            _PAYMENT_METHOD_FORM_READY_EXPRESSION,
            timeout_ms=30_000,
        ):
            raise BrowserPersonalPaymentMethodError("payment_method_form_ready_timeout")
    _fill_payment_method_form(page, billing=billing)
    _fill_stripe_card_frame(page, card=card, timeout_s=30)
    submitted = page.evaluate(
        f"{_MAIN_WORLD_PREFIX}() => {{"
        " const button = document.getElementById('__card_submit__');"
        " if (!button || button.disabled) return false;"
        " button.click();"
        " return true;"
        " }"
    )
    if submitted is not True:
        raise BrowserPersonalPaymentMethodError("payment_method_submit_unavailable")
    payload = _wait_for_payment_method_form_result(page, timeout_s=timeout_s)
    result = BrowserPaymentMethodResult(
        personal_account_id=str(expected_personal_account_id or "").strip(),
        payment_method_id=str(payload.get("payment_method_id") or ""),
        last4=str(payload.get("last4") or ""),
        brand=str(payload.get("brand") or ""),
    )
    if not result.payment_method_id.startswith("pm_"):
        raise BrowserPersonalPaymentMethodError("payment method result has invalid id")
    if result.last4 != card.number[-4:]:
        raise BrowserPersonalPaymentMethodError("payment method result last4 mismatch")
    return result


def _run_payment_method_form_script(page: Any) -> None:
    script = PAYMENT_METHOD_FORM_SCRIPT.strip()
    if not script.startswith("(async () => {") or not script.endswith("})();"):
        raise BrowserPersonalPaymentMethodError("payment_method_form_script_invalid")
    expression = f"{_MAIN_WORLD_PREFIX}async () => {{ return await {script[:-1]}; }}"
    page.evaluate(expression)


def _fill_payment_method_form(page: Any, *, billing: BrowserBillingDetails) -> None:
    fields = {
        "#__card_name__": billing.name.strip(),
        "#__billing_email__": billing.email.strip(),
        "#__billing_phone__": billing.phone.strip(),
        "#__billing_line1__": billing.line1.strip(),
        "#__billing_line2__": billing.line2.strip(),
        "#__billing_city__": billing.city.strip(),
        "#__billing_state__": billing.state.strip(),
        "#__billing_postal_code__": billing.postal_code.strip(),
        "#__billing_country__": billing.country.strip().upper(),
    }
    for selector, value in fields.items():
        locator = page.locator(selector)
        locator.wait_for(state="visible", timeout=15_000)
        locator.fill(value)


def _wait_for_payment_method_form_result(page: Any, *, timeout_s: int) -> dict[str, Any]:
    deadline = time.monotonic() + max(1, int(timeout_s))
    while True:
        raw_payload = page.evaluate(
            f"{_MAIN_WORLD_PREFIX}{_PAYMENT_METHOD_FORM_RESULT_EXPRESSION}"
        )
        try:
            payload = json.loads(str(raw_payload or ""))
        except (TypeError, ValueError) as exc:
            raise BrowserPersonalPaymentMethodError(
                "payment_method_form_result_invalid"
            ) from exc
        if not isinstance(payload, dict):
            raise BrowserPersonalPaymentMethodError("payment_method_form_result_invalid")
        if payload.get("ok") is True:
            return payload
        message = str(payload.get("message") or "").strip()
        if payload.get("button_disabled") is False and message:
            raise BrowserPaymentMethodConfirmError(
                "payment_method_confirm_failed",
                message,
            )
        if time.monotonic() >= deadline:
            raise BrowserPaymentMethodConfirmError(
                "payment_method_stripe_timeout",
                message,
            )
        time.sleep(0.1)


def _install_payment_http_trace(
    page: Any,
    *,
    emitter: PaymentHttpTraceEmitter | None,
) -> Callable[[], None]:
    counts = {"stripe_confirm": 0, "payment_method_default": 0}
    statuses: dict[str, list[int]] = {
        "stripe_confirm": [],
        "payment_method_default": [],
    }

    def emit(event_type: str, data: dict[str, Any], level: str = "INFO") -> None:
        logger.log(
            logging.WARNING if level == "WARN" else logging.INFO,
            "%s %s",
            event_type,
            json.dumps(data, sort_keys=True),
        )
        if emitter is None:
            return
        try:
            emitter(event_type, data, level)
        except Exception:
            logger.exception("payment_method.http.trace_emit_failed")

    def on_request(request: Any) -> None:
        target = _payment_http_trace_target(
            method=str(getattr(request, "method", "") or ""),
            url=str(getattr(request, "url", "") or ""),
        )
        if target is None:
            return
        counts[target["operation"]] += 1
        request_body = getattr(request, "post_data", "")
        if callable(request_body):
            request_body = request_body()
        emit(
            "payment_method.http.request",
            {**target, "request_body": str(request_body or "")},
        )

    def on_response(response: Any) -> None:
        request = getattr(response, "request", None)
        target = _payment_http_trace_target(
            method=str(getattr(request, "method", "") or ""),
            url=str(getattr(response, "url", "") or ""),
        )
        if target is None:
            return
        status = int(getattr(response, "status", 0) or 0)
        statuses[target["operation"]].append(status)
        response_body = ""
        response_body_error = ""
        response_text = getattr(response, "text", None)
        if callable(response_text):
            try:
                response_body = str(response_text() or "")
            except Exception as exc:
                response_body_error = f"{type(exc).__name__}: {exc}"
        emit(
            "payment_method.http.response",
            {
                **target,
                "status": status,
                "response_body": response_body,
                **({"response_body_error": response_body_error} if response_body_error else {}),
            },
            "WARN" if status >= 400 else "INFO",
        )

    installed = callable(getattr(page, "on", None))
    if installed:
        page.on("request", on_request)
        page.on("response", on_response)

    def remove() -> None:
        if installed and callable(getattr(page, "remove_listener", None)):
            page.remove_listener("request", on_request)
            page.remove_listener("response", on_response)
        emit(
            "payment_method.http.summary",
            {
                "stripe_confirm_request_count": counts["stripe_confirm"],
                "stripe_confirm_response_statuses": statuses["stripe_confirm"],
                "payment_method_default_request_count": counts["payment_method_default"],
                "payment_method_default_response_statuses": statuses["payment_method_default"],
            },
        )

    return remove


def _payment_http_trace_target(*, method: str, url: str) -> dict[str, str] | None:
    if method.upper() != "POST":
        return None
    parsed = urlparse(url)
    stripe_match = re.fullmatch(
        r"/v1/setup_intents/(seti_[A-Za-z0-9_-]+)/confirm",
        parsed.path,
    )
    if parsed.netloc == "api.stripe.com" and stripe_match:
        return {
            "method": "POST",
            "operation": "stripe_confirm",
            "endpoint": "https://api.stripe.com/v1/setup_intents/{SETUP_INTENT_ID}/confirm",
            "setup_intent_id": stripe_match.group(1),
        }
    if parsed.path == "/backend-api/payments/payment_method/default":
        return {
            "method": "POST",
            "operation": "payment_method_default",
            "endpoint": "/backend-api/payments/payment_method/default",
        }
    return None


_STRIPE_CONFIRM_DIAGNOSTIC_KEYS = (
    "error_type",
    "decline_code",
    "param",
    "doc_url",
    "request_id",
    "request_log_url",
    "advice_code",
    "network_advice_code",
    "network_decline_code",
    "setup_intent_id",
    "setup_intent_status",
    "payment_method_id",
    "charge_id",
)




def _sanitize_stripe_confirm_diagnostics(source: Any) -> dict[str, str]:
    if not isinstance(source, dict):
        return {}
    diagnostics: dict[str, str] = {}
    for key in _STRIPE_CONFIRM_DIAGNOSTIC_KEYS:
        value = str(source.get(key) or "").strip()
        if value:
            diagnostics[key] = value[:1000]
    return diagnostics




def _wait_for_main_world_condition(
    page: Any,
    expression: str,
    *,
    timeout_ms: int,
) -> bool:
    deadline = time.monotonic() + (max(1, int(timeout_ms)) / 1000)
    while True:
        try:
            if page.evaluate(f"{_MAIN_WORLD_PREFIX}{expression}") is True:
                return True
        except Exception:
            pass
        if time.monotonic() >= deadline:
            return False
        time.sleep(0.1)




def _validated_checkout_url(payload: Any) -> str:
    if not isinstance(payload, dict):
        raise BrowserPersonalPaymentMethodError("payment method checkout result is invalid")
    checkout_session_id = str(payload.get("checkout_session_id") or "").strip()
    processor_entity = str(payload.get("processor_entity") or "").strip()
    checkout_url = str(payload.get("checkout_url") or "").strip()
    if not checkout_session_id or "/" in checkout_session_id:
        raise BrowserPersonalPaymentMethodError("payment method hosted checkout session is invalid")
    if not re.fullmatch(r"[A-Za-z0-9_]+", processor_entity):
        raise BrowserPersonalPaymentMethodError(
            "payment method checkout processor entity is invalid"
        )
    parsed = urlparse(checkout_url)
    expected_path = f"/checkout/{processor_entity}/{checkout_session_id}"
    if (
        parsed.scheme != "https"
        or parsed.hostname != "chatgpt.com"
        or parsed.port is not None
        or parsed.path != expected_path
        or parsed.params
        or parsed.query
        or parsed.fragment
    ):
        raise BrowserPersonalPaymentMethodError("payment method checkout URL is invalid")
    return checkout_url


def _fill_stripe_card_frame(
    page: Any,
    *,
    card: BrowserPaymentCard,
    timeout_s: int,
) -> None:
    deadline = time.monotonic() + max(1, int(timeout_s))
    frame = None
    while time.monotonic() < deadline:
        for candidate in list(page.frames):
            if _frame_has_selector(candidate, 'input[name="cardnumber"]'):
                frame = candidate
                break
        if frame is not None:
            break
        time.sleep(0.1)
    if frame is None:
        raise BrowserPersonalPaymentMethodError("stripe card frame not found")

    _fill_frame_input(frame, 'input[name="cardnumber"]', card.number)
    _fill_frame_input(
        frame,
        'input[name="exp-date"]',
        f"{card.exp_month:02d}{card.exp_year % 100:02d}",
    )
    _fill_frame_input(frame, 'input[name="cvc"]', card.cvc)


def _frame_has_selector(frame: Any, selector: str) -> bool:
    try:
        return int(frame.locator(selector).count()) > 0
    except Exception:
        return False


def _fill_frame_input(frame: Any, selector: str, value: str) -> None:
    locator = frame.locator(selector).first
    locator.wait_for(state="visible", timeout=15_000)
    locator.fill(value)




def _validate_input(*, card: BrowserPaymentCard, billing: BrowserBillingDetails) -> None:
    if not re.fullmatch(r"\d{12,19}", card.number):
        raise BrowserPersonalPaymentMethodError("card number is invalid")
    if not re.fullmatch(r"\d{3,4}", card.cvc):
        raise BrowserPersonalPaymentMethodError("card cvc is invalid")
    if card.exp_month < 1 or card.exp_month > 12 or card.exp_year < 2000:
        raise BrowserPersonalPaymentMethodError("card expiration is invalid")
    required = {
        "name": billing.name,
        "email": billing.email,
        "line1": billing.line1,
        "city": billing.city,
        "postal_code": billing.postal_code,
        "country": billing.country,
    }
    missing = [name for name, value in required.items() if not str(value or "").strip()]
    if missing:
        raise BrowserPersonalPaymentMethodError(
            f"billing details missing fields: {','.join(missing)}"
        )
    if not re.fullmatch(r"[A-Za-z]{2}", billing.country.strip()):
        raise BrowserPersonalPaymentMethodError("billing country must be a two-letter code")
