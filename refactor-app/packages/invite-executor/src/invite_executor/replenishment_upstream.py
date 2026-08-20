from __future__ import annotations

import hashlib
import logging
import re
from collections.abc import Callable
from datetime import UTC, datetime
from tempfile import TemporaryDirectory
from threading import Lock
from time import monotonic
from typing import Any

from refactor_app.application.workflows.protocol_registration import (
    HeroSmsPhoneProviderAdapter,
)
from refactor_app.plugins.browser_runtime import managed_camoufox_context
from refactor_app.plugins.mail_external_api.client import ExternalMailApiClient
from refactor_app.plugins.openai_auth_browser import (
    BrowserAccountDeactivatedError,
    BrowserChatGPTAccountMissingError,
    BrowserEmailRegistrationConfig,
    BrowserEmailRegistrationError,
    CamoufoxEmailRegistration,
)
from refactor_app.plugins.openai_auth_protocol.codex_browser_rt import (
    DEFAULT_CODEX_CLIENT_ID,
    HERO_ADD_PHONE_INVALID_STATE,
    HERO_ADD_PHONE_OTP_TIMEOUT,
    CodexBrowserRtResult,
    RetainedBrowserPhoneOtpProvider,
    acquire_codex_rt_with_browser_login,
    acquire_codex_rt_with_existing_browser_session,
)
from refactor_app.plugins.openai_auth_protocol.config import PhoneConfig
from refactor_app.plugins.openai_chatgpt.client import (
    OpenAIChatGPTClient,
    OpenAIChatGPTClientConfig,
    decode_access_token_claims,
)

from invite_executor.proxy_pool import StaticProxyAssignment
from invite_executor.replenishment_models import (
    AccountDeactivatedProvisioningError,
    AuthorizationForbiddenProvisioningError,
    ChatGPTAccountMissingProvisioningError,
    ProvisionedCodexCredential,
    RemoteInvite,
    RemoteMember,
    SelectChannelProvisioningError,
    SpaceAdminContext,
    SpaceRemoteSnapshot,
    SpaceReplenishmentConfig,
)

logger = logging.getLogger(__name__)


class ReplenishmentUpstreamError(RuntimeError):
    pass


class StableProxyDirectory:
    def __init__(
        self,
        *,
        allocator: Callable[[int], list[StaticProxyAssignment]],
        endpoint_count: int,
    ) -> None:
        self._allocator = allocator
        self._endpoint_count = max(1, int(endpoint_count))
        self._lock = Lock()
        self._assignments: tuple[StaticProxyAssignment, ...] = ()

    def for_key(self, key: str, *, offset: int = 0) -> StaticProxyAssignment:
        normalized_key = str(key or "").strip()
        if not normalized_key:
            raise ReplenishmentUpstreamError("proxy binding key is required")
        assignments = self._load()
        ranked = sorted(
            assignments,
            key=lambda item: hashlib.sha256(
                f"{normalized_key}\0{item.endpoint_id}".encode()
            ).digest(),
            reverse=True,
        )
        return ranked[max(0, int(offset)) % len(ranked)]

    def _load(self) -> tuple[StaticProxyAssignment, ...]:
        with self._lock:
            if self._assignments:
                return self._assignments
            assignments = self._allocator(self._endpoint_count)
            if not assignments:
                raise ReplenishmentUpstreamError("stable proxy directory is empty")
            unique: dict[str, StaticProxyAssignment] = {}
            for assignment in assignments:
                if assignment.endpoint_id and assignment.proxy_url:
                    unique.setdefault(assignment.endpoint_id, assignment)
            if not unique:
                raise ReplenishmentUpstreamError("stable proxy directory has no usable endpoints")
            self._assignments = tuple(sorted(unique.values(), key=lambda item: item.endpoint_id))
            return self._assignments


class ChatGPTSpaceGateway:
    def __init__(
        self,
        *,
        chatgpt_base_url: str,
        request_timeout_s: float,
        proxy_directory: StableProxyDirectory,
    ) -> None:
        self._config = OpenAIChatGPTClientConfig(
            chatgpt_base_url=chatgpt_base_url,
            timeout_s=request_timeout_s,
        )
        self._proxy_directory = proxy_directory
        self._account_proxy_lock = Lock()
        self._account_proxy_attempts: dict[str, int] = {}

    def snapshot(self, space: SpaceReplenishmentConfig) -> SpaceRemoteSnapshot:
        admin = self._admin_context(space)
        client = OpenAIChatGPTClient(self._config)
        try:
            subscription = client.fetch_subscription(
                access_token=admin.access_token,
                account_id=space.external_space_id,
                cookie_header=admin.cookie_header,
                proxy_url=admin.proxy_url,
            )
            members_payload = client.list_account_users(
                access_token=admin.access_token,
                account_id=space.external_space_id,
                cookie_header=admin.cookie_header,
                page_size=100,
                proxy_url=admin.proxy_url,
            )
            invites_payload = client.list_account_invites(
                access_token=admin.access_token,
                account_id=space.external_space_id,
                cookie_header=admin.cookie_header,
                page_size=100,
                proxy_url=admin.proxy_url,
            )
        finally:
            client.close()
        return SpaceRemoteSnapshot(
            external_space_id=space.external_space_id,
            members=_parse_remote_members(members_payload),
            invites=_parse_remote_invites(invites_payload),
            admin=admin,
            seat_limit=_subscription_seat_limit(subscription),
        )

    def list_members(
        self,
        space: SpaceReplenishmentConfig,
        admin: SpaceAdminContext,
    ) -> tuple[RemoteMember, ...]:
        client = OpenAIChatGPTClient(self._config)
        try:
            payload = client.list_account_users(
                access_token=admin.access_token,
                account_id=space.external_space_id,
                cookie_header=admin.cookie_header,
                page_size=100,
                proxy_url=admin.proxy_url,
            )
        finally:
            client.close()
        return _parse_remote_members(payload)

    def remove_member(
        self,
        space: SpaceReplenishmentConfig,
        admin: SpaceAdminContext,
        *,
        user_id: str,
    ) -> None:
        normalized_user_id = _stable_user_id(user_id)
        if not normalized_user_id:
            raise ReplenishmentUpstreamError("remote user ID is required for removal")
        client = OpenAIChatGPTClient(self._config)
        try:
            client.remove_account_user(
                access_token=admin.access_token,
                account_id=space.external_space_id,
                user_id=normalized_user_id,
                cookie_header=admin.cookie_header,
                proxy_url=admin.proxy_url,
            )
        finally:
            client.close()

    def revoke_invite(
        self,
        space: SpaceReplenishmentConfig,
        admin: SpaceAdminContext,
        *,
        email: str,
    ) -> None:
        client = OpenAIChatGPTClient(self._config)
        try:
            client.revoke_account_invite(
                access_token=admin.access_token,
                account_id=space.external_space_id,
                email=email,
                cookie_header=admin.cookie_header,
                proxy_url=admin.proxy_url,
            )
        finally:
            client.close()

    def account_proxy(self, email: str) -> StaticProxyAssignment:
        normalized_email = email.strip().casefold()
        key = f"account:{normalized_email}"
        with self._account_proxy_lock:
            attempt = self._account_proxy_attempts.get(key, 0)
            self._account_proxy_attempts[key] = attempt + 1
        assignment = self._proxy_directory.for_key(key, offset=attempt)
        if attempt:
            logger.warning(
                "replenishment account proxy rotated: email=%s attempt=%s endpoint_id=%s",
                normalized_email,
                attempt + 1,
                assignment.endpoint_id,
            )
        return assignment

    def _admin_context(self, space: SpaceReplenishmentConfig) -> SpaceAdminContext:
        explicit_proxy = space.admin_proxy_url.get_secret_value()
        admin_binding_key = space.admin_key or space.admin_user_id or space.external_space_id
        assignment = self._proxy_directory.for_key(f"admin:{admin_binding_key}")
        proxy_url = explicit_proxy or assignment.proxy_url
        configured_access_token = space.admin_access_token.get_secret_value()
        cookie_header = space.admin_cookie_header.get_secret_value()
        access_token = configured_access_token

        client = OpenAIChatGPTClient(self._config)
        try:
            if cookie_header:
                try:
                    access_token = client.exchange_workspace_session_access_token(
                        chatgpt_account_id=space.external_space_id,
                        cookie_header=cookie_header,
                        proxy_url=proxy_url,
                    )
                except Exception:
                    if not configured_access_token:
                        raise
        finally:
            client.close()
        if not access_token:
            raise ReplenishmentUpstreamError(
                f"space admin access token is unavailable: {space.external_space_id}"
            )
        admin_user_id = _stable_user_id(space.admin_user_id)
        if "." in access_token:
            claims = decode_access_token_claims(access_token)
            if claims.token_chatgpt_account_id != space.external_space_id:
                raise ReplenishmentUpstreamError(
                    "configured admin access token belongs to another space: "
                    f"expected={space.external_space_id} "
                    f"actual={claims.token_chatgpt_account_id}"
                )
            if not admin_user_id:
                admin_user_id = _stable_user_id(claims.account_id)
        return SpaceAdminContext(
            access_token=access_token,
            cookie_header=cookie_header,
            proxy_url=proxy_url,
            admin_user_id=admin_user_id,
        )


class FixedEmailBrowserMailbox:
    """Expose one already-invited mailbox to the browser login workflow."""

    def __init__(self, *, mail_client: ExternalMailApiClient, email: str) -> None:
        self._mail_client = mail_client
        self._email = str(email or "").strip()

    def create_mailbox(self) -> str:
        if not self._email:
            raise ReplenishmentUpstreamError("browser mailbox email is required")
        return self._email

    def ensure_domain_email(self, *, email: str) -> dict[str, Any]:
        """Forward the domain-mailbox preparation hook used by shared auth flows."""
        return self._mail_client.ensure_domain_email(email=email)

    def wait_for_otp(
        self,
        _email: str,
        timeout: int = 180,
        issued_after: float | None = None,
        max_polls: int | None = None,
    ) -> str:
        otp = self._mail_client.wait_for_otp_by_email(
            email=self._email,
            timeout_s=timeout,
            issued_after=issued_after,
            max_polls=max_polls,
            code_source="content",
        )
        return str(otp.code or "").strip()


def _run_browser_login_retries(
    *,
    run_browser_login: Callable[[], CodexBrowserRtResult],
    initial_failure_code: str,
) -> CodexBrowserRtResult:
    invalid_state_retry_used = False
    phone_timeout_retry_used = initial_failure_code == HERO_ADD_PHONE_OTP_TIMEOUT
    while True:
        result = run_browser_login()
        if (
            result.failure_code == HERO_ADD_PHONE_INVALID_STATE
            and not invalid_state_retry_used
        ):
            invalid_state_retry_used = True
            continue
        if result.failure_code == HERO_ADD_PHONE_OTP_TIMEOUT and not phone_timeout_retry_used:
            phone_timeout_retry_used = True
            logger.warning(
                "replenishment phone OTP timed out; "
                "retrying authorization with a new number"
            )
            continue
        return result


class BrowserCodexCredentialProvisioner:
    def __init__(
        self,
        *,
        mail_client: ExternalMailApiClient,
        browser_headless: bool,
        browser_otp_timeout_s: int,
        codex_timeout_s: int,
        grizzly_sms_api_key: str,
        grizzly_sms_base_url: str,
        grizzly_sms_service: str,
        grizzly_sms_country: str,
        grizzly_sms_max_price: str,
        grizzly_sms_max_number_attempts: int,
        grizzly_sms_request_timeout_s: int,
        grizzly_sms_otp_timeout_s: int,
        grizzly_sms_poll_interval_s: float,
    ) -> None:
        self._mail_client = mail_client
        self._browser_headless = bool(browser_headless)
        self._browser_otp_timeout_s = max(1, int(browser_otp_timeout_s))
        self._codex_timeout_s = max(1, int(codex_timeout_s))
        api_key = str(grizzly_sms_api_key or "").strip()
        self._phone_provider = (
            HeroSmsPhoneProviderAdapter(
                PhoneConfig(
                    enabled=True,
                    provider="hero_sms",
                    base_url=str(grizzly_sms_base_url or "").strip(),
                    api_key_env="INVITE_EXECUTOR_AUTO_REPLENISH_GRIZZLY_SMS_API_KEY",
                    country=str(grizzly_sms_country or "").strip(),
                    countries=[str(grizzly_sms_country or "").strip()],
                    service=str(grizzly_sms_service or "").strip(),
                    maxPrice=str(grizzly_sms_max_price or "").strip(),
                    max_number_attempts=max(1, int(grizzly_sms_max_number_attempts)),
                    request_timeout_s=max(1, int(grizzly_sms_request_timeout_s)),
                    otp_timeout_s=max(1, int(grizzly_sms_otp_timeout_s)),
                    otp_poll_interval_s=max(0.1, float(grizzly_sms_poll_interval_s)),
                ),
                api_key=api_key,
                event_callback=self._phone_event,
            )
            if api_key
            else None
        )

    def prepare(self) -> None:
        with TemporaryDirectory(prefix="invite_executor_browser_") as profile_dir:
            with managed_camoufox_context(
                flow="invite-executor-runtime-prepare",
                headless=True,
                persistent_context=True,
                user_data_dir=profile_dir,
            ) as context:
                if not context.pages:
                    raise ReplenishmentUpstreamError(
                        "fingerprint browser persistent context opened without an initial page"
                    )
                context.pages[0].title()
        logger.info("Camoufox browser runtime ready")

    def close(self) -> None:
        if self._phone_provider is not None:
            self._phone_provider.close()

    def provision(
        self,
        *,
        space: SpaceReplenishmentConfig,
        email: str,
        proxy_assignment: StaticProxyAssignment,
    ) -> ProvisionedCodexCredential:
        return self._provision(
            space=space,
            email=email,
            proxy_assignment=proxy_assignment,
            passwordless_for_existing_login=False,
        )

    def reauthorize(
        self,
        *,
        space: SpaceReplenishmentConfig,
        email: str,
        proxy_assignment: StaticProxyAssignment,
    ) -> ProvisionedCodexCredential:
        return self._provision(
            space=space,
            email=email,
            proxy_assignment=proxy_assignment,
            passwordless_for_existing_login=True,
        )

    def _provision(
        self,
        *,
        space: SpaceReplenishmentConfig,
        email: str,
        proxy_assignment: StaticProxyAssignment,
        passwordless_for_existing_login: bool,
    ) -> ProvisionedCodexCredential:
        normalized_email = str(email or "").strip()
        if not normalized_email or "@" not in normalized_email:
            raise ReplenishmentUpstreamError("a valid invitation email is required")

        started_at = monotonic()
        logger.info(
            "replenishment browser auth started: external_space_id=%s email=%s",
            space.external_space_id,
            normalized_email,
        )
        browser = CamoufoxEmailRegistration(
            BrowserEmailRegistrationConfig(
                proxy_url=proxy_assignment.proxy_url,
                headless=self._browser_headless,
                otp_timeout_s=self._browser_otp_timeout_s,
                work_id=f"space-{space.external_space_id}-{normalized_email}",
                capture_artifacts=True,
            ),
            event_callback=self._browser_event,
        )
        try:
            mailbox = FixedEmailBrowserMailbox(
                mail_client=self._mail_client,
                email=normalized_email,
            )
            session = (
                browser.authenticate_passwordless(mailbox)
                if passwordless_for_existing_login
                else browser.run(mailbox)
            )
        except BrowserAccountDeactivatedError as exc:
            raise AccountDeactivatedProvisioningError(normalized_email) from exc
        except BrowserChatGPTAccountMissingError as exc:
            raise ChatGPTAccountMissingProvisioningError(normalized_email) from exc
        except BrowserEmailRegistrationError as exc:
            if _contains_http_status(str(exc), 403):
                raise AuthorizationForbiddenProvisioningError(normalized_email) from exc
            raise
        web_claims = decode_access_token_claims(session.access_token)
        chatgpt_user_id = _stable_user_id(web_claims.account_id)
        if not chatgpt_user_id:
            raise ReplenishmentUpstreamError("browser web session is missing chatgpt_user_id")

        phone_provider = (
            RetainedBrowserPhoneOtpProvider(self._phone_provider)
            if self._phone_provider is not None
            else None
        )
        oauth = acquire_codex_rt_with_existing_browser_session(
            cookie_header=session.cookie_header,
            auth_cookie_header=session.auth_cookie_header,
            proxy=proxy_assignment.proxy_url,
            account_email=normalized_email,
            target_workspace_id=space.external_space_id,
            target_workspace_name=space.name,
            phone_provider=phone_provider,
            timeout_s=min(45, self._codex_timeout_s),
            capture_diagnostics=False,
            headless=self._browser_headless,
        )
        if not oauth.ok:
            logger.warning(
                "replenishment Codex fast path failed; using browser login: "
                "external_space_id=%s email=%s failure_code=%s",
                space.external_space_id,
                normalized_email,
                oauth.failure_code or "unknown",
            )

            def run_browser_login():
                return acquire_codex_rt_with_browser_login(
                    email=normalized_email,
                    password="",
                    mail_provider=self._mail_client,
                    proxy=proxy_assignment.proxy_url,
                    target_workspace_id=space.external_space_id,
                    target_workspace_name=space.name,
                    phone_provider=phone_provider,
                    cookie_header=session.cookie_header,
                    auth_cookie_header=session.auth_cookie_header,
                    timeout_s=self._codex_timeout_s,
                    headless=self._browser_headless,
                )

            oauth = _run_browser_login_retries(
                run_browser_login=run_browser_login,
                initial_failure_code=oauth.failure_code,
            )
        if oauth.failure_code == "phone_otp_select_channel":
            raise SelectChannelProvisioningError(
                email=normalized_email,
                chatgpt_user_id=chatgpt_user_id,
            )
        if not oauth.ok:
            if phone_provider is not None:
                phone_provider.release_retained("replenishment_codex_authorization_failed")
            if _oauth_failed_with_status(oauth, 403):
                raise AuthorizationForbiddenProvisioningError(normalized_email)
            raise ReplenishmentUpstreamError(
                "Codex OAuth failed: "
                f"code={oauth.failure_code or 'unknown'} "
                f"message={oauth.failure_message[:500]}"
            )
        if not oauth.access_token or not oauth.refresh_token:
            raise ReplenishmentUpstreamError("Codex OAuth response is missing token fields")
        oauth_claims = decode_access_token_claims(oauth.access_token)
        if oauth_claims.token_chatgpt_account_id != space.external_space_id:
            raise ReplenishmentUpstreamError(
                "Codex OAuth token belongs to another space: "
                f"expected={space.external_space_id} "
                f"actual={oauth_claims.token_chatgpt_account_id}"
            )
        oauth_user_id = _stable_user_id(oauth_claims.account_id)
        if oauth_user_id != chatgpt_user_id:
            raise ReplenishmentUpstreamError(
                "Codex OAuth token belongs to another user: "
                f"web={chatgpt_user_id} oauth={oauth_user_id}"
            )
        logger.info(
            "replenishment Codex OAuth succeeded: external_space_id=%s email=%s "
            "elapsed_s=%.3f",
            space.external_space_id,
            normalized_email,
            monotonic() - started_at,
        )
        return ProvisionedCodexCredential(
            email=normalized_email,
            chatgpt_user_id=oauth_user_id,
            external_space_id=space.external_space_id,
            access_token=oauth.access_token,
            id_token=oauth.id_token,
            refresh_token=oauth.refresh_token,
            client_id=DEFAULT_CODEX_CLIENT_ID,
            expires_at=_token_expires_at(oauth_claims.raw),
            account_proxy_endpoint_id=proxy_assignment.endpoint_id,
        )

    @staticmethod
    def _browser_event(stage: str, data: dict[str, Any], level: str = "INFO") -> None:
        if stage not in {"browser.started", "browser.succeeded", "browser.failed"}:
            return
        message = (
            "replenishment browser event: stage=%s email=%s error=%s artifact_dir=%s"
        )
        args = (
            stage,
            str(data.get("email") or ""),
            str(data.get("error") or ""),
            str(data.get("artifact_dir") or ""),
        )
        if level == "ERROR":
            logger.error(message, *args)
        elif level == "WARN":
            logger.warning(message, *args)
        else:
            logger.info(message, *args)

    @staticmethod
    def _phone_event(stage: str, data: dict[str, Any], level: str = "INFO") -> None:
        if stage not in {
            "phone.allocate.started",
            "phone.allocate.succeeded",
            "phone.otp.wait.started",
            "phone.otp.wait.succeeded",
            "phone.otp.wait.failed",
        }:
            return
        message = "replenishment phone event: stage=%s country=%s"
        args = (stage, str(data.get("country") or ""))
        if level == "ERROR":
            logger.error(message, *args)
        elif level == "WARN":
            logger.warning(message, *args)
        else:
            logger.info(message, *args)


def _oauth_failed_with_status(result: CodexBrowserRtResult, status: int) -> bool:
    return _contains_http_status(result.failure_code, status) or _contains_http_status(
        result.failure_message,
        status,
    )


def _contains_http_status(value: str, status: int) -> bool:
    normalized = str(value or "").strip().casefold()
    if not normalized:
        return False
    code = str(int(status))
    patterns = (
        rf"oauth_token_http_{code}(?:\D|$)",
        rf"http(?:_status)?[\s_:=/-]*{code}(?:\D|$)",
        rf"status(?:_code)?[\s_:=/-]*{code}(?:\D|$)",
    )
    return any(re.search(pattern, normalized) is not None for pattern in patterns)


def _subscription_seat_limit(subscription: dict[str, Any]) -> int:
    value = subscription.get("seats_entitled", subscription.get("seatsEntitled"))
    if isinstance(value, bool):
        raise ReplenishmentUpstreamError("subscription seats_entitled must be an integer")
    try:
        seat_limit = int(value)
    except (TypeError, ValueError) as exc:
        raise ReplenishmentUpstreamError(
            f"subscription response is missing seats_entitled: {value!r}"
        ) from exc
    if seat_limit < 1:
        raise ReplenishmentUpstreamError(
            f"subscription seats_entitled must be positive: {seat_limit}"
        )
    return seat_limit


def _token_expires_at(claims: dict[str, Any]) -> datetime | None:
    value = claims.get("exp")
    if isinstance(value, bool):
        return None
    try:
        timestamp = int(value)
    except (TypeError, ValueError):
        return None
    if timestamp <= 0:
        return None
    return datetime.fromtimestamp(timestamp, tz=UTC)


def _parse_remote_members(items: list[dict]) -> tuple[RemoteMember, ...]:
    by_user_id: dict[str, RemoteMember] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        user_id = _remote_user_id(item)
        if not user_id:
            continue
        by_user_id.setdefault(
            user_id,
            RemoteMember(
                user_id=user_id,
                email=_remote_member_email(item),
                role=_remote_member_role(item),
                raw=dict(item),
            ),
        )
    return tuple(by_user_id.values())


def _parse_remote_invites(items: list[dict]) -> tuple[RemoteInvite, ...]:
    by_email: dict[str, RemoteInvite] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        email = _remote_invite_email(item)
        if not email:
            continue
        by_email.setdefault(email.casefold(), RemoteInvite(email=email, raw=dict(item)))
    return tuple(by_email.values())


def _remote_user_id(item: dict[str, Any]) -> str:
    user = item.get("user") if isinstance(item.get("user"), dict) else {}
    for value in (
        item.get("user_id"),
        item.get("id"),
        user.get("id"),
        user.get("user_id"),
        item.get("account_user_id"),
        item.get("accountUserId"),
    ):
        user_id = _stable_user_id(value)
        if user_id:
            return user_id
    return ""


def _remote_member_email(item: dict[str, Any]) -> str:
    user = item.get("user") if isinstance(item.get("user"), dict) else {}
    profile = item.get("profile") if isinstance(item.get("profile"), dict) else {}
    for value in (item.get("email"), user.get("email"), profile.get("email")):
        text = str(value or "").strip()
        if text:
            return text
    return ""


def _remote_member_role(item: dict[str, Any]) -> str:
    for key in ("role", "account_user_role", "user_role"):
        text = str(item.get(key) or "").strip().lower()
        if text:
            return text
    return ""


def _remote_invite_email(item: dict[str, Any]) -> str:
    for key in ("email", "email_address", "emailAddress", "recipient_email"):
        text = str(item.get(key) or "").strip()
        if text:
            return text
    user = item.get("user") if isinstance(item.get("user"), dict) else {}
    return str(user.get("email") or "").strip()


def _stable_user_id(value: object) -> str:
    text = str(value or "").strip()
    if "__" in text:
        text = text.split("__", 1)[0].strip()
    return text if text.startswith("user-") else ""
