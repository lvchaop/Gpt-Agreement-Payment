from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from time import sleep
from typing import Any

from sqlalchemy.orm import Session

from refactor_app.application.workflows.proxy import ensure_team_admin_static_proxy_url_in_session
from refactor_app.infrastructure.db.models import SpaceModel, TeamAdminSessionModel
from refactor_app.infrastructure.logging.event_writer import EventWriter
from refactor_app.plugins.contracts import OpenAIChatGPTProvider

TARGET_SEATS = 999
MIN_SEAT_INCREASE = 1
MAX_SEAT_INCREASE = 15
REQUEST_DELAY_MS = 250
MAX_NO_PROGRESS_COUNT = 10
MAX_HTTP_FAILURE_COUNT = 10

SessionFactory = Callable[[], Session]


class SpaceSeatExpansionError(RuntimeError):
    pass


@dataclass(frozen=True)
class SpaceSeatExpansionContext:
    space_id: str
    external_space_id: str
    team_admin_session_id: str
    access_token: str
    cookie_header: str
    proxy_url: str


def next_seat_count(current_seats: int) -> int:
    if current_seats < 1:
        raise SpaceSeatExpansionError(f"current seats must be positive: {current_seats}")
    increase = min(MAX_SEAT_INCREASE, max(MIN_SEAT_INCREASE, current_seats - 1))
    return min(TARGET_SEATS, current_seats + increase)


class SpaceSeatExpansionWorkflow:
    def __init__(
        self,
        *,
        session_factory: SessionFactory,
        openai_provider: OpenAIChatGPTProvider,
        sleep_fn: Callable[[float], None] = sleep,
    ) -> None:
        self._session_factory = session_factory
        self._openai_provider = openai_provider
        self._sleep = sleep_fn

    def run(
        self,
        *,
        space_id: str,
        run_id: str = "",
        work_id: str = "",
    ) -> dict[str, Any]:
        context = self._load_context(space_id=space_id)
        subscription, fetch_failures = self._fetch_subscription_with_retries(
            context=context,
            run_id=run_id,
            work_id=work_id,
            stage="initial",
        )
        self._write_subscription_snapshot(space_id=space_id, subscription=subscription)
        current_seats = _subscription_seats(subscription)
        initial_seats = current_seats
        no_progress_count = 0
        http_failure_count = fetch_failures
        update_count = 0

        while current_seats < TARGET_SEATS:
            updated_seats = next_seat_count(current_seats)
            update_failures = self._update_seats_with_retries(
                context=context,
                updated_seats=updated_seats,
                run_id=run_id,
                work_id=work_id,
            )
            http_failure_count += update_failures
            update_count += 1
            self._sleep(REQUEST_DELAY_MS / 1000)

            subscription, fetch_failures = self._fetch_subscription_with_retries(
                context=context,
                run_id=run_id,
                work_id=work_id,
                stage="verify",
            )
            http_failure_count += fetch_failures
            self._write_subscription_snapshot(space_id=space_id, subscription=subscription)
            observed_seats = _subscription_seats(subscription)
            if observed_seats <= current_seats:
                no_progress_count += 1
            else:
                no_progress_count = 0

            self._write_event(
                run_id=run_id,
                event_type="space.seat_expand.verified",
                message="space seat expansion verified",
                data_json={
                    "work_id": work_id,
                    "space_id": space_id,
                    "external_space_id": context.external_space_id,
                    "previous_seats": current_seats,
                    "requested_seats": updated_seats,
                    "observed_seats": observed_seats,
                    "no_progress_count": no_progress_count,
                    "max_no_progress_count": MAX_NO_PROGRESS_COUNT,
                },
            )
            if no_progress_count >= MAX_NO_PROGRESS_COUNT:
                raise SpaceSeatExpansionError(
                    "space seat expansion made no progress: "
                    f"space_id={space_id} current={current_seats} requested={updated_seats} "
                    f"observed={observed_seats} count={no_progress_count}"
                )
            current_seats = max(current_seats, observed_seats)

        return {
            "space_id": space_id,
            "external_space_id": context.external_space_id,
            "initial_seats": initial_seats,
            "final_seats": current_seats,
            "target_seats": TARGET_SEATS,
            "update_count": update_count,
            "http_failure_count": http_failure_count,
            "no_progress_count": no_progress_count,
        }

    def _load_context(self, *, space_id: str) -> SpaceSeatExpansionContext:
        with self._session_factory() as session:
            space = session.get(SpaceModel, space_id)
            if space is None:
                raise SpaceSeatExpansionError(f"space not found: {space_id}")
            if space.space_type != "business":
                raise SpaceSeatExpansionError(f"space is not business: {space_id}")
            if space.space_status != "active":
                raise SpaceSeatExpansionError(
                    f"space is not active: space_id={space_id} status={space.space_status}"
                )
            if not space.external_space_id:
                raise SpaceSeatExpansionError(f"space external id is missing: {space_id}")
            if not space.source_admin_session_id:
                raise SpaceSeatExpansionError(f"space admin session is missing: {space_id}")

            admin_session = session.get(TeamAdminSessionModel, space.source_admin_session_id)
            if admin_session is None:
                raise SpaceSeatExpansionError(
                    f"team admin session not found: {space.source_admin_session_id}"
                )
            if not admin_session.access_token:
                raise SpaceSeatExpansionError(
                    f"team admin access token is missing: {admin_session.id}"
                )
            proxy_url = ensure_team_admin_static_proxy_url_in_session(
                session=session,
                team_admin_session_id=admin_session.id,
                bind_reason="space_seat_expansion",
            )
            context = SpaceSeatExpansionContext(
                space_id=space.id,
                external_space_id=space.external_space_id,
                team_admin_session_id=admin_session.id,
                access_token=admin_session.access_token,
                cookie_header=admin_session.cookie_header,
                proxy_url=proxy_url,
            )
            session.commit()
            return context

    def _fetch_subscription_with_retries(
        self,
        *,
        context: SpaceSeatExpansionContext,
        run_id: str,
        work_id: str,
        stage: str,
    ) -> tuple[dict, int]:
        for failure_count in range(MAX_HTTP_FAILURE_COUNT):
            try:
                payload = self._openai_provider.fetch_subscription(
                    access_token=context.access_token,
                    account_id=context.external_space_id,
                    cookie_header=context.cookie_header,
                    proxy_url=context.proxy_url,
                )
                _subscription_seats(payload)
                return payload, failure_count
            except Exception as exc:
                current_failure_count = failure_count + 1
                self._write_http_failure_event(
                    run_id=run_id,
                    work_id=work_id,
                    context=context,
                    operation=f"fetch_subscription:{stage}",
                    failure_count=current_failure_count,
                    error=exc,
                )
                if current_failure_count >= MAX_HTTP_FAILURE_COUNT:
                    raise SpaceSeatExpansionError(
                        "subscription query reached HTTP failure limit: "
                        f"space_id={context.space_id} stage={stage} "
                        f"failures={current_failure_count} error={type(exc).__name__}: {exc}"
                    ) from exc
                self._sleep(REQUEST_DELAY_MS / 1000)
        raise AssertionError("unreachable")

    def _update_seats_with_retries(
        self,
        *,
        context: SpaceSeatExpansionContext,
        updated_seats: int,
        run_id: str,
        work_id: str,
    ) -> int:
        for failure_count in range(MAX_HTTP_FAILURE_COUNT):
            try:
                self._openai_provider.update_subscription_seats(
                    access_token=context.access_token,
                    account_id=context.external_space_id,
                    updated_seats=updated_seats,
                    cookie_header=context.cookie_header,
                    proxy_url=context.proxy_url,
                )
                self._write_event(
                    run_id=run_id,
                    event_type="space.seat_expand.updated",
                    message="space seat update accepted",
                    data_json={
                        "work_id": work_id,
                        "space_id": context.space_id,
                        "external_space_id": context.external_space_id,
                        "updated_seats": updated_seats,
                        "http_failures_before_success": failure_count,
                    },
                )
                return failure_count
            except Exception as exc:
                current_failure_count = failure_count + 1
                self._write_http_failure_event(
                    run_id=run_id,
                    work_id=work_id,
                    context=context,
                    operation="update_subscription_seats",
                    failure_count=current_failure_count,
                    error=exc,
                    updated_seats=updated_seats,
                )
                if current_failure_count >= MAX_HTTP_FAILURE_COUNT:
                    raise SpaceSeatExpansionError(
                        "seat update reached HTTP failure limit: "
                        f"space_id={context.space_id} updated_seats={updated_seats} "
                        f"failures={current_failure_count} error={type(exc).__name__}: {exc}"
                    ) from exc
                self._sleep(REQUEST_DELAY_MS / 1000)
        raise AssertionError("unreachable")

    def _write_subscription_snapshot(self, *, space_id: str, subscription: dict) -> None:
        seats_entitled = _subscription_seats(subscription)
        seats_in_use = _optional_nonnegative_int(
            subscription.get("seats_in_use", subscription.get("seatsInUse"))
        )
        now = datetime.now(UTC)
        with self._session_factory() as session:
            space = session.get(SpaceModel, space_id)
            if space is None:
                raise SpaceSeatExpansionError(f"space disappeared: {space_id}")
            space.seats_entitled = seats_entitled
            space.seat_limit = seats_entitled
            if seats_in_use is not None:
                space.seats_in_use = seats_in_use
            plan_type = str(
                subscription.get("plan_type") or subscription.get("planType") or ""
            ).strip()
            if plan_type:
                space.plan_type = plan_type
            space.raw_space_json = subscription
            space.last_subscription_sync_at = now
            space.updated_at = now
            session.commit()

    def _write_http_failure_event(
        self,
        *,
        run_id: str,
        work_id: str,
        context: SpaceSeatExpansionContext,
        operation: str,
        failure_count: int,
        error: Exception,
        updated_seats: int | None = None,
    ) -> None:
        data_json: dict[str, Any] = {
            "work_id": work_id,
            "space_id": context.space_id,
            "external_space_id": context.external_space_id,
            "operation": operation,
            "http_failure_count": failure_count,
            "max_http_failure_count": MAX_HTTP_FAILURE_COUNT,
            "error": f"{type(error).__name__}: {error}",
        }
        if updated_seats is not None:
            data_json["updated_seats"] = updated_seats
        self._write_event(
            run_id=run_id,
            event_type="space.seat_expand.http_failed",
            message="space seat expansion HTTP request failed",
            level="ERROR",
            data_json=data_json,
        )

    def _write_event(
        self,
        *,
        run_id: str,
        event_type: str,
        message: str,
        data_json: dict[str, Any],
        level: str = "INFO",
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
            )
            session.commit()


def _subscription_seats(subscription: dict) -> int:
    value = subscription.get("seats_entitled", subscription.get("seatsEntitled"))
    if isinstance(value, bool):
        raise SpaceSeatExpansionError("subscription seats_entitled must be an integer")
    try:
        seats = int(value)
    except (TypeError, ValueError) as exc:
        raise SpaceSeatExpansionError(
            f"subscription response is missing seats_entitled: {value!r}"
        ) from exc
    if seats < 1:
        raise SpaceSeatExpansionError(f"subscription seats_entitled must be positive: {seats}")
    return seats


def _optional_nonnegative_int(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= 0 else None
