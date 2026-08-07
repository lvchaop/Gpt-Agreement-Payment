from __future__ import annotations

import re
import time
from dataclasses import dataclass
from typing import Any


class BrowserPersonalPaymentMethodError(RuntimeError):
    pass


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


PAYMENT_METHOD_BOOTSTRAP_SCRIPT = r"""async ({expectedPersonalAccountId}) => {
    async function request(path, init = {}) {
        const response = await fetch(path, {
            credentials: 'include',
            cache: 'no-store',
            ...init,
        });
        const text = await response.text();
        let data = {};
        try { data = text ? JSON.parse(text) : {}; } catch (_) {}
        if (!response.ok) {
            throw new Error(
                `${init.method || 'GET'} ${path} -> ${response.status}: ` +
                text.slice(0, 500)
            );
        }
        return data;
    }

    const session = await request('/api/auth/session');
    const accessToken = String(session.accessToken || '');
    if (!accessToken) throw new Error('payment_method_missing_web_access_token');

    const accountsData = await request('/backend-api/accounts/check/v4-2023-04-27', {
        headers: {authorization: `Bearer ${accessToken}`},
    });
    let personalAccountId = '';
    for (const [key, entry] of Object.entries(accountsData.accounts || {})) {
        const account = entry?.account || entry || {};
        const structure = String(entry?.structure || account?.structure || '').toLowerCase();
        const accountId = String(account?.account_id || entry?.account_id || '');
        if ((key === 'person' || structure === 'personal') && accountId) {
            if (!expectedPersonalAccountId || accountId === expectedPersonalAccountId) {
                personalAccountId = accountId;
                break;
            }
        }
    }
    if (!personalAccountId) {
        throw new Error(`payment_method_personal_account_not_found:${expectedPersonalAccountId}`);
    }

    const apiHeaders = {
        accept: 'application/json',
        authorization: `Bearer ${accessToken}`,
        'chatgpt-account-id': personalAccountId,
    };
    const bootstrap = await request(
        `/backend-api/payments/stripe_client_bootstrap?account_id=${encodeURIComponent(personalAccountId)}`,
        {headers: apiHeaders},
    );
    const publishableKey = String(bootstrap.publishable_key || '');
    if (!publishableKey) throw new Error('payment_method_missing_stripe_publishable_key');

    const setupIntent = await request('/backend-api/payments/payment_method', {
        method: 'POST',
        headers: {...apiHeaders, 'content-type': 'application/json'},
        body: JSON.stringify({account_id: personalAccountId}),
    });
    const clientSecret = String(setupIntent.client_secret || '');
    if (!clientSecret) throw new Error('payment_method_missing_setup_intent_client_secret');

    if (typeof window.Stripe !== 'function') {
        await new Promise((resolve, reject) => {
            const script = document.createElement('script');
            script.src = 'https://js.stripe.com/basil/stripe.js';
            script.async = true;
            script.onload = resolve;
            script.onerror = () => reject(new Error('payment_method_stripe_js_load_failed'));
            document.head.appendChild(script);
        });
    }
    if (typeof window.Stripe !== 'function') {
        throw new Error('payment_method_stripe_constructor_missing');
    }

    document.getElementById('__refactor_payment_card_host__')?.remove();
    const host = document.createElement('div');
    host.id = '__refactor_payment_card_host__';
    host.style.cssText = [
        'position:fixed', 'left:12px', 'bottom:12px', 'width:460px',
        'min-height:80px', 'z-index:2147483647', 'background:#fff', 'padding:12px',
    ].join(';');
    document.body.appendChild(host);

    const stripe = window.Stripe(publishableKey);
    const elements = stripe.elements({locale: 'en'});
    const card = elements.create('card', {hidePostalCode: true});
    const state = {
        personalAccountId,
        accessToken,
        apiHeaders,
        clientSecret,
        stripe,
        card,
        ready: false,
        complete: false,
        error: '',
    };
    window.__refactorPersonalPaymentMethod = state;
    card.on('ready', () => { state.ready = true; });
    card.on('change', (event) => {
        state.complete = event?.complete === true;
        state.error = String(event?.error?.message || '');
    });
    card.mount('#__refactor_payment_card_host__');
    return {personal_account_id: personalAccountId};
}"""


PAYMENT_METHOD_CONFIRM_SCRIPT = r"""async ({billingDetails, timeoutMs}) => {
    const state = window.__refactorPersonalPaymentMethod;
    if (!state?.stripe || !state?.card || !state?.clientSecret) {
        return {ok: false, error_code: 'payment_method_browser_state_missing', error_message: ''};
    }
    const timeout = new Promise((resolve) => {
        setTimeout(() => resolve({__timeout: true}), timeoutMs);
    });
    const confirmation = state.stripe.confirmCardSetup(
        state.clientSecret,
        {
            payment_method: {
                card: state.card,
                billing_details: billingDetails,
                allow_redisplay: 'always',
            },
            set_as_default_payment_method: true,
        },
    );
    const result = await Promise.race([confirmation, timeout]);
    if (result?.__timeout) {
        return {ok: false, error_code: 'payment_method_stripe_timeout', error_message: ''};
    }
    if (result?.error) {
        return {
            ok: false,
            error_code: String(
                result.error.code || result.error.decline_code ||
                result.error.type || 'stripe_error'
            ),
            error_message: String(result.error.message || '').slice(0, 500),
        };
    }
    const setupIntent = result?.setupIntent || {};
    if (setupIntent.status !== 'succeeded') {
        return {
            ok: false,
            error_code: `payment_method_setup_${String(setupIntent.status || 'unknown')}`,
            error_message: '',
        };
    }
    const paymentMethodId = typeof setupIntent.payment_method === 'string'
        ? setupIntent.payment_method
        : String(setupIntent.payment_method?.id || '');
    if (!paymentMethodId) {
        return {ok: false, error_code: 'payment_method_id_missing', error_message: ''};
    }

    async function request(path, init = {}) {
        const response = await fetch(path, {
            credentials: 'include',
            cache: 'no-store',
            ...init,
        });
        const text = await response.text();
        let data = {};
        try { data = text ? JSON.parse(text) : {}; } catch (_) {}
        if (!response.ok) {
            throw new Error(
                `${init.method || 'GET'} ${path} -> ${response.status}: ` +
                text.slice(0, 500)
            );
        }
        return data;
    }

    const listPath = '/backend-api/payments/payment_methods?account_id=' +
        encodeURIComponent(state.personalAccountId);
    let savedMethod = null;
    let paymentMethods = {};
    for (let attempt = 0; attempt < 8; attempt += 1) {
        paymentMethods = await request(listPath, {headers: state.apiHeaders});
        savedMethod = (paymentMethods.payment_methods || []).find(
            (item) => item?.id === paymentMethodId,
        ) || null;
        if (savedMethod) break;
        await new Promise((resolve) => setTimeout(resolve, 500));
    }
    if (!savedMethod) {
        return {ok: false, error_code: 'payment_method_not_returned_by_list', error_message: ''};
    }

    if (paymentMethods.default_payment_method_id !== paymentMethodId) {
        await request('/backend-api/payments/payment_method/default', {
            method: 'POST',
            headers: {...state.apiHeaders, 'content-type': 'application/json'},
            body: JSON.stringify({
                account_id: state.personalAccountId,
                payment_method_id: paymentMethodId,
            }),
        });
    }
    let defaultVerified = false;
    for (let attempt = 0; attempt < 8; attempt += 1) {
        paymentMethods = await request(listPath, {headers: state.apiHeaders});
        if (paymentMethods.default_payment_method_id === paymentMethodId) {
            defaultVerified = true;
            break;
        }
        await new Promise((resolve) => setTimeout(resolve, 500));
    }
    if (!defaultVerified) {
        return {ok: false, error_code: 'payment_method_default_not_verified', error_message: ''};
    }
    return {
        ok: true,
        personal_account_id: state.personalAccountId,
        payment_method_id: paymentMethodId,
        last4: String(savedMethod.card?.last4 || ''),
        brand: String(savedMethod.card?.brand || ''),
    };
}"""


def bind_personal_payment_card(
    page: Any,
    *,
    expected_personal_account_id: str,
    card: BrowserPaymentCard,
    billing: BrowserBillingDetails,
    timeout_s: int = 120,
) -> BrowserPaymentMethodResult:
    _validate_input(card=card, billing=billing)
    page.goto(
        "https://chatgpt.com/",
        wait_until="domcontentloaded",
        timeout=60_000,
    )
    bootstrap = page.evaluate(
        PAYMENT_METHOD_BOOTSTRAP_SCRIPT,
        {"expectedPersonalAccountId": str(expected_personal_account_id or "").strip()},
    )
    actual_personal_account_id = str(
        (bootstrap or {}).get("personal_account_id") or ""
    ).strip()
    if actual_personal_account_id != str(expected_personal_account_id or "").strip():
        raise BrowserPersonalPaymentMethodError(
            "payment method browser selected a different personal account"
        )
    page.wait_for_function(
        "() => window.__refactorPersonalPaymentMethod?.ready === true",
        timeout=30_000,
    )
    _fill_stripe_card_frame(page, card=card, timeout_s=30)
    page.wait_for_function(
        "() => window.__refactorPersonalPaymentMethod?.complete === true",
        timeout=30_000,
    )
    payload = page.evaluate(
        PAYMENT_METHOD_CONFIRM_SCRIPT,
        {
            "billingDetails": _billing_payload(billing),
            "timeoutMs": max(1, int(timeout_s)) * 1000,
        },
    )
    if not isinstance(payload, dict) or payload.get("ok") is not True:
        error_code = str((payload or {}).get("error_code") or "payment_method_unknown_error")
        error_message = str((payload or {}).get("error_message") or "")
        raise BrowserPersonalPaymentMethodError(
            f"{error_code}: {error_message}".rstrip(": ")
        )
    result = BrowserPaymentMethodResult(
        personal_account_id=str(payload.get("personal_account_id") or ""),
        payment_method_id=str(payload.get("payment_method_id") or ""),
        last4=str(payload.get("last4") or ""),
        brand=str(payload.get("brand") or ""),
    )
    if not result.payment_method_id.startswith("pm_"):
        raise BrowserPersonalPaymentMethodError("payment method result has invalid id")
    if result.last4 != card.number[-4:]:
        raise BrowserPersonalPaymentMethodError("payment method result last4 mismatch")
    return result


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


def _billing_payload(billing: BrowserBillingDetails) -> dict[str, Any]:
    return {
        "name": billing.name.strip(),
        "email": billing.email.strip(),
        **({"phone": billing.phone.strip()} if billing.phone.strip() else {}),
        "address": {
            "line1": billing.line1.strip(),
            **({"line2": billing.line2.strip()} if billing.line2.strip() else {}),
            "city": billing.city.strip(),
            **({"state": billing.state.strip()} if billing.state.strip() else {}),
            "postal_code": billing.postal_code.strip(),
            "country": billing.country.strip().upper(),
        },
    }


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
