from __future__ import annotations

from collections.abc import Callable
from contextlib import asynccontextmanager
from secrets import compare_digest
from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException, status
from refactor_app.plugins.mail_external_api.client import (
    ExternalMailApiClient,
    ExternalMailApiClientConfig,
)

from invite_executor.execution_gate import BatchExecutionGate
from invite_executor.executor import (
    InviteBatchAlreadyRunningError,
    InviteBatchManager,
    InviteBatchNotFoundError,
    InviteBatchTooLargeError,
)
from invite_executor.models import (
    InviteBatchRequest,
    InviteBatchView,
    SessionOtpBatchRequest,
    SessionOtpBatchView,
)
from invite_executor.proxy_pool import StaticBackboneProxyPool, StaticProxyAssignment
from invite_executor.replenishment_engine import SpaceReplenishmentEngine
from invite_executor.replenishment_models import (
    ReplenishmentRegistration,
    ReplenishmentRunView,
    ReplenishmentSpaceUpsertRequest,
    SpaceRuntimeView,
)
from invite_executor.replenishment_registry import ReplenishmentRegistry
from invite_executor.replenishment_runtime import SpaceReplenishmentManager
from invite_executor.replenishment_upstream import (
    BrowserCodexCredentialProvisioner,
    ChatGPTSpaceGateway,
    StableProxyDirectory,
)
from invite_executor.session_otp_executor import (
    SessionOtpBatchAlreadyRunningError,
    SessionOtpBatchManager,
    SessionOtpBatchNotFoundError,
    SessionOtpBatchTooLargeError,
)
from invite_executor.session_otp_transport import ExistingAsyncSessionOtpTransport
from invite_executor.settings import InviteExecutorSettings
from invite_executor.sub2api import Sub2APIAdminClient
from invite_executor.transport import ExistingAsyncInviteTransport


def create_app(
    settings: InviteExecutorSettings | None = None,
    manager: InviteBatchManager | None = None,
    otp_manager: SessionOtpBatchManager | None = None,
    replenishment_manager: SpaceReplenishmentManager | None = None,
    replenishment_proxy_allocator: (Callable[[int], list[StaticProxyAssignment]] | None) = None,
) -> FastAPI:
    resolved_settings = settings or InviteExecutorSettings()
    if manager is not None:
        execution_gate = manager.execution_gate
    elif otp_manager is not None:
        execution_gate = otp_manager.execution_gate
    else:
        execution_gate = BatchExecutionGate()
    proxy_pool = StaticBackboneProxyPool(
        gateway_host=resolved_settings.static_proxy_gateway_host,
        gateway_port=resolved_settings.static_proxy_gateway_port,
        username=resolved_settings.static_proxy_username,
        password=resolved_settings.static_proxy_password,
        country_code=resolved_settings.static_proxy_country,
    )
    resolved_manager = manager or InviteBatchManager(
        max_batch_size=resolved_settings.max_batch_size,
        default_barrier_timeout_s=resolved_settings.barrier_timeout_s,
        release_interval_ms=resolved_settings.invite_release_interval_ms,
        result_ttl_s=resolved_settings.result_ttl_s,
        transport_factory=lambda max_clients: ExistingAsyncInviteTransport(
            chatgpt_base_url=resolved_settings.chatgpt_base_url,
            request_timeout_s=resolved_settings.request_timeout_s,
            max_clients=max_clients,
            max_streams_per_proxy=resolved_settings.invites_per_proxy,
            prewarm_rounds=resolved_settings.prewarm_rounds,
            prewarm_attempts=resolved_settings.prewarm_attempts,
            prewarm_start_interval_s=(resolved_settings.prewarm_start_interval_ms / 1000.0),
            prewarm_keepalive_interval_s=(resolved_settings.prewarm_keepalive_interval_s),
            prewarm_timeout_s=resolved_settings.prewarm_timeout_s,
        ),
        proxy_allocator=proxy_pool.allocate,
        invite_proxy_count=resolved_settings.invite_proxy_count,
        execution_gate=execution_gate,
    )
    resolved_otp_manager = otp_manager or SessionOtpBatchManager(
        max_batch_size=resolved_settings.max_batch_size,
        default_barrier_timeout_s=resolved_settings.session_otp_barrier_timeout_s,
        release_window_s=resolved_settings.session_otp_release_window_s,
        result_ttl_s=resolved_settings.result_ttl_s,
        execution_gate=execution_gate,
        transport_factory=lambda max_clients: ExistingAsyncSessionOtpTransport(
            request_timeout_s=resolved_settings.request_timeout_s,
            max_clients=max_clients,
            prewarm_rounds=resolved_settings.prewarm_rounds,
            prewarm_attempts=resolved_settings.prewarm_attempts,
            prewarm_start_interval_s=(resolved_settings.prewarm_start_interval_ms / 1000.0),
            prewarm_keepalive_interval_s=(resolved_settings.prewarm_keepalive_interval_s),
            prewarm_timeout_s=resolved_settings.prewarm_timeout_s,
        ),
    )
    resolved_replenishment_manager = replenishment_manager
    if resolved_replenishment_manager is None and resolved_settings.auto_replenish_enabled:
        resolved_replenishment_manager = _build_replenishment_manager(
            settings=resolved_settings,
            proxy_pool=proxy_pool,
            proxy_allocator=replenishment_proxy_allocator,
        )

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        if resolved_replenishment_manager is not None:
            resolved_replenishment_manager.start()
        try:
            yield
        finally:
            if resolved_replenishment_manager is not None:
                resolved_replenishment_manager.stop()

    app = FastAPI(title="Pinned Batch Executor", version="0.7.0", lifespan=lifespan)
    app.state.settings = resolved_settings
    app.state.manager = resolved_manager
    app.state.otp_manager = resolved_otp_manager
    app.state.replenishment_manager = resolved_replenishment_manager

    def require_api_key(
        authorization: Annotated[str | None, Header()] = None,
    ) -> None:
        expected = resolved_settings.api_key.strip()
        if not expected:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="INVITE_EXECUTOR_API_KEY is not configured",
            )
        scheme, _, supplied = str(authorization or "").partition(" ")
        if scheme.lower() != "bearer" or not compare_digest(supplied, expected):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="invalid API key",
                headers={"WWW-Authenticate": "Bearer"},
            )

    @app.get("/health")
    def health() -> dict:
        active = execution_gate.active
        replenishment_enabled = resolved_replenishment_manager is not None
        return {
            "status": "ok",
            "active_batch_id": active.batch_id if active is not None else "",
            "active_batch_type": active.batch_type if active is not None else "",
            "invite_active_batch_id": resolved_manager.active_batch_id,
            "session_otp_active_batch_id": resolved_otp_manager.active_batch_id,
            "max_batch_size": resolved_settings.max_batch_size,
            "proxy_mode": "webshare_backbone",
            "proxy_configured": proxy_pool.configured,
            "proxy_country": resolved_settings.static_proxy_country.upper(),
            "invite_proxy_count": resolved_settings.invite_proxy_count,
            "invites_per_proxy": resolved_settings.invites_per_proxy,
            "invite_release_interval_ms": resolved_settings.invite_release_interval_ms,
            "transport": "curl_cffi_pinned_async_sessions",
            "prewarm_rounds": resolved_settings.prewarm_rounds,
            "prewarm_attempts": resolved_settings.prewarm_attempts,
            "prewarm_start_interval_ms": resolved_settings.prewarm_start_interval_ms,
            "prewarm_keepalive_interval_s": (resolved_settings.prewarm_keepalive_interval_s),
            "prewarm_timeout_s": resolved_settings.prewarm_timeout_s,
            "session_otp_submit": {
                "enabled": True,
                "proxy_mode": "request_item_direct_proxy",
                "barrier_timeout_s": resolved_settings.session_otp_barrier_timeout_s,
                "release_window_s": resolved_settings.session_otp_release_window_s,
                "validate_path": "/api/accounts/email-otp/validate",
            },
            "auto_replenishment": {
                "enabled": replenishment_enabled,
                "dynamic_registration": replenishment_enabled,
                "interval_s": (
                    resolved_replenishment_manager.interval_s
                    if resolved_replenishment_manager is not None
                    else resolved_settings.auto_replenish_interval_s
                ),
                "account_proxy_country": (
                    resolved_settings.auto_replenish_account_proxy_country.upper()
                ),
                "configured_space_count": (
                    resolved_replenishment_manager.configured_space_count
                    if resolved_replenishment_manager is not None
                    else 0
                ),
                "active_space_count": (
                    resolved_replenishment_manager.active_space_count()
                    if resolved_replenishment_manager is not None
                    else 0
                ),
                "startup_state": (
                    resolved_replenishment_manager.startup_state
                    if resolved_replenishment_manager is not None
                    else "disabled"
                ),
                "startup_error": (
                    resolved_replenishment_manager.startup_error
                    if resolved_replenishment_manager is not None
                    else ""
                ),
            },
        }

    @app.post(
        "/v1/invite-batches",
        response_model=InviteBatchView,
        status_code=status.HTTP_202_ACCEPTED,
        dependencies=[Depends(require_api_key)],
    )
    def create_invite_batch(request: InviteBatchRequest) -> InviteBatchView:
        if request.replenishment is not None and resolved_replenishment_manager is not None:
            resolved_replenishment_manager.register_space(
                external_space_id=request.external_space_id,
                registration=request.replenishment,
                access_token=request.access_token.get_secret_value(),
                cookie_header=request.cookie_header.get_secret_value(),
            )
        try:
            return resolved_manager.submit(request)
        except InviteBatchAlreadyRunningError as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "message": str(exc),
                    "active_batch_type": exc.batch_type,
                    "active_batch_id": exc.batch_id,
                },
            ) from exc
        except InviteBatchTooLargeError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=str(exc),
            ) from exc

    @app.get(
        "/v1/invite-batches/{batch_id}",
        response_model=InviteBatchView,
        dependencies=[Depends(require_api_key)],
    )
    def get_invite_batch(batch_id: str) -> InviteBatchView:
        try:
            return resolved_manager.get(batch_id)
        except InviteBatchNotFoundError as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="invite batch not found",
            ) from exc

    @app.post(
        "/v1/session-otp-submit-batches",
        response_model=SessionOtpBatchView,
        status_code=status.HTTP_202_ACCEPTED,
        dependencies=[Depends(require_api_key)],
    )
    def create_session_otp_batch(
        request: SessionOtpBatchRequest,
    ) -> SessionOtpBatchView:
        try:
            return resolved_otp_manager.submit(request)
        except SessionOtpBatchAlreadyRunningError as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "message": str(exc),
                    "active_batch_type": exc.batch_type,
                    "active_batch_id": exc.batch_id,
                },
            ) from exc
        except SessionOtpBatchTooLargeError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=str(exc),
            ) from exc

    @app.get(
        "/v1/session-otp-submit-batches/{batch_id}",
        response_model=SessionOtpBatchView,
        dependencies=[Depends(require_api_key)],
    )
    def get_session_otp_batch(batch_id: str) -> SessionOtpBatchView:
        try:
            return resolved_otp_manager.get(batch_id)
        except SessionOtpBatchNotFoundError as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="session OTP batch not found",
            ) from exc

    @app.get(
        "/v1/replenishment/spaces",
        response_model=list[SpaceRuntimeView],
        dependencies=[Depends(require_api_key)],
    )
    def list_replenishment_spaces() -> list[SpaceRuntimeView]:
        if resolved_replenishment_manager is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="automatic replenishment is not configured",
            )
        return resolved_replenishment_manager.status()

    @app.post(
        "/v1/replenishment/spaces/{external_space_id}/run",
        response_model=ReplenishmentRunView,
        status_code=status.HTTP_202_ACCEPTED,
        dependencies=[Depends(require_api_key)],
    )
    def run_replenishment_space(external_space_id: str) -> ReplenishmentRunView:
        if resolved_replenishment_manager is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="automatic replenishment is not configured",
            )
        result = resolved_replenishment_manager.trigger(external_space_id)
        if not result.accepted:
            status_code = (
                status.HTTP_404_NOT_FOUND
                if result.reason == "space_not_configured_or_disabled"
                else status.HTTP_409_CONFLICT
            )
            raise HTTPException(status_code=status_code, detail=result.reason)
        return result

    @app.put(
        "/v1/replenishment/spaces/{external_space_id}",
        response_model=SpaceRuntimeView,
        dependencies=[Depends(require_api_key)],
    )
    def upsert_replenishment_space(
        external_space_id: str,
        request: ReplenishmentSpaceUpsertRequest,
    ) -> SpaceRuntimeView:
        if resolved_replenishment_manager is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="automatic replenishment is not configured",
            )
        registration = ReplenishmentRegistration(
            admin_key=request.admin_key,
            admin_email=request.admin_email,
            admin_user_id=request.admin_user_id,
            name=request.name,
            enabled=request.enabled,
            credential_type=request.credential_type,
            seat_limit=request.seat_limit,
            admin_proxy_url=request.admin_proxy_url,
        )
        return resolved_replenishment_manager.register_space(
            external_space_id=external_space_id,
            registration=registration,
            access_token=request.admin_access_token.get_secret_value(),
            cookie_header=request.admin_cookie_header.get_secret_value(),
        )

    @app.delete(
        "/v1/replenishment/spaces/{external_space_id}",
        dependencies=[Depends(require_api_key)],
    )
    def delete_replenishment_space(external_space_id: str) -> dict[str, object]:
        if resolved_replenishment_manager is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="automatic replenishment is not configured",
            )
        try:
            removed = resolved_replenishment_manager.remove_space(external_space_id)
        except RuntimeError as exc:
            if str(exc) == "space_cycle_already_active":
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="space cycle is currently active",
                ) from exc
            raise
        if not removed:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="replenishment space not found",
            )
        return {"removed": True, "external_space_id": external_space_id}

    return app


def _build_replenishment_manager(
    *,
    settings: InviteExecutorSettings,
    proxy_pool: StaticBackboneProxyPool,
    proxy_allocator: Callable[[int], list[StaticProxyAssignment]] | None = None,
) -> SpaceReplenishmentManager:
    settings.validate_auto_replenishment()
    registry = ReplenishmentRegistry(settings.auto_replenish_registry_path)
    spaces = registry.resolved_spaces()
    account_proxy_pool = StaticBackboneProxyPool(
        gateway_host=settings.static_proxy_gateway_host,
        gateway_port=settings.static_proxy_gateway_port,
        username=settings.static_proxy_username,
        password=settings.static_proxy_password,
        country_code=settings.auto_replenish_account_proxy_country,
    )
    proxy_directory = StableProxyDirectory(
        allocator=proxy_allocator or account_proxy_pool.allocate,
        endpoint_count=settings.auto_replenish_account_proxy_count,
    )
    mail_client = ExternalMailApiClient(
        ExternalMailApiClientConfig(
            base_url=settings.auto_replenish_mail_base_url,
            api_key=settings.auto_replenish_mail_api_key,
            api_key_header=settings.auto_replenish_mail_api_key_header,
            provider_name=settings.auto_replenish_mail_provider_name,
            timeout_s=settings.auto_replenish_mail_timeout_s,
            poll_interval_s=settings.auto_replenish_mail_poll_interval_s,
        )
    )
    downstream = Sub2APIAdminClient(
        base_url=settings.auto_replenish_sub2api_base_url,
        api_key=settings.auto_replenish_sub2api_api_key,
        api_key_header=settings.auto_replenish_sub2api_api_key_header,
        request_timeout_s=settings.auto_replenish_sub2api_timeout_s,
    )
    gateway = ChatGPTSpaceGateway(
        chatgpt_base_url=settings.chatgpt_base_url,
        request_timeout_s=settings.request_timeout_s,
        proxy_directory=proxy_directory,
    )
    provisioner = BrowserCodexCredentialProvisioner(
        mail_client=mail_client,
        browser_headless=settings.auto_replenish_browser_headless,
        browser_otp_timeout_s=settings.auto_replenish_browser_otp_timeout_s,
        codex_timeout_s=settings.auto_replenish_codex_timeout_s,
        grizzly_sms_api_key=settings.auto_replenish_grizzly_sms_api_key,
        grizzly_sms_base_url=settings.auto_replenish_grizzly_sms_base_url,
        grizzly_sms_service=settings.auto_replenish_grizzly_sms_service,
        grizzly_sms_country=settings.auto_replenish_grizzly_sms_country,
        grizzly_sms_max_price=settings.auto_replenish_grizzly_sms_max_price,
        grizzly_sms_max_number_attempts=(settings.auto_replenish_grizzly_sms_max_number_attempts),
        grizzly_sms_request_timeout_s=(settings.auto_replenish_grizzly_sms_request_timeout_s),
        grizzly_sms_otp_timeout_s=settings.auto_replenish_grizzly_sms_otp_timeout_s,
        grizzly_sms_poll_interval_s=(settings.auto_replenish_grizzly_sms_poll_interval_s),
    )
    engine = SpaceReplenishmentEngine(
        gateway=gateway,
        provisioner=provisioner,
        downstream=downstream,
        downstream_group_id=settings.auto_replenish_sub2api_group_id,
        downstream_push_group_ids=settings.sub2api_push_group_ids(),
        usage_threshold_percent=settings.auto_replenish_usage_threshold_percent,
        usage_stale_after_s=settings.auto_replenish_usage_stale_after_s,
        member_confirm_attempts=settings.auto_replenish_member_confirm_attempts,
        member_confirm_interval_s=settings.auto_replenish_member_confirm_interval_s,
        candidate_failure_cooldown_s=(settings.auto_replenish_candidate_failure_cooldown_s),
    )
    return SpaceReplenishmentManager(
        spaces=spaces,
        engine=engine,
        registry=registry,
        interval_s=settings.auto_replenish_interval_s,
        max_workers=settings.auto_replenish_max_workers,
    )
