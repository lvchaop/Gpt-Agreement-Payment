from __future__ import annotations

import json
import os
import re
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import quote
from uuid import uuid4

import httpx
from sqlalchemy import func, select
from sqlalchemy.orm import Session

try:
    from curl_cffi import requests as curl_requests
except ModuleNotFoundError:  # pragma: no cover - exercised in minimal test envs.
    class _MissingCurlRequests:
        def Session(self, *args: object, **kwargs: object) -> object:
            raise RuntimeError("curl_cffi is required for ChatGPT browser-session requests")

    curl_requests = _MissingCurlRequests()

from refactor_app.domain.enums import ProxyBindStatus, ProxyStatus
from refactor_app.infrastructure.db.models import (
    JobStepModel,
    ProxyInventoryModel,
    SpaceMembershipModel,
    SpaceModel,
    UserAccountModel,
    UserAccountProxyBindingModel,
)
from refactor_app.infrastructure.logging.event_writer import EventWriter
from refactor_app.plugins.mail_external_api.plugin import ExternalMailApiPlugin
from refactor_app.plugins.openai_auth_protocol.codex_browser_rt import (
    DEFAULT_CODEX_CLIENT_ID,
    acquire_codex_rt_with_browser_login,
    acquire_codex_rt_with_existing_browser_session,
)
from refactor_app.plugins.openai_auth_protocol.session_login import acquire_chatgpt_session
from refactor_app.plugins.openai_chatgpt.client import decode_access_token_claims
from refactor_app.application.workflows.space_authorization import (
    UpsertPersonalCodexSpaceCredentialInput,
    UpsertPersonalCodexSpaceCredentialWorkflow,
)

PROXY_HEALTHCHECK_URL = "https://chatgpt.com/cdn-cgi/trace"
ACCOUNTS_CHECK_URL = "https://chatgpt.com/backend-api/accounts/check/v4-2023-04-27"
TRACE_DIR = Path("runtime/auth-traces")


class AccountAuthWorkflowError(RuntimeError):
    pass


def ensure_account_proxy_url(
    session_factory: Callable[[], Session],
    user_account_id: str,
    *,
    bind_reason: str = "",
    event_writer=None,
) -> str:
    with session_factory() as session:
        account = session.get(UserAccountModel, user_account_id)
        if account is None:
            raise AccountAuthWorkflowError(f"user account not found: {user_account_id}")
        proxy = _active_proxy(session, user_account_id)
        if proxy is not None and _probe_proxy_alive(_proxy_url(proxy)):
            if event_writer is not None:
                event_writer(
                    "account_auth.proxy_ready",
                    "existing account proxy is alive",
                    {"user_account_id": user_account_id, "proxy_id": proxy.id},
                )
            return _proxy_url(proxy)
        if proxy is not None:
            proxy.provider_valid = False
            proxy.proxy_status = ProxyStatus.ERROR.value
            proxy.last_healthcheck_at = datetime.now(UTC)
            proxy.updated_at = datetime.now(UTC)
            if event_writer is not None:
                event_writer(
                    "account_auth.proxy_dead",
                    "existing account proxy is dead",
                    {"user_account_id": user_account_id, "proxy_id": proxy.id},
                    level="WARN",
                )
            session.commit()

    while True:
        now = datetime.now(UTC)
        with session_factory() as session:
            proxy = _least_bound_proxy_for_update(session)
            if proxy is None:
                raise AccountAuthWorkflowError("no available webshare proxy")
            binding = session.scalars(
                select(UserAccountProxyBindingModel)
                .where(UserAccountProxyBindingModel.user_account_id == user_account_id)
                .with_for_update()
            ).first()
            if binding is None:
                binding = UserAccountProxyBindingModel(
                    id=f"proxy-binding-{uuid4()}",
                    user_account_id=user_account_id,
                    proxy_id=proxy.id,
                    bind_status=ProxyBindStatus.ACTIVE.value,
                    bind_reason=bind_reason,
                    bound_by_job_id="",
                    bound_at=now,
                    created_at=now,
                    updated_at=now,
                )
                session.add(binding)
            else:
                binding.proxy_id = proxy.id
                binding.bind_status = ProxyBindStatus.ACTIVE.value
                binding.bind_reason = bind_reason
                binding.bound_at = now
                binding.last_error_code = ""
                binding.updated_at = now
            proxy.proxy_status = ProxyStatus.BOUND.value
            proxy.updated_at = now
            session.commit()
            proxy_url = _proxy_url(proxy)
            proxy_id = proxy.id

        if event_writer is not None:
            event_writer(
                "account_auth.proxy_reassigned",
                "account proxy reassigned",
                {"user_account_id": user_account_id, "proxy_id": proxy_id},
            )
        if _probe_proxy_alive(proxy_url):
            with session_factory() as session:
                proxy = session.get(ProxyInventoryModel, proxy_id)
                if proxy is not None:
                    proxy.provider_valid = True
                    proxy.last_healthcheck_at = datetime.now(UTC)
                    proxy.updated_at = datetime.now(UTC)
                session.commit()
            if event_writer is not None:
                event_writer(
                    "account_auth.proxy_ready",
                    "reassigned account proxy is alive",
                    {"user_account_id": user_account_id, "proxy_id": proxy_id},
                )
            return proxy_url
        with session_factory() as session:
            proxy = session.get(ProxyInventoryModel, proxy_id)
            if proxy is not None:
                proxy.provider_valid = False
                proxy.proxy_status = ProxyStatus.ERROR.value
                proxy.last_healthcheck_at = datetime.now(UTC)
                proxy.updated_at = datetime.now(UTC)
            session.commit()
        if event_writer is not None:
            event_writer(
                "account_auth.proxy_dead",
                "reassigned account proxy is dead",
                {"user_account_id": user_account_id, "proxy_id": proxy_id},
                level="WARN",
            )


class BackfillSessionWorkflow:
    def __init__(
        self,
        *,
        session_factory: Callable[[], Session],
        mail_provider: ExternalMailApiPlugin,
    ) -> None:
        self._session_factory = session_factory
        self._mail_provider = mail_provider

    def run(self, *, user_account_id: str, run_id: str = "") -> str:
        workflow_step_id = self._start_step(
            run_id,
            "account_auth.backfill_session",
            {"user_account_id": user_account_id},
        )
        self._write_event(
            run_id,
            "account_auth.started",
            "account session backfill started",
            {"user_account_id": user_account_id},
            step_id=workflow_step_id,
        )
        try:
            account, auth, proxy_url = self._load_input(user_account_id, run_id=run_id)
        except Exception as exc:
            self._finish_step(
                workflow_step_id,
                "failed",
                error_code=type(exc).__name__,
                error_message=str(exc),
            )
            raise
        now = datetime.now(UTC)

        if not auth.password:
            self._write_failure(
                user_account_id=user_account_id,
                error_code="missing_password",
                error_message="password is required to backfill session/rt",
                now=now,
            )
            self._write_event(
                run_id,
                "account_auth.failed",
                "missing password",
                {"user_account_id": user_account_id},
                level="ERROR",
                step_id=workflow_step_id,
            )
            self._finish_step(
                workflow_step_id,
                "failed",
                error_code="missing_password",
                error_message="password is required to backfill session/rt",
            )
            raise AccountAuthWorkflowError("missing_password")

        proxy_reassign_count = 0
        while True:
            protocol_step_id = self._start_step(
                run_id,
                "chatgpt_session_login_protocol",
                {
                    "user_account_id": user_account_id,
                    "proxy_used": bool(proxy_url),
                    "proxy_reassign_count": proxy_reassign_count,
                },
            )
            trace_path = (
                _new_trace_path(user_account_id=user_account_id, run_id=run_id)
                if _auth_trace_enabled()
                else None
            )
            trace_path_value = _trace_path_value(trace_path)
            try:
                event_data = {
                    "user_account_id": user_account_id,
                    "proxy_used": bool(proxy_url),
                    "proxy_reassign_count": proxy_reassign_count,
                }
                if trace_path_value:
                    event_data["trace_path"] = trace_path_value
                self._write_event(
                    run_id,
                    "account_auth.protocol_started",
                    "chatgpt session login protocol started",
                    event_data,
                    step_id=protocol_step_id,
                )
                result = acquire_chatgpt_session(
                    email=account.email,
                    password=auth.password,
                    proxy=proxy_url,
                    mail_provider=self._mail_provider,
                    trace_dump_path=trace_path_value,
                    skip_oauth_token_exchange=True,
                )
                break
            except Exception as exc:
                trace_summary = _trace_summary(trace_path)
                if _is_cloudflare_csrf_403_after_retries(exc):
                    released_proxy_id = self._release_active_proxy_for_reassign(
                        user_account_id=user_account_id,
                        error_code="cloudflare_csrf_403_after_3_retries",
                        error_message=str(exc),
                    )
                    event_data = {
                        "user_account_id": user_account_id,
                        "proxy_id": released_proxy_id,
                        "error_type": type(exc).__name__,
                        "error_message": str(exc)[:1000],
                        "trace_summary": trace_summary,
                        "next_action": "reassign_proxy",
                    }
                    if trace_path_value:
                        event_data["trace_path"] = trace_path_value
                    self._write_event(
                        run_id,
                        "account_auth.proxy_reassign_after_cloudflare_403",
                        "cloudflare csrf 403 after retries; releasing proxy and reassigning",
                        event_data,
                        level="WARN",
                        step_id=protocol_step_id,
                    )
                    self._write_trace_steps(run_id, protocol_step_id, trace_summary)
                    step_output = {
                        "trace_summary": trace_summary,
                        "released_proxy_id": released_proxy_id,
                    }
                    if trace_path_value:
                        step_output["trace_path"] = trace_path_value
                    self._finish_step(
                        protocol_step_id,
                        "failed",
                        output_json=step_output,
                        error_code="cloudflare_csrf_403_after_3_retries",
                        error_message=str(exc),
                    )
                    account, auth, proxy_url = self._load_input(
                        user_account_id,
                        run_id=run_id,
                    )
                    proxy_reassign_count += 1
                    continue

                self._write_failure(
                    user_account_id=user_account_id,
                    error_code=type(exc).__name__,
                    error_message=str(exc),
                    now=datetime.now(UTC),
                )
                event_data = {
                    "user_account_id": user_account_id,
                    "error_type": type(exc).__name__,
                    "error_message": str(exc)[:1000],
                    "trace_summary": trace_summary,
                }
                if trace_path_value:
                    event_data["trace_path"] = trace_path_value
                self._write_event(
                    run_id,
                    "account_auth.protocol_exception",
                    "chatgpt session login protocol raised exception",
                    event_data,
                    level="ERROR",
                    step_id=protocol_step_id,
                )
                self._write_trace_steps(run_id, protocol_step_id, trace_summary)
                step_output = {"trace_summary": trace_summary}
                if trace_path_value:
                    step_output["trace_path"] = trace_path_value
                self._finish_step(
                    protocol_step_id,
                    "failed",
                    output_json=step_output,
                    error_code=type(exc).__name__,
                    error_message=str(exc),
                )
                self._finish_step(
                    workflow_step_id,
                    "failed",
                    error_code=type(exc).__name__,
                    error_message=str(exc),
                )
                raise

        if (
            not result.ok
            or not result.auth_result.session_token
            or not result.auth_result.access_token
        ):
            trace_summary = _trace_summary(trace_path)
            protocol_snapshot = _summarize_protocol_snapshot(result.snapshot)
            failure_stage = trace_summary.get("failure_stage") or "unknown_protocol_stage"
            result_flags = {
                "ok": result.ok,
                "has_access_token": bool(result.auth_result.access_token),
                "has_id_token": bool(result.auth_result.id_token),
                "has_session_token": bool(result.auth_result.session_token),
                "has_cookie_header": bool(result.cookie_header),
            }
            self._write_failure(
                user_account_id=user_account_id,
                error_code="session_not_obtained",
                error_message="chatgpt login flow finished without session/access token",
                now=datetime.now(UTC),
            )
            event_data = {
                "user_account_id": user_account_id,
                **result_flags,
                "failure_stage": trace_summary.get("failure_stage", ""),
                "last_http": trace_summary.get("last_http", {}),
                "trace_summary": trace_summary,
                "protocol_snapshot": protocol_snapshot,
            }
            if trace_path_value:
                event_data["trace_path"] = trace_path_value
            self._write_event(
                run_id,
                "account_auth.protocol_failed",
                "chatgpt session login protocol finished without session/access token",
                event_data,
                level="ERROR",
                step_id=protocol_step_id,
            )
            self._write_trace_steps(run_id, protocol_step_id, trace_summary)
            step_output = {
                "result_flags": result_flags,
                "trace_summary": trace_summary,
                "protocol_snapshot": protocol_snapshot,
            }
            if trace_path_value:
                step_output["trace_path"] = trace_path_value
            self._finish_step(
                protocol_step_id,
                "failed",
                output_json=step_output,
                error_code="session_not_obtained",
                error_message=f"failed at {failure_stage}",
            )
            self._finish_step(
                workflow_step_id,
                "failed",
                error_code="session_not_obtained",
                error_message=f"failed at {failure_stage}",
            )
            raise AccountAuthWorkflowError("session_not_obtained")

        self._write_success(user_account_id=user_account_id, result=result, now=datetime.now(UTC))
        accounts_check_payload = self._mark_detected_space_memberships(
            user_account_id=user_account_id,
            access_token=result.auth_result.access_token,
            cookie_header=result.cookie_header or result.auth_result.cookie_header,
            proxy_url=proxy_url,
            oai_device_id=result.auth_result.device_id,
            run_id=run_id,
            parent_step_id=workflow_step_id,
        )
        if not self._has_personal_chatgpt_account_id(user_account_id):
            self._discover_personal_chatgpt_account(
                user_account_id=user_account_id,
                access_token=result.auth_result.access_token,
                cookie_header=result.cookie_header or result.auth_result.cookie_header,
                proxy_url=proxy_url,
                oai_device_id=result.auth_result.device_id,
                run_id=run_id,
                parent_step_id=workflow_step_id,
                accounts_check_payload=accounts_check_payload,
            )
        trace_summary = _trace_summary(trace_path)
        self._write_trace_steps(run_id, protocol_step_id, trace_summary)
        step_output = {"trace_summary": trace_summary}
        if trace_path_value:
            step_output["trace_path"] = trace_path_value
        self._finish_step(
            protocol_step_id,
            "succeeded",
            output_json=step_output,
        )
        self._finish_step(workflow_step_id, "succeeded")
        event_data = {
            "user_account_id": user_account_id,
            "has_refresh_token": bool(result.auth_result.refresh_token),
            "has_session_token": bool(result.auth_result.session_token),
            "has_cookie_header": bool(result.cookie_header),
        }
        if trace_path_value:
            event_data["trace_path"] = trace_path_value
        self._write_event(
            run_id,
            "account_auth.succeeded",
            "account session backfill succeeded",
            event_data,
            step_id=workflow_step_id,
        )
        return user_account_id

    def _load_input(
        self,
        user_account_id: str,
        run_id: str = "",
    ) -> tuple[UserAccountModel, UserAccountModel, str]:
        account, auth, proxy = self._load_account_auth_proxy(user_account_id)
        if proxy is not None and _probe_proxy_alive(_proxy_url(proxy)):
            self._mark_proxy_health(proxy.id, alive=True)
            self._write_event(
                run_id,
                "account_auth.proxy_ready",
                "existing account proxy is alive",
                {"user_account_id": user_account_id, "proxy_id": proxy.id},
            )
            return account, auth, _proxy_url(proxy)

        if proxy is not None:
            self._mark_proxy_health(proxy.id, alive=False)
            self._write_event(
                run_id,
                "account_auth.proxy_dead",
                "existing account proxy is dead",
                {"user_account_id": user_account_id, "proxy_id": proxy.id},
                level="WARN",
            )

        while True:
            proxy = self._rebind_least_bound_proxy(user_account_id)
            self._write_event(
                run_id,
                "account_auth.proxy_reassigned",
                "account proxy reassigned",
                {"user_account_id": user_account_id, "proxy_id": proxy.id},
            )
            if _probe_proxy_alive(_proxy_url(proxy)):
                self._mark_proxy_health(proxy.id, alive=True)
                self._write_event(
                    run_id,
                    "account_auth.proxy_ready",
                    "reassigned account proxy is alive",
                    {"user_account_id": user_account_id, "proxy_id": proxy.id},
                )
                return account, auth, _proxy_url(proxy)
            self._mark_proxy_health(proxy.id, alive=False)
            self._write_event(
                run_id,
                "account_auth.proxy_dead",
                "reassigned account proxy is dead",
                {"user_account_id": user_account_id, "proxy_id": proxy.id},
                level="WARN",
            )

    def _load_account_auth_proxy(
        self,
        user_account_id: str,
    ) -> tuple[UserAccountModel, UserAccountModel, ProxyInventoryModel | None]:
        with self._session_factory() as session:
            account = session.get(UserAccountModel, user_account_id)
            if account is None:
                raise AccountAuthWorkflowError(f"user account not found: {user_account_id}")
            proxy = _active_proxy(session, user_account_id)
            return account, account, proxy

    def _rebind_least_bound_proxy(self, user_account_id: str) -> ProxyInventoryModel:
        now = datetime.now(UTC)
        with self._session_factory() as session:
            account = session.get(UserAccountModel, user_account_id)
            if account is None:
                raise AccountAuthWorkflowError(f"user account not found: {user_account_id}")

            proxy = _least_bound_proxy_for_update(session)
            if proxy is None:
                raise AccountAuthWorkflowError("no available webshare proxy")

            binding = session.scalars(
                select(UserAccountProxyBindingModel)
                .where(UserAccountProxyBindingModel.user_account_id == user_account_id)
                .with_for_update()
            ).first()
            if binding is None:
                binding = UserAccountProxyBindingModel(
                    id=f"proxy-binding-{uuid4()}",
                    user_account_id=user_account_id,
                    proxy_id=proxy.id,
                    bind_status=ProxyBindStatus.ACTIVE.value,
                    bind_reason="backfill_session_rt",
                    bound_by_job_id="",
                    bound_at=now,
                    created_at=now,
                    updated_at=now,
                )
                session.add(binding)
            else:
                binding.proxy_id = proxy.id
                binding.bind_status = ProxyBindStatus.ACTIVE.value
                binding.bind_reason = "backfill_session_rt"
                binding.bound_at = now
                binding.last_error_code = ""
                binding.updated_at = now

            proxy.proxy_status = ProxyStatus.BOUND.value
            proxy.updated_at = now
            session.commit()
            session.refresh(proxy)
            return proxy

    def _write_event(
        self,
        run_id: str,
        event_type: str,
        message: str,
        data_json: dict,
        *,
        level: str = "INFO",
        step_id: str | None = None,
    ) -> None:
        if not run_id:
            return
        with self._session_factory() as session:
            EventWriter(session).write(
                run_id=run_id,
                event_type=event_type,
                message=message,
                level=level,
                data_json=data_json,
                step_id=step_id,
            )
            session.commit()

    def _start_step(self, run_id: str, name: str, input_json: dict | None = None) -> str:
        if not run_id:
            return ""
        step_id = str(uuid4())
        now = datetime.now(UTC)
        with self._session_factory() as session:
            session.add(
                JobStepModel(
                    id=step_id,
                    run_id=run_id,
                    name=name,
                    step_status="running",
                    attempt=1,
                    started_at=now,
                    input_json=input_json or {},
                    output_json={},
                    error_code="",
                    error_message="",
                )
            )
            session.commit()
        return step_id

    def _finish_step(
        self,
        step_id: str,
        status: str,
        *,
        output_json: dict | None = None,
        error_code: str = "",
        error_message: str = "",
    ) -> None:
        if not step_id:
            return
        with self._session_factory() as session:
            step = session.get(JobStepModel, step_id)
            if step is None:
                return
            step.step_status = status
            step.finished_at = datetime.now(UTC)
            if output_json is not None:
                step.output_json = output_json
            step.error_code = error_code[:200]
            step.error_message = error_message[:1000]
            session.commit()

    def _write_trace_steps(self, run_id: str, parent_step_id: str, trace_summary: dict) -> None:
        if not run_id:
            return
        records = trace_summary.get("records", [])
        if not isinstance(records, list):
            return
        now = datetime.now(UTC)
        with self._session_factory() as session:
            for index, record in enumerate(records, start=1):
                if not isinstance(record, dict):
                    continue
                status_code = int(record.get("status_code") or 0)
                is_failure = bool(record.get("is_failure"))
                step = JobStepModel(
                    id=str(uuid4()),
                    run_id=run_id,
                    name=f"protocol.http.{index:02d}.{record.get('step') or 'unknown'}",
                    step_status="failed" if is_failure else "succeeded",
                    attempt=1,
                    started_at=now,
                    finished_at=now,
                    input_json={
                        "parent_step_id": parent_step_id,
                        "method": record.get("method", ""),
                        "url": record.get("url", ""),
                    },
                    output_json=record,
                    error_code=f"http_{status_code}" if is_failure and status_code else "",
                    error_message=(
                        str(record.get("body_snippet") or record.get("location") or "")[:1000]
                        if is_failure
                        else ""
                    ),
                )
                session.add(step)
            session.commit()

    def _mark_proxy_health(self, proxy_id: str, *, alive: bool) -> None:
        now = datetime.now(UTC)
        with self._session_factory() as session:
            proxy = session.get(ProxyInventoryModel, proxy_id)
            if proxy is None:
                return
            proxy.last_healthcheck_at = now
            if alive:
                proxy.provider_valid = True
                proxy.proxy_status = ProxyStatus.BOUND.value
            else:
                proxy.provider_valid = False
                proxy.proxy_status = ProxyStatus.ERROR.value
            proxy.updated_at = now
            session.commit()

    def _release_active_proxy_for_reassign(
        self,
        *,
        user_account_id: str,
        error_code: str,
        error_message: str,
    ) -> str:
        now = datetime.now(UTC)
        with self._session_factory() as session:
            row = session.execute(
                select(UserAccountProxyBindingModel, ProxyInventoryModel)
                .join(
                    ProxyInventoryModel,
                    ProxyInventoryModel.id == UserAccountProxyBindingModel.proxy_id,
                )
                .where(
                    UserAccountProxyBindingModel.user_account_id == user_account_id,
                    UserAccountProxyBindingModel.bind_status == ProxyBindStatus.ACTIVE.value,
                )
                .with_for_update()
                .limit(1)
            ).first()
            if row is None:
                return ""

            binding, proxy = row
            binding.bind_status = ProxyBindStatus.RELEASED.value
            binding.last_error_code = error_code[:200]
            binding.updated_at = now

            proxy.provider_valid = False
            proxy.proxy_status = ProxyStatus.ERROR.value
            proxy.last_healthcheck_at = now
            proxy.updated_at = now
            session.commit()
            return proxy.id

    def _write_success(self, *, user_account_id: str, result, now: datetime) -> None:
        auth_result = result.auth_result
        with self._session_factory() as session:
            account = session.get(UserAccountModel, user_account_id)
            if account is None:
                raise AccountAuthWorkflowError("user_account row disappeared")
            account.session_token = _keep_existing_if_empty(
                account.session_token,
                auth_result.session_token,
            )
            account.cookie_header = _keep_existing_if_empty(
                account.cookie_header,
                result.cookie_header or auth_result.cookie_header,
            )
            account.cookie_header = _ensure_session_token_cookie(
                account.cookie_header,
                account.session_token,
            )
            account.auth_cookie_header = _keep_existing_if_empty(
                account.auth_cookie_header,
                getattr(result, "auth_cookie_header", ""),
            )
            account.device_id = _keep_existing_if_empty(account.device_id, auth_result.device_id)
            account.csrf_token = _keep_existing_if_empty(account.csrf_token, auth_result.csrf_token)
            if auth_result.access_token:
                account.access_token = auth_result.access_token
            if (
                str(getattr(auth_result, "chatgpt_account_structure", "") or "").lower()
                == "personal"
                and str(getattr(auth_result, "chatgpt_account_id", "") or "").strip()
            ):
                _ensure_personal_space(
                    session=session,
                    user_account_id=user_account_id,
                    external_space_id=str(
                        getattr(auth_result, "chatgpt_account_id", "") or ""
                    ).strip(),
                    space_name=account.email,
                    now=now,
                )
            account.session_status = (
                "active"
                if account.session_token or account.cookie_header
                else account.session_status
            )
            account.last_session_refresh_at = now
            account.last_login_error_code = ""
            account.last_login_error_message = ""
            account.updated_at = now
            if auth_result.access_token:
                try:
                    claims = decode_access_token_claims(auth_result.access_token)
                except Exception:
                    claims = None
                if claims is not None and claims.chatgpt_account_user_id:
                    account.openai_user_id = claims.chatgpt_account_user_id
                    account.updated_at = now
            session.commit()

    def _has_personal_chatgpt_account_id(self, user_account_id: str) -> bool:
        return bool(self._personal_space_external_id(user_account_id))

    def _personal_space_external_id(self, user_account_id: str) -> str:
        with self._session_factory() as session:
            return _personal_space_external_id(session=session, user_account_id=user_account_id)

    def _discover_personal_chatgpt_account(
        self,
        *,
        user_account_id: str,
        access_token: str,
        cookie_header: str,
        proxy_url: str,
        oai_device_id: str = "",
        run_id: str,
        parent_step_id: str,
        accounts_check_payload: dict | None = None,
    ) -> None:
        step_id = self._start_step(
            run_id,
            "account_auth.accounts_check_personal",
            {"user_account_id": user_account_id},
        )
        try:
            payload = accounts_check_payload
            if payload is None:
                payload = _fetch_accounts_check_v4(
                    access_token=access_token,
                    cookie_header=cookie_header,
                    proxy_url=proxy_url,
                    oai_device_id=oai_device_id,
                )
            personal_account_id = _extract_personal_chatgpt_account_id(payload)
            if not personal_account_id:
                self._write_event(
                    run_id,
                    "account_auth.personal_account_not_found",
                    "accounts/check did not contain personal account",
                    {"user_account_id": user_account_id},
                    level="WARN",
                    step_id=step_id or parent_step_id,
                )
                self._finish_step(
                    step_id,
                    "skipped",
                    output_json={"reason": "personal_account_not_found"},
                )
                return
            now = datetime.now(UTC)
            with self._session_factory() as session:
                account = session.get(UserAccountModel, user_account_id)
                if account is None:
                    raise AccountAuthWorkflowError("user_account row disappeared")
                _ensure_personal_space(
                    session=session,
                    user_account_id=user_account_id,
                    external_space_id=personal_account_id,
                    space_name=account.email,
                    now=now,
                )
                session.commit()
            self._write_event(
                run_id,
                "account_auth.personal_account_discovered",
                "personal ChatGPT account discovered from accounts/check",
                {
                    "user_account_id": user_account_id,
                    "personal_chatgpt_account_id": personal_account_id,
                },
                step_id=step_id or parent_step_id,
            )
            self._finish_step(
                step_id,
                "succeeded",
                output_json={"personal_chatgpt_account_id": personal_account_id},
            )
        except Exception as exc:
            self._write_event(
                run_id,
                "account_auth.personal_account_discovery_failed",
                "accounts/check personal account discovery failed",
                {
                    "user_account_id": user_account_id,
                    "error_type": type(exc).__name__,
                    "error_message": str(exc)[:1000],
                },
                level="WARN",
                step_id=step_id or parent_step_id,
            )
            self._finish_step(
                step_id,
                "failed",
                error_code=type(exc).__name__,
                error_message=str(exc),
            )

    def _mark_detected_space_memberships(
        self,
        *,
        user_account_id: str,
        access_token: str,
        cookie_header: str,
        proxy_url: str,
        oai_device_id: str = "",
        run_id: str,
        parent_step_id: str,
    ) -> dict | None:
        step_id = self._start_step(
            run_id,
            "account_auth.accounts_check_memberships",
            {"user_account_id": user_account_id},
        )
        try:
            payload = _fetch_accounts_check_v4(
                access_token=access_token,
                cookie_header=cookie_header,
                proxy_url=proxy_url,
                oai_device_id=oai_device_id,
            )
            visible_account_ids = _extract_visible_chatgpt_account_ids(payload)
            if not visible_account_ids:
                self._finish_step(
                    step_id,
                    "skipped",
                    output_json={"reason": "no_visible_account_ids"},
                )
                return payload

            now = datetime.now(UTC)
            with self._session_factory() as session:
                account = session.get(UserAccountModel, user_account_id)
                if account is None:
                    raise AccountAuthWorkflowError("user_account row disappeared")
                spaces = session.scalars(
                    select(SpaceModel).where(
                        SpaceModel.provider == "openai_chatgpt",
                        SpaceModel.external_space_id.in_(visible_account_ids),
                    )
                ).all()
                marked = 0
                for space in spaces:
                    membership = session.scalars(
                        select(SpaceMembershipModel).where(
                            SpaceMembershipModel.space_id == space.id,
                            SpaceMembershipModel.user_account_id == user_account_id,
                        )
                    ).first()
                    if membership is None:
                        membership = SpaceMembershipModel(
                            id=f"space-membership-{uuid4()}",
                            space_id=space.id,
                            user_account_id=user_account_id,
                            role="",
                            membership_status="active",
                            session_account_detected=True,
                            remote_user_id=account.openai_user_id,
                            created_at=now,
                            updated_at=now,
                        )
                        session.add(membership)
                    else:
                        membership.membership_status = "active"
                        membership.session_account_detected = True
                        if account.openai_user_id and not membership.remote_user_id:
                            membership.remote_user_id = account.openai_user_id
                        membership.failure_code = ""
                        membership.failure_message = ""
                        membership.updated_at = now
                    marked += 1
                session.commit()

            self._write_event(
                run_id,
                "account_auth.space_memberships_detected",
                "space memberships detected from accounts/check",
                {
                    "user_account_id": user_account_id,
                    "visible_account_count": len(visible_account_ids),
                    "marked_membership_count": marked,
                },
                step_id=step_id or parent_step_id,
            )
            self._finish_step(
                step_id,
                "succeeded",
                output_json={
                    "visible_account_count": len(visible_account_ids),
                    "marked_membership_count": marked,
                },
            )
            return payload
        except Exception as exc:
            self._write_event(
                run_id,
                "account_auth.space_membership_detection_failed",
                "accounts/check space membership detection failed",
                {
                    "user_account_id": user_account_id,
                    "error_type": type(exc).__name__,
                    "error_message": str(exc)[:1000],
                },
                level="WARN",
                step_id=step_id or parent_step_id,
            )
            self._finish_step(
                step_id,
                "failed",
                error_code=type(exc).__name__,
                error_message=str(exc)[:1000],
            )
            return None

    def _write_failure(
        self,
        *,
        user_account_id: str,
        error_code: str,
        error_message: str,
        now: datetime,
    ) -> None:
        with self._session_factory() as session:
            account = session.get(UserAccountModel, user_account_id)
            if account is not None:
                if _is_deleted_or_deactivated_account_error(error_message):
                    account.account_status = "invalid"
                    account.session_status = "dead"
                else:
                    account.session_status = "error"
                account.last_login_error_code = error_code[:200]
                account.last_login_error_message = error_message[:1000]
                account.updated_at = now
                session.commit()


class BackfillSessionRtWorkflow(BackfillSessionWorkflow):
    def run(self, *, user_account_id: str, run_id: str = "") -> str:
        super().run(user_account_id=user_account_id, run_id=run_id)
        return BackfillRtWorkflow(
            session_factory=self._session_factory,
            mail_provider=self._mail_provider,
        ).run(user_account_id=user_account_id, run_id=run_id)


class BackfillRtWorkflow(BackfillSessionWorkflow):
    def __init__(
        self,
        *,
        session_factory: Callable[[], Session],
        mail_provider: ExternalMailApiPlugin,
    ) -> None:
        self._session_factory = session_factory
        self._mail_provider = mail_provider

    def run(self, *, user_account_id: str, run_id: str = "") -> str:
        step_id = self._start_step(
            run_id,
            "account_auth.backfill_rt_fast_path",
            {"user_account_id": user_account_id},
        )
        account, auth, proxy_url = self._load_input(user_account_id, run_id=run_id)
        cookie_header = auth.cookie_header or ""
        auth_cookie_header = auth.auth_cookie_header or ""
        personal_chatgpt_account_id = self._personal_space_external_id(user_account_id)
        if not personal_chatgpt_account_id:
            self._write_rt_failure(
                user_account_id=user_account_id,
                error_code="missing_personal_chatgpt_account_id",
                error_message="补个人 RT 需要先从 session/v4 解析 personal_chatgpt_account_id",
            )
            self._finish_step(
                step_id,
                "failed",
                error_code="missing_personal_chatgpt_account_id",
                error_message="补个人 RT 需要先从 session/v4 解析 personal_chatgpt_account_id",
            )
            raise AccountAuthWorkflowError("missing_personal_chatgpt_account_id")
        if not (cookie_header or auth_cookie_header):
            self._write_rt_failure(
                user_account_id=user_account_id,
                error_code="missing_session_cookie",
                error_message="补 RT 需要已有 session/cookie，请先补 Session",
            )
            self._finish_step(
                step_id,
                "failed",
                error_code="missing_session_cookie",
                error_message="补 RT 需要已有 session/cookie，请先补 Session",
            )
            raise AccountAuthWorkflowError("missing_session_cookie")

        self._write_event(
            run_id,
            "account_auth.rt_fast_path_started",
            "codex rt fast path started with existing browser session",
            {
                "user_account_id": user_account_id,
                "email": account.email,
                "proxy_used": bool(proxy_url),
                "has_cookie_header": bool(cookie_header),
                "has_auth_cookie_header": bool(auth_cookie_header),
                "target_personal_chatgpt_account_id": personal_chatgpt_account_id,
            },
            step_id=step_id,
        )
        result = acquire_codex_rt_with_existing_browser_session(
            cookie_header=cookie_header,
            auth_cookie_header=auth_cookie_header,
            proxy=proxy_url,
            target_workspace_id=personal_chatgpt_account_id,
            target_workspace_name="Personal account",
        )
        used_browser_login = False
        if not result.ok:
            self._write_event(
                run_id,
                "account_auth.rt_fast_path_failed",
                "codex rt fast path failed",
                {
                    "user_account_id": user_account_id,
                    "failure_code": result.failure_code,
                    "failure_message": result.failure_message,
                    "callback_url_seen": result.callback_url_seen,
                    "final_url": result.final_url,
                },
                level="ERROR",
                step_id=step_id,
            )
            if not auth.password:
                self._write_rt_failure(
                    user_account_id=user_account_id,
                    error_code=result.failure_code or "rt_fast_path_failed",
                    error_message=result.failure_message,
                )
                self._finish_step(
                    step_id,
                    "failed",
                    output_json={
                        "failure_code": result.failure_code,
                        "failure_message": result.failure_message,
                        "callback_url_seen": result.callback_url_seen,
                        "final_url": result.final_url,
                    },
                    error_code=result.failure_code or "rt_fast_path_failed",
                    error_message=result.failure_message,
                )
                raise AccountAuthWorkflowError(result.failure_code or "rt_fast_path_failed")

            self._write_event(
                run_id,
                "account_auth.rt_browser_login_started",
                "codex rt browser login fallback started",
                {
                    "user_account_id": user_account_id,
                        "email": account.email,
                        "proxy_used": bool(proxy_url),
                        "fast_path_failure_code": result.failure_code,
                        "target_personal_chatgpt_account_id": personal_chatgpt_account_id,
                    },
                    step_id=step_id,
                )
            result = acquire_codex_rt_with_browser_login(
                email=account.email,
                password=auth.password,
                mail_provider=self._mail_provider,
                proxy=proxy_url,
                target_workspace_id=personal_chatgpt_account_id,
                target_workspace_name="Personal account",
            )
            used_browser_login = True
            if not result.ok:
                self._write_rt_failure(
                    user_account_id=user_account_id,
                    error_code=result.failure_code or "rt_browser_login_failed",
                    error_message=result.failure_message,
                )
                self._write_event(
                    run_id,
                    "account_auth.rt_browser_login_failed",
                    "codex rt browser login fallback failed",
                    {
                        "user_account_id": user_account_id,
                        "failure_code": result.failure_code,
                        "failure_message": result.failure_message,
                        "callback_url_seen": result.callback_url_seen,
                        "final_url": result.final_url,
                    },
                    level="ERROR",
                    step_id=step_id,
                )
                self._finish_step(
                    step_id,
                    "failed",
                    output_json={
                        "failure_code": result.failure_code,
                        "failure_message": result.failure_message,
                        "callback_url_seen": result.callback_url_seen,
                        "final_url": result.final_url,
                    },
                    error_code=result.failure_code or "rt_browser_login_failed",
                    error_message=result.failure_message,
                )
                raise AccountAuthWorkflowError(result.failure_code or "rt_browser_login_failed")

        if not result.access_token:
            error_message = (
                "补个人 RT 成功返回 refresh_token 但缺少 access_token，"
                "无法校验 account"
            )
            self._write_rt_failure(
                user_account_id=user_account_id,
                error_code="missing_access_token",
                error_message=error_message,
            )
            self._finish_step(
                step_id,
                "failed",
                error_code="missing_access_token",
                error_message=error_message,
            )
            raise AccountAuthWorkflowError("missing_access_token")
        claims = decode_access_token_claims(result.access_token)
        if claims.token_chatgpt_account_id != personal_chatgpt_account_id:
            message = (
                "补个人 RT 拿到的 token_chatgpt_account_id 不匹配: "
                f"expected={personal_chatgpt_account_id} actual={claims.token_chatgpt_account_id}"
            )
            self._write_rt_failure(
                user_account_id=user_account_id,
                error_code="personal_rt_space_mismatch",
                error_message=message,
            )
            self._write_event(
                run_id,
                "account_auth.rt_personal_space_mismatch",
                "personal rt token space mismatch",
                {
                    "user_account_id": user_account_id,
                    "expected": personal_chatgpt_account_id,
                    "actual": claims.token_chatgpt_account_id,
                },
                level="ERROR",
                step_id=step_id,
            )
            self._finish_step(
                step_id,
                "failed",
                error_code="personal_rt_space_mismatch",
                error_message=message,
            )
            raise AccountAuthWorkflowError("personal_rt_space_mismatch")

        now = datetime.now(UTC)
        with self._session_factory() as session:
            account = session.get(UserAccountModel, user_account_id)
            if account is None:
                raise AccountAuthWorkflowError("user_account row disappeared")
            if claims.chatgpt_account_user_id:
                account.openai_user_id = claims.chatgpt_account_user_id
            account.last_login_error_code = ""
            account.last_login_error_message = ""
            account.updated_at = now
            session.commit()
        UpsertPersonalCodexSpaceCredentialWorkflow(
            session_factory=self._session_factory,
        ).run(
            UpsertPersonalCodexSpaceCredentialInput(
                user_account_id=user_account_id,
                external_space_id=personal_chatgpt_account_id,
                access_token=result.access_token,
                id_token=result.id_token,
                refresh_token=result.refresh_token,
                codex_client_id=DEFAULT_CODEX_CLIENT_ID,
                account_id=claims.chatgpt_account_user_id,
                token_chatgpt_account_id=claims.token_chatgpt_account_id,
                expires_at=None,
                raw_credential_json={
                    "token_type": result.token_type,
                    "scope": result.scope,
                    "source": "account.backfill_rt",
                },
                space_name=account_email,
            )
        )

        self._write_event(
            run_id,
            (
                "account_auth.rt_browser_login_succeeded"
                if used_browser_login
                else "account_auth.rt_fast_path_succeeded"
            ),
            (
                "codex rt browser login fallback succeeded"
                if used_browser_login
                else "codex rt fast path succeeded"
            ),
            {
                "user_account_id": user_account_id,
                "used_browser_login": used_browser_login,
                "has_refresh_token": bool(result.refresh_token),
                "has_access_token": bool(result.access_token),
                "has_id_token": bool(result.id_token),
                "scope": result.scope,
            },
            step_id=step_id,
        )
        self._finish_step(
            step_id,
            "succeeded",
            output_json={
                "has_refresh_token": bool(result.refresh_token),
                "has_access_token": bool(result.access_token),
                "has_id_token": bool(result.id_token),
                "scope": result.scope,
            },
        )
        return user_account_id

    def _write_rt_failure(
        self,
        *,
        user_account_id: str,
        error_code: str,
        error_message: str,
    ) -> None:
        now = datetime.now(UTC)
        with self._session_factory() as session:
            account = session.get(UserAccountModel, user_account_id)
            if account is not None:
                account.last_login_error_code = error_code[:200]
                account.last_login_error_message = error_message[:1000]
                account.updated_at = now
                session.commit()


def _active_proxy(session: Session, user_account_id: str) -> ProxyInventoryModel | None:
    row = session.execute(
        select(UserAccountProxyBindingModel, ProxyInventoryModel)
        .join(ProxyInventoryModel, ProxyInventoryModel.id == UserAccountProxyBindingModel.proxy_id)
        .where(
            UserAccountProxyBindingModel.user_account_id == user_account_id,
            UserAccountProxyBindingModel.bind_status == ProxyBindStatus.ACTIVE.value,
            ProxyInventoryModel.proxy_status.in_(
                (ProxyStatus.AVAILABLE.value, ProxyStatus.BOUND.value)
            ),
            ProxyInventoryModel.provider_valid.is_(True),
        )
        .limit(1)
    ).first()
    if row is None:
        return None
    _binding, proxy = row
    return proxy


def _personal_space_external_id(*, session: Session, user_account_id: str) -> str:
    space = session.scalars(
        select(SpaceModel).where(
            SpaceModel.provider == "openai_chatgpt",
            SpaceModel.owner_user_account_id == user_account_id,
            SpaceModel.space_type == "personal",
            SpaceModel.credential_type == "personal_account",
        )
    ).first()
    return space.external_space_id if space is not None else ""


def _ensure_personal_space(
    *,
    session: Session,
    user_account_id: str,
    external_space_id: str,
    space_name: str,
    now: datetime,
) -> SpaceModel:
    external_id = external_space_id.strip()
    if not external_id:
        raise AccountAuthWorkflowError("personal_space_external_id_required")
    space = session.scalars(
        select(SpaceModel).where(
            SpaceModel.provider == "openai_chatgpt",
            SpaceModel.external_space_id == external_id,
        )
    ).first()
    if space is None:
        space = SpaceModel(
            id=f"space-{uuid4()}",
            provider="openai_chatgpt",
            external_space_id=external_id,
            owner_user_account_id=user_account_id,
            name=space_name or external_id,
            space_type="personal",
            auth_mode="codex_oauth",
            credential_type="personal_account",
            plan_type="",
            seat_limit=0,
            seats_in_use=0,
            seats_entitled=0,
            space_status="active",
            source_admin_session_id="",
            raw_space_json={},
            last_probe_at=now,
            created_at=now,
            updated_at=now,
        )
        session.add(space)
        return space
    space.owner_user_account_id = user_account_id
    space.name = space.name or space_name or external_id
    space.space_type = "personal"
    space.auth_mode = "codex_oauth"
    space.credential_type = "personal_account"
    space.space_status = "active"
    space.last_probe_at = now
    space.updated_at = now
    return space


def _new_trace_path(*, user_account_id: str, run_id: str) -> Path:
    TRACE_DIR.mkdir(parents=True, exist_ok=True)
    safe_account_id = re.sub(r"[^a-zA-Z0-9_.-]+", "_", user_account_id)[:80]
    safe_run_id = re.sub(r"[^a-zA-Z0-9_.-]+", "_", run_id or "no-run")[:80]
    ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    return TRACE_DIR / f"{ts}_{safe_account_id}_{safe_run_id}.jsonl"


def _auth_trace_enabled() -> bool:
    return os.getenv("REFACTOR_APP_AUTH_TRACE_ENABLED", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _trace_path_value(path: Path | None) -> str:
    return str(path) if path is not None else ""


def _trace_summary(path: Path | None) -> dict:
    if path is None:
        return {}
    return _summarize_trace_file(path)


def _summarize_trace_file(path: Path) -> dict:
    if not path.exists():
        return {
            "trace_path": str(path),
            "record_count": 0,
            "failure_stage": "trace_file_missing",
            "records": [],
            "last_http": {},
        }

    records: list[dict] = []
    with path.open("r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                raw = json.loads(line)
            except json.JSONDecodeError:
                continue
            item = _summarize_trace_record(raw)
            if item:
                records.append(item)

    failure_record = _pick_failure_record(records)
    last_http = records[-1] if records else {}
    failure_stage = (failure_record or last_http).get("step", "") if records else "trace_empty"
    return {
        "trace_path": str(path),
        "record_count": len(records),
        "failure_stage": failure_stage,
        "failure_http": failure_record or {},
        "last_http": last_http,
        "records": records,
    }


def _summarize_protocol_snapshot(snapshot: dict) -> dict:
    if not isinstance(snapshot, dict):
        return {}
    result = snapshot.get("result") if isinstance(snapshot.get("result"), dict) else {}
    oauth = snapshot.get("oauth") if isinstance(snapshot.get("oauth"), dict) else {}
    mail_events = snapshot.get("mail_events")
    if not isinstance(mail_events, list):
        mail_events = []
    return {
        "phase": snapshot.get("phase", ""),
        "page_type": snapshot.get("page_type", ""),
        "continue_url": _redact(str(snapshot.get("continue_url", "")))[:600],
        "mail_events": mail_events[-10:],
        "has_session_token": bool(result.get("session_token")),
        "has_access_token": bool(result.get("access_token")),
        "has_id_token": bool(result.get("id_token")),
        "has_refresh_token": bool(result.get("refresh_token")),
        "oauth_client_id": oauth.get("client_id", ""),
        "oauth_redirect_uri": oauth.get("redirect_uri", ""),
        "oauth_scope": oauth.get("scope", ""),
        "oauth_has_auth_url": bool(oauth.get("auth_url")),
        "oauth_has_captured_login_verifier": bool(oauth.get("captured_login_verifier")),
    }


def _summarize_trace_record(raw: dict) -> dict:
    request = raw.get("request") if isinstance(raw.get("request"), dict) else {}
    response = raw.get("response") if isinstance(raw.get("response"), dict) else {}
    status_code = _safe_int(response.get("status_code"))
    location = _redact(str(response.get("location") or ""))
    body = _redact(str(response.get("body") or ""))
    url = _redact(str(response.get("url") or request.get("url") or ""))
    step = str(raw.get("step") or "unknown")
    is_failure = _is_failed_trace_record(
        step=step,
        status_code=status_code,
        url=url,
        location=location,
        body=body,
    )
    return {
        "step": step,
        "method": str(request.get("method") or ""),
        "url": url[:600],
        "status_code": status_code,
        "location": location[:600],
        "x_request_id": str(response.get("x_request_id") or "")[:160],
        "content_type": str(response.get("content_type") or "")[:160],
        "body_snippet": body[:600],
        "is_failure": is_failure,
    }


def _pick_failure_record(records: list[dict]) -> dict | None:
    for record in reversed(records):
        if record.get("is_failure"):
            return record
    return None


def _safe_int(value) -> int:
    try:
        return int(value)
    except Exception:
        return 0


def _is_failed_trace_record(
    *,
    step: str,
    status_code: int,
    url: str,
    location: str,
    body: str,
) -> bool:
    if status_code >= 400:
        return True
    if _looks_like_auth_error(body) or _looks_like_auth_error(location):
        return True
    if step.startswith("codex_authorize_noprompt") and status_code == 200:
        return "auth.openai.com/log-in" in url
    return False


def _looks_like_auth_error(text: str) -> bool:
    lowered = text.lower()
    markers = (
        '"error"',
        '"invalid_request_error"',
        '"code":"invalid_',
        '"code": "invalid_',
        "session is no longer valid",
        "unauthorized",
        "forbidden",
        "incorrect password",
        "captcha",
        "rate limit",
        "too many requests",
    )
    return any(marker in lowered for marker in markers)


def _redact(value: str) -> str:
    value = re.sub(
        r"(?i)(access_token|refresh_token|id_token|code|state|session_token)=([^&\\s]+)",
        r"\1=<redacted>",
        value,
    )
    value = re.sub(r"(?i)(bearer\\s+)[a-z0-9._~-]+", r"\1<redacted>", value)
    value = re.sub(
        r"(?i)(__secure-[^=;\\s]+|oai-[^=;\\s]+|_puid|_cfuvid)=([^;\\s]+)",
        r"\1=<redacted>",
        value,
    )
    return value


def _least_bound_proxy_for_update(session: Session) -> ProxyInventoryModel | None:
    bind_counts = (
        select(
            UserAccountProxyBindingModel.proxy_id.label("proxy_id"),
            func.count(UserAccountProxyBindingModel.id).label("active_bind_count"),
        )
        .where(UserAccountProxyBindingModel.bind_status == ProxyBindStatus.ACTIVE.value)
        .group_by(UserAccountProxyBindingModel.proxy_id)
        .subquery()
    )
    active_bind_count = func.coalesce(bind_counts.c.active_bind_count, 0)
    stmt = (
        select(ProxyInventoryModel)
        .outerjoin(bind_counts, bind_counts.c.proxy_id == ProxyInventoryModel.id)
        .where(
            ProxyInventoryModel.provider == "webshare",
            ProxyInventoryModel.proxy_type == "proxyserver",
            ProxyInventoryModel.proxy_status.in_(
                (ProxyStatus.AVAILABLE.value, ProxyStatus.BOUND.value)
            ),
            ProxyInventoryModel.provider_valid.is_(True),
        )
        .order_by(active_bind_count.asc(), ProxyInventoryModel.updated_at.asc())
        .with_for_update(of=ProxyInventoryModel, skip_locked=True)
        .limit(1)
    )
    return session.scalars(stmt).first()


def _proxy_url(proxy: ProxyInventoryModel) -> str:
    scheme = proxy.proxy_scheme or "http"
    host = proxy.proxy_host
    port = proxy.proxy_port
    if proxy.proxy_username:
        username = quote(proxy.proxy_username, safe="")
        password = quote(proxy.proxy_password or "", safe="")
        return f"{scheme}://{username}:{password}@{host}:{port}"
    return f"{scheme}://{host}:{port}"


def _is_deleted_or_deactivated_account_error(error_message: str) -> bool:
    normalized = " ".join(str(error_message or "").lower().split())
    return (
        "you do not have an account because it has been deleted or deactivated"
        in normalized
    )


def _is_cloudflare_csrf_403_after_retries(exc: Exception) -> bool:
    text = str(exc or "").lower()
    if "cloudflare_csrf_403_after_3_retries" in text:
        return True

    response = getattr(exc, "response", None)
    try:
        status_code = int(getattr(response, "status_code", 0) or 0)
    except Exception:
        status_code = 0
    if status_code != 403:
        return False

    request = getattr(response, "request", None)
    request_url = str(getattr(request, "url", "") or getattr(response, "url", "") or "")
    return "/api/auth/csrf" in request_url


def _probe_proxy_alive(proxy_url: str) -> bool:
    if not proxy_url:
        return False
    try:
        with httpx.Client(proxy=proxy_url, timeout=10.0, follow_redirects=False) as client:
            response = client.get(PROXY_HEALTHCHECK_URL)
            return response.status_code < 500
    except Exception:
        return False


def _fetch_accounts_check_v4(
    *,
    access_token: str,
    cookie_header: str,
    proxy_url: str,
    chatgpt_account_id: str = "",
    oai_device_id: str = "",
) -> dict:
    if not access_token:
        raise AccountAuthWorkflowError("missing_access_token_for_accounts_check")
    if not cookie_header:
        raise AccountAuthWorkflowError("missing_cookie_for_accounts_check")
    headers = {
        "accept": "*/*",
        "accept-language": "zh-CN,zh;q=0.9",
        "authorization": f"Bearer {access_token}",
        "cookie": cookie_header,
        "oai-client-build-number": "7646290",
        "oai-client-version": "prod-497f333866796e100096ad083b51ca949d22e751",
        "oai-language": "zh-CN",
        "oai-session-id": str(uuid4()),
        "priority": "u=1, i",
        "referer": "https://chatgpt.com/admin/members?tab=invites",
        "sec-ch-ua": '"Chromium";v="135", "Not-A.Brand";v="8"',
        "sec-ch-ua-arch": '"arm"',
        "sec-ch-ua-bitness": '"64"',
        "sec-ch-ua-full-version": '"135.0.7049.72"',
        "sec-ch-ua-full-version-list": '"Chromium";v="135.0.7049.72", "Not-A.Brand";v="8.0.0.0"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-model": '""',
        "sec-ch-ua-platform": '"macOS"',
        "sec-ch-ua-platform-version": '"15.6.1"',
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-origin",
        "user-agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/135.0.0.0 Safari/537.36"
        ),
        "x-openai-target-path": "/backend-api/accounts/check/v4-2023-04-27",
        "x-openai-target-route": "/backend-api/accounts/check/{version}",
    }
    if chatgpt_account_id:
        headers["chatgpt-account-id"] = chatgpt_account_id
    if oai_device_id:
        headers["oai-device-id"] = oai_device_id
    proxies = _curl_proxies(proxy_url)
    with curl_requests.Session(impersonate="chrome136", proxies=proxies) as client:
        response = client.get(
            f"{ACCOUNTS_CHECK_URL}?timezone_offset_min=-480",
            headers=headers,
            timeout=30,
        )
    if int(response.status_code or 0) >= 400:
        raise AccountAuthWorkflowError(
            f"accounts_check_failed:http_status={response.status_code}"
        )
    payload = response.json()
    if not isinstance(payload, dict):
        raise AccountAuthWorkflowError("accounts_check_response_not_object")
    return payload


def _extract_personal_chatgpt_account_id(payload: dict) -> str:
    accounts = payload.get("accounts")
    if not isinstance(accounts, dict):
        return ""

    default = accounts.get("default")
    default_id = _personal_account_id_from_entry(default)
    if default_id:
        return default_id

    ordering = payload.get("account_ordering")
    if isinstance(ordering, list):
        for key in ordering:
            entry = accounts.get(str(key))
            account_id = _personal_account_id_from_entry(entry)
            if account_id:
                return account_id

    for entry in accounts.values():
        account_id = _personal_account_id_from_entry(entry)
        if account_id:
            return account_id
    return ""


def _extract_visible_chatgpt_account_ids(payload: dict) -> set[str]:
    accounts = payload.get("accounts")
    if not isinstance(accounts, dict):
        return set()

    result: set[str] = set()
    for key, entry in accounts.items():
        key_text = str(key or "").strip()
        if key_text and key_text != "default":
            result.add(key_text)
        entry_id = _account_id_from_entry(entry)
        if entry_id:
            result.add(entry_id)
    return result


def _account_id_from_entry(entry: object) -> str:
    if not isinstance(entry, dict):
        return ""
    account = entry.get("account")
    if isinstance(account, dict):
        value = account.get("account_id") or account.get("accountId") or account.get("id")
        if value:
            return str(value).strip()
    return str(
        entry.get("account_id")
        or entry.get("accountId")
        or entry.get("id")
        or ""
    ).strip()


def _personal_account_id_from_entry(entry: object) -> str:
    if not isinstance(entry, dict):
        return ""
    account = entry.get("account")
    if not isinstance(account, dict):
        return ""
    structure = str(account.get("structure") or entry.get("structure") or "").lower()
    if structure != "personal":
        return ""
    return str(
        account.get("account_id")
        or account.get("accountId")
        or account.get("id")
        or entry.get("account_id")
        or entry.get("id")
        or ""
    ).strip()


def _curl_proxies(proxy_url: str) -> dict[str, str] | None:
    proxy_url = str(proxy_url or "")
    if not proxy_url:
        return None
    if proxy_url.startswith("socks5://"):
        proxy_url = proxy_url.replace("socks5://", "socks5h://", 1)
    return {"http": proxy_url, "https": proxy_url}


def _keep_existing_if_empty(existing: str, candidate: str) -> str:
    candidate = str(candidate or "")
    return candidate if candidate else existing


def _ensure_session_token_cookie(cookie_header: str, session_token: str) -> str:
    session_token = str(session_token or "")
    cookie_header = str(cookie_header or "")
    name = "__Secure-next-auth.session-token"
    if not session_token or f"{name}=" in cookie_header:
        return cookie_header
    if not cookie_header:
        return f"{name}={session_token}"
    return f"{name}={session_token}; {cookie_header}"
