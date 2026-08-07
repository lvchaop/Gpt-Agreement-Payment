from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse
from uuid import uuid4


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


_STRIPE_CONSTRUCTOR_READY_EXPRESSION = "() => typeof window.Stripe === 'function'"
_STRIPE_CARD_READY_EXPRESSION = (
    "() => window.__refactorPersonalPaymentMethod?.ready === true"
)
_STRIPE_CARD_COMPLETE_EXPRESSION = (
    "() => window.__refactorPersonalPaymentMethod?.complete === true"
)
_MAIN_WORLD_PREFIX = "mw:"
_MAIN_WORLD_TASKS = "__refactorMainWorldTasks"


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


PAYMENT_METHOD_CHECKOUT_SCRIPT = r"""async ({expectedPersonalAccountId}) => {
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

    function findCheckoutId(value, seen = new WeakSet()) {
        if (typeof value === 'string') {
            return value.match(/\bcs_(?:live|test)_[A-Za-z0-9_-]+/)?.[0] || '';
        }
        if (!value || typeof value !== 'object' || seen.has(value)) return '';
        seen.add(value);
        for (const child of Object.values(value)) {
            const found = findCheckoutId(child, seen);
            if (found) return found;
        }
        return '';
    }

    const session = await request('/api/auth/session');
    const accessToken = String(session.accessToken || '');
    const personalAccountId = String(session?.account?.id || '');
    if (!accessToken) throw new Error('payment_method_missing_web_access_token');
    if (!personalAccountId) throw new Error('payment_method_missing_session_account_id');
    if (expectedPersonalAccountId && personalAccountId !== expectedPersonalAccountId) {
        throw new Error(
            `payment_method_personal_account_mismatch:` +
            `${expectedPersonalAccountId}:${personalAccountId}`
        );
    }

    const createPayload = {
        entry_point: 'all_plans_pricing_modal',
        plan_name: 'chatgptplusplan',
        billing_details: {
            country: 'US',
            currency: 'USD',
        },
        checkout_ui_mode: 'hosted',
    };
    const checkout = await request('/backend-api/payments/checkout', {
        method: 'POST',
        headers: {
            accept: 'application/json',
            authorization: `Bearer ${accessToken}`,
            'content-type': 'application/json',
            'x-openai-target-path': '/backend-api/payments/checkout',
            'x-openai-target-route': '/backend-api/payments/checkout',
        },
        body: JSON.stringify(createPayload),
    });

    const directCheckoutId = [
        checkout?.checkout_session_id,
        checkout?.session_id,
        checkout?.id,
    ].find((value) => typeof value === 'string' && /^cs_(?:live|test)_/.test(value));
    const checkoutSessionId = String(directCheckoutId || findCheckoutId(checkout) || '');
    if (!/^cs_(?:live|test)_[A-Za-z0-9_-]+$/.test(checkoutSessionId)) {
        throw new Error('payment_method_hosted_checkout_session_missing');
    }

    const responseUrl = String(
        checkout?.checkout_url || checkout?.url || checkout?.openai_checkout_url || ''
    );
    const responseUrlMatch = responseUrl.match(
        /\/checkout\/([A-Za-z0-9_]+)\/cs_(?:live|test)_[A-Za-z0-9_-]+/
    );
    const processorEntity = String(
        checkout?.processor_entity || responseUrlMatch?.[1] || 'openai_llc'
    );
    if (!/^[A-Za-z0-9_]+$/.test(processorEntity)) {
        throw new Error('payment_method_checkout_processor_entity_invalid');
    }
    const checkoutUrl = `${location.origin}/checkout/` +
        `${encodeURIComponent(processorEntity)}/${encodeURIComponent(checkoutSessionId)}`;
    return {
        personal_account_id: personalAccountId,
        checkout_session_id: checkoutSessionId,
        processor_entity: processorEntity,
        checkout_url: checkoutUrl,
    };
}"""


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
    if (typeof window.Stripe !== 'function') {
        throw new Error('payment_method_stripe_constructor_missing');
    }

    const setupIntent = await request('/backend-api/payments/payment_method', {
        method: 'POST',
        headers: {
            ...apiHeaders,
            'content-type': 'application/json',
            'x-openai-target-path': '/backend-api/payments/payment_method',
            'x-openai-target-route': '/backend-api/payments/payment_method',
        },
        body: JSON.stringify({account_id: personalAccountId}),
    });
    const clientSecret = String(setupIntent.client_secret || '');
    if (!clientSecret) throw new Error('payment_method_missing_setup_intent_client_secret');
    const setupIntentId = String(
        setupIntent.id || clientSecret.split('_secret_')[0] || ''
    );

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
        setupIntentId,
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
        return {
            ok: false,
            failure_stage: 'pre_confirm',
            error_code: 'payment_method_browser_state_missing',
            error_message: '',
        };
    }

    function objectId(value) {
        if (typeof value === 'string') return value;
        return String(value?.id || '');
    }

    function stripeDiagnostics(error, fallbackSetupIntent = null) {
        const setupIntent = error?.setup_intent || fallbackSetupIntent || {};
        const paymentMethod = error?.payment_method || setupIntent?.payment_method || {};
        const charge = error?.charge || setupIntent?.latest_charge || {};
        return {
            error_type: String(error?.type || '').slice(0, 200),
            decline_code: String(error?.decline_code || '').slice(0, 200),
            param: String(error?.param || '').slice(0, 200),
            doc_url: String(error?.doc_url || '').slice(0, 1000),
            request_id: String(error?.request_id || '').slice(0, 200),
            request_log_url: String(error?.request_log_url || '').slice(0, 1000),
            advice_code: String(error?.advice_code || '').slice(0, 200),
            network_advice_code: String(error?.network_advice_code || '').slice(0, 200),
            network_decline_code: String(error?.network_decline_code || '').slice(0, 200),
            setup_intent_id: String(setupIntent?.id || state.setupIntentId || '').slice(0, 200),
            setup_intent_status: String(setupIntent?.status || '').slice(0, 200),
            payment_method_id: objectId(paymentMethod).slice(0, 200),
            charge_id: objectId(charge).slice(0, 200),
        };
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
    let result;
    try {
        result = await Promise.race([confirmation, timeout]);
    } catch (error) {
        return {
            ok: false,
            failure_stage: 'confirm',
            error_code: String(
                error?.code || error?.name || 'payment_method_confirm_failed'
            ),
            error_message: String(error?.message || error || '').slice(0, 500),
            stripe_diagnostics: stripeDiagnostics(error),
        };
    }
    if (result?.__timeout) {
        return {
            ok: false,
            failure_stage: 'confirm',
            error_code: 'payment_method_stripe_timeout',
            error_message: '',
            stripe_diagnostics: stripeDiagnostics(null),
        };
    }
    if (result?.error) {
        return {
            ok: false,
            failure_stage: 'confirm',
            error_code: String(
                result.error.code || result.error.decline_code ||
                result.error.type || 'stripe_error'
            ),
            error_message: String(result.error.message || '').slice(0, 500),
            stripe_diagnostics: stripeDiagnostics(result.error),
        };
    }
    const setupIntent = result?.setupIntent || {};
    if (setupIntent.status !== 'succeeded') {
        return {
            ok: false,
            failure_stage: 'confirm',
            error_code: `payment_method_setup_${String(setupIntent.status || 'unknown')}`,
            error_message: '',
            stripe_diagnostics: stripeDiagnostics(null, setupIntent),
        };
    }
    const paymentMethodId = typeof setupIntent.payment_method === 'string'
        ? setupIntent.payment_method
        : String(setupIntent.payment_method?.id || '');
    if (!paymentMethodId) {
        return {
            ok: false,
            failure_stage: 'post_confirm',
            error_code: 'payment_method_id_missing',
            error_message: '',
        };
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
    const listHeaders = {
        ...state.apiHeaders,
        'x-openai-target-path': '/backend-api/payments/payment_methods',
        'x-openai-target-route': '/backend-api/payments/payment_methods',
    };
    let savedMethod = null;
    let paymentMethods = {};
    for (let attempt = 0; attempt < 8; attempt += 1) {
        paymentMethods = await request(listPath, {headers: listHeaders});
        savedMethod = (paymentMethods.payment_methods || []).find(
            (item) => item?.id === paymentMethodId,
        ) || null;
        if (savedMethod) break;
        await new Promise((resolve) => setTimeout(resolve, 500));
    }
    if (!savedMethod) {
        return {
            ok: false,
            failure_stage: 'post_confirm',
            error_code: 'payment_method_not_returned_by_list',
            error_message: '',
        };
    }

    if (paymentMethods.default_payment_method_id !== paymentMethodId) {
        await request('/backend-api/payments/payment_method/default', {
            method: 'POST',
            headers: {
                ...state.apiHeaders,
                'content-type': 'application/json',
                'x-openai-target-path': '/backend-api/payments/payment_method/default',
                'x-openai-target-route': '/backend-api/payments/payment_method/default',
            },
            body: JSON.stringify({
                account_id: state.personalAccountId,
                payment_method_id: paymentMethodId,
            }),
        });
    }
    let defaultVerified = false;
    for (let attempt = 0; attempt < 8; attempt += 1) {
        paymentMethods = await request(listPath, {headers: listHeaders});
        if (paymentMethods.default_payment_method_id === paymentMethodId) {
            defaultVerified = true;
            break;
        }
        await new Promise((resolve) => setTimeout(resolve, 500));
    }
    if (!defaultVerified) {
        return {
            ok: false,
            failure_stage: 'post_confirm',
            error_code: 'payment_method_default_not_verified',
            error_message: '',
        };
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
    checkout = page.evaluate(
        PAYMENT_METHOD_CHECKOUT_SCRIPT,
        {"expectedPersonalAccountId": str(expected_personal_account_id or "").strip()},
    )
    checkout_url = _validated_checkout_url(checkout)
    page.goto(
        checkout_url,
        wait_until="domcontentloaded",
        timeout=60_000,
    )
    _ensure_stripe_constructor(page, timeout_s=30)
    bootstrap = _evaluate_main_world_async(
        page,
        PAYMENT_METHOD_BOOTSTRAP_SCRIPT,
        {"expectedPersonalAccountId": str(expected_personal_account_id or "").strip()},
        timeout_s=60,
    )
    actual_personal_account_id = str(
        (bootstrap or {}).get("personal_account_id") or ""
    ).strip()
    if actual_personal_account_id != str(expected_personal_account_id or "").strip():
        raise BrowserPersonalPaymentMethodError(
            "payment method browser selected a different personal account"
        )
    if not _wait_for_main_world_condition(
        page,
        _STRIPE_CARD_READY_EXPRESSION,
        timeout_ms=30_000,
    ):
        raise BrowserPersonalPaymentMethodError("payment_method_stripe_card_ready_timeout")
    _fill_stripe_card_frame(page, card=card, timeout_s=30)
    if not _wait_for_main_world_condition(
        page,
        _STRIPE_CARD_COMPLETE_EXPRESSION,
        timeout_ms=30_000,
    ):
        raise BrowserPersonalPaymentMethodError(
            "payment_method_stripe_card_incomplete_timeout"
        )
    payload = _evaluate_main_world_async(
        page,
        PAYMENT_METHOD_CONFIRM_SCRIPT,
        {
            "billingDetails": _billing_payload(billing),
            "timeoutMs": max(1, int(timeout_s)) * 1000,
        },
        timeout_s=max(1, int(timeout_s)) + 30,
    )
    if not isinstance(payload, dict) or payload.get("ok") is not True:
        error_code = str((payload or {}).get("error_code") or "payment_method_unknown_error")
        error_message = str((payload or {}).get("error_message") or "")
        if str((payload or {}).get("failure_stage") or "") == "confirm":
            raise BrowserPaymentMethodConfirmError(
                error_code,
                error_message,
                diagnostics=_stripe_confirm_diagnostics(payload),
            )
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


def _stripe_confirm_diagnostics(payload: Any) -> dict[str, str]:
    source = payload.get("stripe_diagnostics") if isinstance(payload, dict) else None
    return _sanitize_stripe_confirm_diagnostics(source)


def _sanitize_stripe_confirm_diagnostics(source: Any) -> dict[str, str]:
    if not isinstance(source, dict):
        return {}
    diagnostics: dict[str, str] = {}
    for key in _STRIPE_CONFIRM_DIAGNOSTIC_KEYS:
        value = str(source.get(key) or "").strip()
        if value:
            diagnostics[key] = value[:1000]
    return diagnostics


def _ensure_stripe_constructor(page: Any, *, timeout_s: int) -> None:
    first_wait_ms = min(15_000, max(1, int(timeout_s)) * 1_000)
    if _wait_for_stripe_constructor(page, timeout_ms=first_wait_ms):
        return

    errors = ["initial_wait=timeout"]
    try:
        page.reload(wait_until="domcontentloaded", timeout=60_000)
    except Exception as exc:
        errors.append(f"reload={type(exc).__name__}:{str(exc)[:180]}")
    remaining_wait_ms = min(15_000, max(1, int(timeout_s)) * 1_000)
    if _wait_for_stripe_constructor(page, timeout_ms=remaining_wait_ms):
        return
    errors.append("reload_wait=timeout")

    detail = "; ".join(errors)
    raise BrowserPersonalPaymentMethodError(
        f"payment_method_stripe_constructor_missing: {detail}".rstrip(": ")
    )


def _wait_for_stripe_constructor(page: Any, *, timeout_ms: int) -> bool:
    return _wait_for_main_world_condition(
        page,
        _STRIPE_CONSTRUCTOR_READY_EXPRESSION,
        timeout_ms=timeout_ms,
    )


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


def _evaluate_main_world_async(
    page: Any,
    script: str,
    argument: dict[str, Any],
    *,
    timeout_s: int,
) -> Any:
    """Run an async function in Camoufox's page world and await its plain result."""
    task_id = f"task_{uuid4().hex}"
    task_id_json = json.dumps(task_id)
    argument_json = json.dumps(argument, ensure_ascii=True, separators=(",", ":"))
    start_expression = f"""{_MAIN_WORLD_PREFIX}() => {{
        const taskId = {task_id_json};
        const tasks = window.{_MAIN_WORLD_TASKS} ||
            (window.{_MAIN_WORLD_TASKS} = Object.create(null));
        tasks[taskId] = {{status: 'pending'}};
        Promise.resolve(({script})({argument_json})).then(
            (value) => {{ tasks[taskId] = {{status: 'fulfilled', value}}; }},
            (error) => {{
                tasks[taskId] = {{
                    status: 'rejected',
                    error: {{
                        name: String(error?.name || 'Error'),
                        message: String(error?.message || error || ''),
                        stack: String(error?.stack || '').slice(0, 4000),
                    }},
                }};
            }},
        );
        return taskId;
    }}"""
    started_task_id = page.evaluate(start_expression)
    if started_task_id != task_id:
        raise BrowserPersonalPaymentMethodError(
            "payment_method_main_world_task_not_started"
        )

    read_expression = f"""{_MAIN_WORLD_PREFIX}() => {{
        const taskId = {task_id_json};
        const tasks = window.{_MAIN_WORLD_TASKS};
        const task = tasks?.[taskId];
        if (!task) return JSON.stringify({{status: 'missing'}});
        if (task.status === 'pending') return JSON.stringify(task);
        const payload = JSON.stringify(task);
        delete tasks[taskId];
        return payload;
    }}"""
    deadline = time.monotonic() + max(1, int(timeout_s))
    while True:
        raw_payload = page.evaluate(read_expression)
        try:
            payload = json.loads(str(raw_payload or ""))
        except (TypeError, ValueError) as exc:
            raise BrowserPersonalPaymentMethodError(
                "payment_method_main_world_task_result_invalid"
            ) from exc
        status = str(payload.get("status") or "") if isinstance(payload, dict) else ""
        if status == "fulfilled":
            return payload.get("value")
        if status == "rejected":
            error = payload.get("error") if isinstance(payload.get("error"), dict) else {}
            error_name = str(error.get("name") or "Error")
            error_message = str(error.get("message") or "")
            detail = f"{error_name}: {error_message}".rstrip(": ")
            raise BrowserPersonalPaymentMethodError(detail)
        if status == "missing":
            raise BrowserPersonalPaymentMethodError(
                "payment_method_main_world_task_missing"
            )
        if status != "pending":
            raise BrowserPersonalPaymentMethodError(
                "payment_method_main_world_task_result_invalid"
            )
        if time.monotonic() >= deadline:
            raise BrowserPersonalPaymentMethodError(
                "payment_method_main_world_task_timeout"
            )
        time.sleep(0.1)


def _validated_checkout_url(payload: Any) -> str:
    if not isinstance(payload, dict):
        raise BrowserPersonalPaymentMethodError("payment method checkout result is invalid")
    checkout_session_id = str(payload.get("checkout_session_id") or "").strip()
    processor_entity = str(payload.get("processor_entity") or "").strip()
    checkout_url = str(payload.get("checkout_url") or "").strip()
    if not re.fullmatch(r"cs_(?:live|test)_[A-Za-z0-9_-]+", checkout_session_id):
        raise BrowserPersonalPaymentMethodError(
            "payment method hosted checkout session is invalid"
        )
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
        raise BrowserPersonalPaymentMethodError(
            "payment method checkout URL is invalid"
        )
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
