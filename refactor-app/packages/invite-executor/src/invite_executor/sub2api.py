from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from threading import Lock
from typing import Any

import httpx
from refactor_app.plugins.contracts import DownstreamCodexPayload
from refactor_app.plugins.downstream_common import codex_credentials_body
from refactor_app.plugins.downstream_sub2api.client import (
    build_sub2api_import_payload,
)

from invite_executor.replenishment_models import (
    ProvisionedCodexCredential,
    SpaceReplenishmentConfig,
)


class Sub2APIAdminError(RuntimeError):
    pass


SUB2API_PUSH_CONCURRENCY = 50


@dataclass(frozen=True)
class Sub2APIAccount:
    id: int
    name: str
    platform: str
    account_type: str
    status: str
    error_message: str = ""
    credentials: dict[str, Any] = field(default_factory=dict)
    extra: dict[str, Any] = field(default_factory=dict)
    created_at: str = ""
    updated_at: str = ""

    @property
    def chatgpt_account_id(self) -> str:
        return str(self.credentials.get("chatgpt_account_id") or "").strip()

    @property
    def chatgpt_user_id(self) -> str:
        return _stable_user_id(self.credentials.get("chatgpt_user_id"))

    @property
    def email(self) -> str:
        return str(self.credentials.get("email") or "").strip()

    @property
    def replacement_for_user_id(self) -> str:
        return _stable_user_id(self.extra.get("auto_replenish_replacement_for_user_id"))

    @property
    def replacement_space_id(self) -> str:
        return str(self.extra.get("auto_replenish_space_id") or "").strip()

    @property
    def error_http_status(self) -> int | None:
        match = re.search(r"(?<!\d)([1-5]\d{2})(?!\d)", self.error_message)
        return int(match.group(1)) if match else None


@dataclass(frozen=True)
class UsageSignal:
    usable: bool
    used_percent: float = 0.0
    reason: str = ""
    updated_at: datetime | None = None
    reset_at: datetime | None = None


class Sub2APIAdminClient:
    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        api_key_header: str = "x-api-key",
        request_timeout_s: float = 30.0,
        http_client: httpx.Client | None = None,
    ) -> None:
        self._accounts_url = _accounts_url(base_url)
        self._codex_import_url = f"{self._accounts_url}/import/codex-session"
        self._api_key = str(api_key or "").strip()
        self._api_key_header = str(api_key_header or "x-api-key").strip()
        if not self._api_key:
            raise Sub2APIAdminError("Sub2API API key is required")
        if not self._api_key_header:
            raise Sub2APIAdminError("Sub2API API key header is required")
        self._owns_client = http_client is None
        self._client = http_client or httpx.Client(
            timeout=httpx.Timeout(max(1.0, float(request_timeout_s))),
            trust_env=False,
        )
        self._push_priority_lock = Lock()
        self._next_push_priority = 1

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def list_openai_accounts(self, *, group_id: int) -> list[Sub2APIAccount]:
        page = 1
        page_size = 100
        accounts: list[Sub2APIAccount] = []
        while True:
            data = self._request_data(
                "GET",
                self._accounts_url,
                params={
                    "page": page,
                    "page_size": page_size,
                    "platform": "openai",
                    "type": "oauth",
                    "group": int(group_id),
                    "sort_by": "id",
                    "sort_order": "asc",
                },
            )
            items = data.get("items") if isinstance(data, dict) else None
            if not isinstance(items, list):
                raise Sub2APIAdminError("Sub2API account list response missing items")
            batch = [_parse_account(item) for item in items if isinstance(item, dict)]
            accounts.extend(batch)
            total = _as_int(data.get("total"))
            if not batch or len(batch) < page_size or (total and len(accounts) >= total):
                break
            page += 1
        return accounts

    def create_account(
        self,
        *,
        payload: dict[str, Any],
        idempotency_key: str,
    ) -> Sub2APIAccount:
        data = self._request_data(
            "POST",
            self._accounts_url,
            json=payload,
            extra_headers={"Idempotency-Key": idempotency_key},
        )
        if not isinstance(data, dict):
            raise Sub2APIAdminError("Sub2API create account response is not an object")
        return _parse_account(data)

    def push_codex_credential(
        self,
        *,
        payload: DownstreamCodexPayload,
        group_ids: tuple[int, ...],
        idempotency_key: str,
    ) -> None:
        normalized_group_ids = tuple(
            dict.fromkeys(int(group_id) for group_id in group_ids if int(group_id) > 0)
        )
        if not normalized_group_ids:
            raise Sub2APIAdminError("Sub2API push requires at least one group ID")
        body = build_sub2api_import_payload(
            payload,
            concurrency=SUB2API_PUSH_CONCURRENCY,
            group_ids=normalized_group_ids,
        )
        body["priority"] = self._take_push_priority()
        data = self._request_data(
            "POST",
            self._codex_import_url,
            json=body,
            extra_headers={
                "Authorization": f"Bearer {self._api_key}",
                "Idempotency-Key": idempotency_key,
            },
        )
        if not isinstance(data, dict):
            raise Sub2APIAdminError("Sub2API Codex import response is not an object")
        if _as_int(data.get("failed")) > 0:
            raise Sub2APIAdminError(
                f"Sub2API Codex import failed: {_import_error_message(data)[:500]}"
            )
        for item in data.get("items") or []:
            if isinstance(item, dict) and str(item.get("action") or "").lower() == "failed":
                raise Sub2APIAdminError(
                    "Sub2API Codex import failed: "
                    f"{str(item.get('message') or item)[:500]}"
                )

    def apply_codex_credential(
        self,
        *,
        account_id: int,
        payload: DownstreamCodexPayload,
        idempotency_key: str,
    ) -> Sub2APIAccount:
        if int(account_id) <= 0:
            raise Sub2APIAdminError("Sub2API account ID must be positive")
        data = self._request_data(
            "POST",
            f"{self._accounts_url}/{int(account_id)}/apply-oauth-credentials",
            json={
                "type": "oauth",
                "credentials": codex_credentials_body(payload),
            },
            extra_headers={
                "Authorization": f"Bearer {self._api_key}",
                "Idempotency-Key": idempotency_key,
            },
        )
        if not isinstance(data, dict):
            raise Sub2APIAdminError(
                "Sub2API apply OAuth credentials response is not an object"
            )
        account = _parse_account(data)
        if account.status.strip().casefold() == "error":
            raise Sub2APIAdminError(
                "Sub2API account remained in error after applying OAuth credentials: "
                f"account_id={account.id} error={account.error_message[:300]}"
            )
        return account

    def _take_push_priority(self) -> int:
        with self._push_priority_lock:
            priority = self._next_push_priority
            self._next_push_priority += 1
        return priority

    def delete_account(self, account_id: int) -> None:
        if int(account_id) <= 0:
            raise Sub2APIAdminError("Sub2API account ID must be positive")
        self._request_data("DELETE", f"{self._accounts_url}/{int(account_id)}")

    def _request_data(
        self,
        method: str,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> Any:
        headers = {
            self._api_key_header: self._api_key,
            "Accept": "application/json",
        }
        if extra_headers:
            headers.update(extra_headers)
        try:
            response = self._client.request(
                method,
                url,
                params=params,
                json=json,
                headers=headers,
            )
        except httpx.HTTPError as exc:
            raise Sub2APIAdminError(
                f"Sub2API request failed: method={method} error={type(exc).__name__}: {exc}"
            ) from exc
        try:
            body = response.json()
        except ValueError as exc:
            raise Sub2APIAdminError(
                f"Sub2API returned non-JSON response: method={method} "
                f"http_status={response.status_code}"
            ) from exc
        if response.is_error:
            raise Sub2APIAdminError(
                f"Sub2API returned HTTP {response.status_code}: {_response_message(body)[:500]}"
            )
        if not isinstance(body, dict):
            raise Sub2APIAdminError("Sub2API response must be an object")
        code = body.get("code")
        if code not in (None, 0, "0"):
            raise Sub2APIAdminError(f"Sub2API returned error: {_response_message(body)[:500]}")
        return body.get("data")


def accounts_for_space(
    accounts: list[Sub2APIAccount],
    *,
    external_space_id: str,
) -> list[Sub2APIAccount]:
    target = str(external_space_id or "").strip()
    suffix = f"_{target}"
    return [
        account
        for account in accounts
        if account.chatgpt_account_id == target
        or account.chatgpt_account_id.endswith(suffix)
    ]


def build_sub2api_codex_payload(
    *,
    space: SpaceReplenishmentConfig,
    credential: ProvisionedCodexCredential,
) -> DownstreamCodexPayload:
    return DownstreamCodexPayload(
        access_token=credential.access_token,
        id_token=credential.id_token,
        refresh_token=credential.refresh_token,
        email=credential.email,
        account_id=credential.chatgpt_user_id,
        downstream_chatgpt_account_id=(
            f"{credential.chatgpt_user_id}_{space.external_space_id}"
        ),
        token_chatgpt_account_id=space.external_space_id,
        client_id=credential.client_id,
        expires_at=credential.expires_at,
        plan_tag=space.credential_type,
        plan_type="team",
    )


def sub2api_idempotency_key(
    *,
    space_id: str,
    chatgpt_user_id: str,
    access_token: str,
) -> str:
    digest = hashlib.sha256(access_token.encode("utf-8")).hexdigest()[:24]
    raw = f"auto-replenish:{space_id}:{chatgpt_user_id}:{digest}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def resolve_usage_signal(
    account: Sub2APIAccount,
    *,
    credential_type: str,
    now: datetime | None = None,
    stale_after_s: int = 7200,
) -> UsageSignal:
    current = now or datetime.now(UTC)
    updated_at = _parse_datetime(account.extra.get("codex_usage_updated_at"))
    if updated_at is None:
        return UsageSignal(usable=False, reason="usage_updated_at_missing")
    if current - updated_at >= timedelta(seconds=max(1, int(stale_after_s))):
        return UsageSignal(
            usable=False,
            reason="usage_snapshot_stale",
            updated_at=updated_at,
        )

    if credential_type == "team_5h_weekly":
        prefix = "codex_7d"
    elif credential_type == "team_monthly":
        prefix = "codex_primary"
    else:
        return UsageSignal(usable=False, reason="unsupported_credential_type")

    used_percent = _as_float(account.extra.get(f"{prefix}_used_percent"))
    if used_percent is None:
        return UsageSignal(
            usable=False,
            reason="usage_percent_missing",
            updated_at=updated_at,
        )

    reset_at = _parse_datetime(account.extra.get(f"{prefix}_reset_at"))
    if reset_at is None:
        reset_after = _as_int(account.extra.get(f"{prefix}_reset_after_seconds"))
        if reset_after > 0:
            reset_at = updated_at + timedelta(seconds=reset_after)
    if reset_at is not None and current >= reset_at:
        return UsageSignal(
            usable=False,
            used_percent=used_percent,
            reason="usage_window_reset",
            updated_at=updated_at,
            reset_at=reset_at,
        )
    return UsageSignal(
        usable=True,
        used_percent=used_percent,
        updated_at=updated_at,
        reset_at=reset_at,
    )


def _accounts_url(base_url: str) -> str:
    normalized = str(base_url or "").strip().rstrip("/")
    if not normalized:
        raise Sub2APIAdminError("Sub2API base URL is required")
    if normalized.endswith("/api/v1/admin/accounts"):
        return normalized
    return f"{normalized}/api/v1/admin/accounts"


def _parse_account(payload: dict[str, Any]) -> Sub2APIAccount:
    account_id = _as_int(payload.get("id"))
    if account_id <= 0:
        raise Sub2APIAdminError("Sub2API account response missing account ID")
    credentials = payload.get("credentials")
    extra = payload.get("extra")
    return Sub2APIAccount(
        id=account_id,
        name=str(payload.get("name") or ""),
        platform=str(payload.get("platform") or ""),
        account_type=str(payload.get("type") or ""),
        status=str(payload.get("status") or ""),
        error_message=str(payload.get("error_message") or ""),
        credentials=dict(credentials) if isinstance(credentials, dict) else {},
        extra=dict(extra) if isinstance(extra, dict) else {},
        created_at=str(payload.get("created_at") or ""),
        updated_at=str(payload.get("updated_at") or ""),
    )


def _response_message(payload: object) -> str:
    if not isinstance(payload, dict):
        return str(payload)
    error = payload.get("error")
    if isinstance(error, dict):
        return str(error.get("message") or error.get("code") or error)
    return str(payload.get("message") or error or payload)


def _import_error_message(payload: dict[str, Any]) -> str:
    for key in ("errors", "items"):
        values = payload.get(key)
        if not isinstance(values, list):
            continue
        for item in values:
            if isinstance(item, dict):
                message = str(item.get("message") or item.get("error") or "").strip()
                if message:
                    return message
            elif item:
                return str(item)
    return f"failed={_as_int(payload.get('failed'))}"


def _stable_user_id(value: object) -> str:
    text = str(value or "").strip()
    if "__" in text:
        text = text.split("__", 1)[0].strip()
    return text if text.startswith("user-") else ""


def _as_int(value: object) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _as_float(value: object) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_datetime(value: object) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)
