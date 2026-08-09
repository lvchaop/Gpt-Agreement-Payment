from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from refactor_app.infrastructure.db.models import (
    SpaceCredentialModel,
    SpaceMembershipModel,
    SpaceModel,
    SpacePushBindingModel,
    UserAccountModel,
)
from refactor_app.plugins.contracts import OpenAIChatGPTProvider, TokenClaims
from refactor_app.plugins.openai_chatgpt import (
    OpenAIChatGPTClientError,
    OpenAIOAuthRefreshError,
    WorkspaceMismatchError,
)

MANUAL_EXPORT_PREFIX = "manual-export-"
SKIPPED_CREDENTIAL_STATUSES = {"revoked", "error", "missing"}
REAUTHORIZATION_CREDENTIAL_STATUSES = {"invalid", "expired"}
PERMANENT_REFRESH_ERROR_CODES = {"invalid_grant", "invalid_token"}


class PersonalCodexCredentialHeartbeatError(RuntimeError):
    def __init__(self, code: str, message: str = "") -> None:
        self.code = str(code or "personal_codex_credential_heartbeat_failed")
        self.detail = str(message or "")
        rendered = self.code if not self.detail else f"{self.code}: {self.detail}"
        super().__init__(rendered)


@dataclass(frozen=True)
class PersonalCodexCredentialHeartbeatInput:
    space_credential_id: str


@dataclass(frozen=True)
class _BindingSnapshot:
    mode: str
    downstream_channel_id: str = ""


class _TokenIdentityError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.detail = message
        super().__init__(f"{code}: {message}")


class PersonalCodexCredentialHeartbeatWorkflow:
    def __init__(
        self,
        *,
        session_factory: Callable[[], Session],
        openai_provider: OpenAIChatGPTProvider,
        proxy_resolver: Callable[[str], str],
        reauthorize: Callable[[str], Any],
        repush: Callable[[str, str], Any],
    ) -> None:
        self._session_factory = session_factory
        self._openai_provider = openai_provider
        self._proxy_resolver = proxy_resolver
        self._reauthorize = reauthorize
        self._repush = repush

    def run(self, input_: PersonalCodexCredentialHeartbeatInput) -> dict[str, Any]:
        credential_id = str(input_.space_credential_id or "").strip()
        if not credential_id:
            raise PersonalCodexCredentialHeartbeatError("space_credential_id_required")

        with self._session_factory() as session:
            credential = session.get(SpaceCredentialModel, credential_id)
            if credential is None:
                raise PersonalCodexCredentialHeartbeatError("missing_space_credential")
            space = session.get(SpaceModel, credential.space_id)
            if space is None:
                raise PersonalCodexCredentialHeartbeatError("missing_space")
            user = session.get(UserAccountModel, credential.user_account_id)
            if user is None:
                raise PersonalCodexCredentialHeartbeatError("missing_user_account")

            if not _is_personal_codex_credential(credential=credential, space=space):
                return _result(
                    credential_id=credential.id,
                    action="skipped",
                    probe_status="skipped",
                    reason="not_personal_codex",
                )
            if credential.credential_status in SKIPPED_CREDENTIAL_STATUSES:
                return _result(
                    credential_id=credential.id,
                    action="skipped",
                    probe_status="skipped",
                    reason=f"credential_status_{credential.credential_status}",
                )
            if credential.credential_status in REAUTHORIZATION_CREDENTIAL_STATUSES:
                return self._complete_reauthorization(
                    session=session,
                    credential=credential,
                    space=space,
                    user=user,
                    trigger_code=f"credential_status_{credential.credential_status}",
                    trigger_message=(
                        "credential entered heartbeat with a reauthorization status: "
                        f"{credential.credential_status}"
                    ),
                )
            if credential.credential_status != "active":
                return _result(
                    credential_id=credential.id,
                    action="skipped",
                    probe_status="skipped",
                    reason=f"credential_status_{credential.credential_status}",
                )

            identity_error = self._token_identity_error(
                access_token=credential.access_token,
                space=space,
                user=user,
            )
            if identity_error is not None:
                return self._complete_reauthorization(
                    session=session,
                    credential=credential,
                    space=space,
                    user=user,
                    trigger_code=identity_error.code,
                    trigger_message=identity_error.detail,
                )

            try:
                proxy_url = str(self._proxy_resolver(user.id) or "").strip()
            except Exception as exc:
                self._raise_transient_failure(
                    session=session,
                    credential=credential,
                    code="proxy_resolution_failed",
                    message=str(exc),
                    cause=exc,
                )

            first_probe = self._probe(
                session=session,
                credential=credential,
                proxy_url=proxy_url,
            )
            if _probe_ok(first_probe):
                self._mark_probe_ok(session=session, credential=credential)
                return _result(
                    credential_id=credential.id,
                    action="ok",
                    probe_status="ok",
                )
            if not _probe_unauthorized(first_probe):
                self._raise_probe_response_failure(
                    session=session,
                    credential=credential,
                    probe=first_probe,
                )

            missing_refresh_fields = [
                name
                for name, value in (
                    ("refresh_token", credential.refresh_token),
                    ("codex_client_id", credential.codex_client_id),
                )
                if not str(value or "").strip()
            ]
            if missing_refresh_fields:
                return self._complete_reauthorization(
                    session=session,
                    credential=credential,
                    space=space,
                    user=user,
                    trigger_code="oauth_refresh_fields_missing",
                    trigger_message=f"missing={','.join(missing_refresh_fields)}",
                )

            try:
                refreshed = self._openai_provider.refresh_workspace_token(
                    refresh_token=credential.refresh_token,
                    external_workspace_id=space.external_space_id,
                    client_id=credential.codex_client_id,
                )
            except OpenAIOAuthRefreshError as exc:
                if _is_permanent_refresh_error(exc):
                    return self._complete_reauthorization(
                        session=session,
                        credential=credential,
                        space=space,
                        user=user,
                        trigger_code="oauth_refresh_rejected",
                        trigger_message=str(exc),
                    )
                self._raise_transient_failure(
                    session=session,
                    credential=credential,
                    code=f"oauth_refresh_http_{exc.http_status}",
                    message=str(exc),
                    cause=exc,
                )
            except WorkspaceMismatchError as exc:
                return self._complete_reauthorization(
                    session=session,
                    credential=credential,
                    space=space,
                    user=user,
                    trigger_code="refreshed_token_workspace_mismatch",
                    trigger_message=str(exc),
                )
            except OpenAIChatGPTClientError as exc:
                if _is_token_decode_failure(exc):
                    return self._complete_reauthorization(
                        session=session,
                        credential=credential,
                        space=space,
                        user=user,
                        trigger_code="refreshed_token_decode_failed",
                        trigger_message=str(exc),
                    )
                self._raise_transient_failure(
                    session=session,
                    credential=credential,
                    code="oauth_refresh_failed",
                    message=str(exc),
                    cause=exc,
                )
            except Exception as exc:
                self._raise_transient_failure(
                    session=session,
                    credential=credential,
                    code="oauth_refresh_failed",
                    message=str(exc),
                    cause=exc,
                )

            refreshed_identity_error = self._token_identity_error(
                access_token=refreshed.access_token,
                space=space,
                user=user,
            )
            if refreshed_identity_error is not None:
                return self._complete_reauthorization(
                    session=session,
                    credential=credential,
                    space=space,
                    user=user,
                    trigger_code=f"refreshed_{refreshed_identity_error.code}",
                    trigger_message=refreshed_identity_error.detail,
                )

            now = datetime.now(UTC)
            credential.access_token = refreshed.access_token
            if refreshed.id_token:
                credential.id_token = refreshed.id_token
            credential.refresh_token = refreshed.refresh_token
            credential.account_id = refreshed.claims.account_id
            credential.token_chatgpt_account_id = refreshed.claims.token_chatgpt_account_id
            credential.expires_at = refreshed.expires_at
            credential.last_authorized_at = now
            credential.updated_at = now
            session.commit()

            refreshed_probe = self._probe(
                session=session,
                credential=credential,
                proxy_url=proxy_url,
            )
            if _probe_ok(refreshed_probe):
                self._mark_probe_ok(session=session, credential=credential)
                return _result(
                    credential_id=credential.id,
                    action="refreshed",
                    probe_status="ok",
                )
            if _probe_unauthorized(refreshed_probe):
                return self._complete_reauthorization(
                    session=session,
                    credential=credential,
                    space=space,
                    user=user,
                    trigger_code="refreshed_probe_unauthorized",
                    trigger_message=_probe_failure_message(refreshed_probe),
                )
            self._raise_probe_response_failure(
                session=session,
                credential=credential,
                probe=refreshed_probe,
            )

        raise PersonalCodexCredentialHeartbeatError("unreachable_heartbeat_state")

    def _probe(
        self,
        *,
        session: Session,
        credential: SpaceCredentialModel,
        proxy_url: str,
    ) -> dict[str, Any]:
        try:
            result = self._openai_provider.probe_codex_responses_usage(
                access_token=credential.access_token,
                team_id="",
                proxy_url=proxy_url,
            )
        except Exception as exc:
            self._raise_transient_failure(
                session=session,
                credential=credential,
                code="codex_probe_request_failed",
                message=str(exc),
                cause=exc,
            )
        if not isinstance(result, dict):
            self._raise_transient_failure(
                session=session,
                credential=credential,
                code="codex_probe_invalid_response",
                message=f"response_type={type(result).__name__}",
            )
        return result

    def _token_identity_error(
        self,
        *,
        access_token: str,
        space: SpaceModel,
        user: UserAccountModel,
    ) -> _TokenIdentityError | None:
        try:
            claims = self._openai_provider.decode_access_token(access_token)
        except Exception as exc:
            return _TokenIdentityError("token_decode_failed", str(exc))
        return _validate_token_identity(claims=claims, space=space, user=user)

    def _complete_reauthorization(
        self,
        *,
        session: Session,
        credential: SpaceCredentialModel,
        space: SpaceModel,
        user: UserAccountModel,
        trigger_code: str,
        trigger_message: str,
    ) -> dict[str, Any]:
        credential_id = credential.id
        binding_snapshot = _binding_snapshot(session=session, credential_id=credential_id)
        membership_id = _active_membership_id(
            session=session,
            credential=credential,
        )

        now = datetime.now(UTC)
        credential.credential_status = "invalid"
        credential.last_probe_at = now
        credential.last_probe_status = "failed"
        credential.failure_code = trigger_code
        credential.failure_message = _limit_message(trigger_message)
        credential.updated_at = now
        session.commit()

        if not membership_id:
            self._record_reauthorization_failure(
                session=session,
                credential_id=credential_id,
                code="reauthorization_target_missing",
                message=(
                    "active membership not found for "
                    f"space_id={credential.space_id} user_account_id={credential.user_account_id}"
                ),
            )
            raise PersonalCodexCredentialHeartbeatError(
                "reauthorization_target_missing",
                f"space_credential_id={credential_id}",
            )

        try:
            self._reauthorize(membership_id)
        except Exception as exc:
            self._record_reauthorization_failure(
                session=session,
                credential_id=credential_id,
                code="reauthorization_failed",
                message=str(exc),
            )
            raise PersonalCodexCredentialHeartbeatError(
                "reauthorization_failed",
                str(exc),
            ) from exc

        session.expire_all()
        restored = session.get(SpaceCredentialModel, credential_id)
        if restored is None or restored.credential_status != "active":
            current_id = session.scalar(
                select(SpaceCredentialModel.id).where(
                    SpaceCredentialModel.space_id == credential.space_id,
                    SpaceCredentialModel.user_account_id == credential.user_account_id,
                )
            )
            message = (
                f"expected_credential_id={credential_id} current_credential_id={current_id or ''} "
                f"current_status={getattr(restored, 'credential_status', 'missing')}"
            )
            self._record_reauthorization_failure(
                session=session,
                credential_id=credential_id,
                code="reauthorized_credential_not_active",
                message=message,
            )
            raise PersonalCodexCredentialHeartbeatError(
                "reauthorized_credential_not_active",
                message,
            )

        restored_identity_error = self._token_identity_error(
            access_token=restored.access_token,
            space=space,
            user=user,
        )
        if restored_identity_error is not None:
            self._record_reauthorization_failure(
                session=session,
                credential_id=credential_id,
                code=f"reauthorized_{restored_identity_error.code}",
                message=restored_identity_error.detail,
            )
            raise PersonalCodexCredentialHeartbeatError(
                f"reauthorized_{restored_identity_error.code}",
                restored_identity_error.detail,
            )

        now = datetime.now(UTC)
        restored.last_probe_at = now
        restored.last_probe_status = "ok"
        restored.failure_code = ""
        restored.failure_message = ""
        restored.updated_at = now
        session.commit()

        if binding_snapshot.mode == "manual_export":
            _reset_manual_export_binding(
                session=session,
                credential_id=credential_id,
            )
            return _result(
                credential_id=credential_id,
                action="reauthorized_manual_export_reset",
                probe_status="ok",
                reason=trigger_code,
            )

        if binding_snapshot.mode == "channel":
            self._repush_original_channel(
                session=session,
                credential_id=credential_id,
                downstream_channel_id=binding_snapshot.downstream_channel_id,
            )
            return _result(
                credential_id=credential_id,
                action="reauthorized_repush",
                probe_status="ok",
                reason=trigger_code,
                repushed=True,
                downstream_channel_id=binding_snapshot.downstream_channel_id,
            )

        return _result(
            credential_id=credential_id,
            action="reauthorized",
            probe_status="ok",
            reason=trigger_code,
        )

    def _repush_original_channel(
        self,
        *,
        session: Session,
        credential_id: str,
        downstream_channel_id: str,
    ) -> None:
        binding = session.get(SpacePushBindingModel, credential_id)
        if binding is None or binding.downstream_channel_id != downstream_channel_id:
            raise PersonalCodexCredentialHeartbeatError(
                "original_push_binding_missing",
                f"space_credential_id={credential_id}",
            )
        binding.push_status = "failed"
        binding.error_code = ""
        binding.error_message = ""
        binding.updated_at = datetime.now(UTC)
        session.commit()

        try:
            self._repush(credential_id, downstream_channel_id)
        except Exception as exc:
            session.expire_all()
            binding = session.get(SpacePushBindingModel, credential_id)
            if binding is not None:
                binding.push_status = "failed"
                if not binding.error_code:
                    binding.error_code = "heartbeat_repush_failed"
                if not binding.error_message:
                    binding.error_message = _limit_message(str(exc))
                binding.updated_at = datetime.now(UTC)
                session.commit()
            raise PersonalCodexCredentialHeartbeatError(
                "heartbeat_repush_failed",
                str(exc),
            ) from exc

        session.expire_all()
        binding = session.get(SpacePushBindingModel, credential_id)
        if (
            binding is None
            or binding.downstream_channel_id != downstream_channel_id
            or binding.push_status != "pushed"
        ):
            observed = getattr(binding, "push_status", "missing")
            if binding is not None:
                binding.push_status = "failed"
                binding.error_code = "heartbeat_repush_not_pushed"
                binding.error_message = f"observed_push_status={observed}"
                binding.updated_at = datetime.now(UTC)
                session.commit()
            raise PersonalCodexCredentialHeartbeatError(
                "heartbeat_repush_not_pushed",
                f"observed_push_status={observed}",
            )

    def _mark_probe_ok(
        self,
        *,
        session: Session,
        credential: SpaceCredentialModel,
    ) -> None:
        now = datetime.now(UTC)
        credential.credential_status = "active"
        credential.last_probe_at = now
        credential.last_probe_status = "ok"
        credential.failure_code = ""
        credential.failure_message = ""
        credential.updated_at = now
        session.commit()

    def _raise_probe_response_failure(
        self,
        *,
        session: Session,
        credential: SpaceCredentialModel,
        probe: dict[str, Any],
    ) -> None:
        http_status = _probe_http_status(probe)
        code = str(probe.get("error_code") or f"codex_probe_http_{http_status or 'unknown'}")
        self._raise_transient_failure(
            session=session,
            credential=credential,
            code=code,
            message=_probe_failure_message(probe),
        )

    def _raise_transient_failure(
        self,
        *,
        session: Session,
        credential: SpaceCredentialModel,
        code: str,
        message: str,
        cause: Exception | None = None,
    ) -> None:
        now = datetime.now(UTC)
        credential.last_probe_at = now
        credential.last_probe_status = "error"
        credential.failure_code = str(code or "heartbeat_transient_failure")
        credential.failure_message = _limit_message(message)
        credential.updated_at = now
        session.commit()
        error = PersonalCodexCredentialHeartbeatError(credential.failure_code, message)
        if cause is not None:
            raise error from cause
        raise error

    @staticmethod
    def _record_reauthorization_failure(
        *,
        session: Session,
        credential_id: str,
        code: str,
        message: str,
    ) -> None:
        session.expire_all()
        credential = session.get(SpaceCredentialModel, credential_id)
        if credential is None:
            return
        now = datetime.now(UTC)
        credential.credential_status = "invalid"
        credential.last_probe_at = now
        credential.last_probe_status = "failed"
        credential.failure_code = code
        credential.failure_message = _limit_message(message)
        credential.updated_at = now
        session.commit()


def _is_personal_codex_credential(
    *,
    credential: SpaceCredentialModel,
    space: SpaceModel,
) -> bool:
    return bool(
        space.provider == "openai_chatgpt"
        and space.space_type == "personal"
        and space.auth_mode == "codex_oauth"
        and space.credential_type == "personal_account"
        and space.plan_type == "plus"
        and credential.auth_mode == "codex_oauth"
    )


def _validate_token_identity(
    *,
    claims: TokenClaims,
    space: SpaceModel,
    user: UserAccountModel,
) -> _TokenIdentityError | None:
    expected_workspace_id = str(space.external_space_id or "").strip()
    actual_workspace_id = str(claims.token_chatgpt_account_id or "").strip()
    if actual_workspace_id != expected_workspace_id:
        return _TokenIdentityError(
            "token_workspace_mismatch",
            f"expected={expected_workspace_id} actual={actual_workspace_id}",
        )
    expected_user_id = str(user.openai_user_id or "").strip()
    actual_user_id = str(claims.account_id or "").strip()
    if actual_user_id != expected_user_id:
        return _TokenIdentityError(
            "token_user_mismatch",
            f"expected={expected_user_id} actual={actual_user_id}",
        )
    return None


def _active_membership_id(
    *,
    session: Session,
    credential: SpaceCredentialModel,
) -> str:
    membership_id = str(credential.space_membership_id or "").strip()
    if membership_id:
        membership = session.get(SpaceMembershipModel, membership_id)
        if (
            membership is not None
            and membership.space_id == credential.space_id
            and membership.user_account_id == credential.user_account_id
            and membership.membership_status == "active"
        ):
            return membership.id
    return str(
        session.scalar(
            select(SpaceMembershipModel.id).where(
                SpaceMembershipModel.space_id == credential.space_id,
                SpaceMembershipModel.user_account_id == credential.user_account_id,
                SpaceMembershipModel.membership_status == "active",
            )
        )
        or ""
    )


def _binding_snapshot(*, session: Session, credential_id: str) -> _BindingSnapshot:
    binding = session.get(SpacePushBindingModel, credential_id)
    if binding is None:
        return _BindingSnapshot(mode="none")
    if (
        binding.downstream_channel_id is None
        and binding.push_status == "pushed"
        and str(binding.downstream_external_id or "").startswith(MANUAL_EXPORT_PREFIX)
    ):
        return _BindingSnapshot(mode="manual_export")
    if (
        binding.downstream_channel_id
        and binding.push_status in {"pushed", "failed"}
        and int(binding.pushed_count or 0) > 0
    ):
        return _BindingSnapshot(
            mode="channel",
            downstream_channel_id=str(binding.downstream_channel_id),
        )
    return _BindingSnapshot(mode="none")


def _reset_manual_export_binding(*, session: Session, credential_id: str) -> None:
    binding = session.get(SpacePushBindingModel, credential_id)
    if binding is None:
        raise PersonalCodexCredentialHeartbeatError(
            "manual_export_binding_missing",
            f"space_credential_id={credential_id}",
        )
    binding.push_status = "none"
    binding.downstream_external_id = ""
    binding.recycle_status = "none"
    binding.recycled_at = None
    binding.error_code = ""
    binding.error_message = ""
    binding.updated_at = datetime.now(UTC)
    session.commit()


def _probe_ok(probe: dict[str, Any]) -> bool:
    return str(probe.get("status") or "").strip().lower() == "ok"


def _probe_unauthorized(probe: dict[str, Any]) -> bool:
    return bool(probe.get("unauthorized")) or _probe_http_status(probe) == 401


def _probe_http_status(probe: dict[str, Any]) -> int:
    try:
        return int(probe.get("http_status") or 0)
    except (TypeError, ValueError):
        return 0


def _probe_failure_message(probe: dict[str, Any]) -> str:
    return (
        f"http_status={_probe_http_status(probe)} "
        f"error_code={str(probe.get('error_code') or '')}"
    )


def _is_permanent_refresh_error(exc: OpenAIOAuthRefreshError) -> bool:
    return (
        exc.http_status == 401
        or str(exc.error_code or "").strip().lower() in PERMANENT_REFRESH_ERROR_CODES
    )


def _is_token_decode_failure(exc: OpenAIChatGPTClientError) -> bool:
    message = str(exc)
    return message.startswith("access_token ")


def _limit_message(message: str, limit: int = 2000) -> str:
    return str(message or "")[:limit]


def _result(
    *,
    credential_id: str,
    action: str,
    probe_status: str,
    reason: str = "",
    repushed: bool = False,
    downstream_channel_id: str = "",
) -> dict[str, Any]:
    return {
        "credential_id": credential_id,
        "action": action,
        "probe_status": probe_status,
        "reason": reason,
        "repushed": repushed,
        "downstream_channel_id": downstream_channel_id,
    }
