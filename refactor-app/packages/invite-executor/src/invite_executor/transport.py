from __future__ import annotations

import asyncio
from collections import Counter
from dataclasses import dataclass
from typing import Protocol
from urllib.parse import urlsplit, urlunsplit

from curl_cffi import requests as curl_requests
from curl_cffi.aio import CURLPIPE_MULTIPLEX
from curl_cffi.const import CurlInfo, CurlMOpt
from curl_cffi.requests.exceptions import Timeout as CurlTimeout
from refactor_app.config.browser_fingerprint import (
    BROWSER_IMPERSONATE,
    BROWSER_USER_AGENT,
)
from refactor_app.plugins.openai_chatgpt.client import (
    OpenAIChatGPTTimeoutError,
    PreparedChatGPTInviteRequest,
    parse_chatgpt_response_payload,
    validate_invite_member_payload,
)

from invite_executor.proxy_pool import StaticProxyAssignment, StaticProxyEndpoint


class InviteConnectionPreparationError(RuntimeError):
    pass


@dataclass(frozen=True)
class PreparedInvite:
    index: int
    email: str
    proxy_assignment: StaticProxyAssignment
    upstream: PreparedChatGPTInviteRequest


@dataclass(frozen=True)
class WarmupReport:
    target_count: int
    completed_count: int
    rounds: int
    http_versions: tuple[int, ...]
    unique_local_ports: int
    reuse_validated_count: int = 0
    opened_during_reuse_validation: int = 0


class AsyncInviteTransport(Protocol):
    async def prewarm(self, prepared: list[PreparedInvite]) -> WarmupReport: ...

    async def send(self, prepared: PreparedInvite) -> dict: ...

    async def close(self) -> None: ...


class ExistingAsyncInviteTransport:
    def __init__(
        self,
        *,
        chatgpt_base_url: str,
        request_timeout_s: float,
        max_clients: int,
        max_streams_per_proxy: int,
        prewarm_rounds: int,
        prewarm_attempts: int,
        prewarm_start_interval_s: float = 0.02,
        prewarm_keepalive_interval_s: float = 5.0,
        prewarm_timeout_s: float = 5.0,
    ) -> None:
        self._chatgpt_base_url = chatgpt_base_url.rstrip("/")
        self._request_timeout_s = max(1.0, float(request_timeout_s))
        self._prewarm_rounds = max(1, int(prewarm_rounds))
        self._prewarm_attempts = max(1, int(prewarm_attempts))
        self._prewarm_start_interval_s = max(0.0, float(prewarm_start_interval_s))
        self._prewarm_keepalive_interval_s = max(
            0.1,
            float(prewarm_keepalive_interval_s),
        )
        self._prewarm_timeout_s = max(1.0, float(prewarm_timeout_s))
        self._max_clients = max(1, int(max_clients))
        self._max_streams_per_proxy = max(1, int(max_streams_per_proxy))
        self._proxy_url_by_index: dict[int, str] = {}
        self._proxy_endpoint_id_by_index: dict[int, str] = {}
        self._proxy_routes_by_index: dict[int, tuple[tuple[str, str], ...]] = {}
        self._proxy_route_position_by_index: dict[int, int] = {}
        self._sessions: dict[int, curl_requests.AsyncSession] = {}

    async def prewarm(self, prepared: list[PreparedInvite]) -> WarmupReport:
        if not prepared:
            return WarmupReport(
                target_count=0,
                completed_count=0,
                rounds=self._prewarm_rounds,
                http_versions=(),
                unique_local_ports=0,
            )
        if len(prepared) > self._max_clients:
            raise InviteConnectionPreparationError(
                f"prepared invite count exceeds transport capacity: "
                f"prepared={len(prepared)} capacity={self._max_clients}"
            )

        for item in prepared:
            routes = _proxy_routes(item.proxy_assignment)
            self._proxy_routes_by_index[item.index] = routes
            self._proxy_route_position_by_index[item.index] = 0
            self._proxy_endpoint_id_by_index[item.index] = routes[0][0]
            self._proxy_url_by_index[item.index] = routes[0][1]
        self._sessions = {}
        for item in prepared:
            session = self._new_session()
            self._configure_session(item, session)
            self._sessions[item.index] = session
        http_versions: set[int] = set()
        final_round_local_ports: set[int] = set()
        prewarm_order = [item for wave in _prewarm_waves(prepared) for item in wave]
        keepalive_stop = asyncio.Event()
        keepalive_tasks: list[asyncio.Task] = []
        try:
            initial_outcomes = await asyncio.gather(
                *(
                    self._establish_and_start_keepalive(
                        item,
                        position,
                        keepalive_stop,
                        keepalive_tasks,
                    )
                    for position, item in enumerate(prewarm_order)
                ),
                return_exceptions=True,
            )
            initial_errors = [
                outcome for outcome in initial_outcomes if isinstance(outcome, Exception)
            ]
            if initial_errors:
                raise _connection_stage_error(
                    stage="connection prewarm",
                    remaining=len(initial_errors),
                    attempts=self._prewarm_attempts,
                    errors=initial_errors,
                )

            round_responses = list(initial_outcomes)
            for _ in range(1, self._prewarm_rounds):
                round_outcomes = await asyncio.gather(
                    *(self._warm_with_retries(item) for item in prewarm_order),
                    return_exceptions=True,
                )
                round_errors = [
                    outcome for outcome in round_outcomes if isinstance(outcome, Exception)
                ]
                if round_errors:
                    raise _connection_stage_error(
                        stage="connection prewarm",
                        remaining=len(round_errors),
                        attempts=self._prewarm_attempts,
                        errors=round_errors,
                    )
                round_responses = list(round_outcomes)

            for response in round_responses:
                http_versions.add(int(response.http_version or 0))
                if int(response.local_port or 0) > 0:
                    final_round_local_ports.add(int(response.local_port))
        finally:
            keepalive_stop.set()
            if keepalive_tasks:
                await asyncio.gather(*keepalive_tasks, return_exceptions=True)

        reuse_validated_count, opened_during_reuse_validation = await self._validate_reuse(
            prewarm_order
        )

        return WarmupReport(
            target_count=len(prepared),
            completed_count=len(prepared) * self._prewarm_rounds,
            rounds=self._prewarm_rounds,
            http_versions=tuple(sorted(http_versions)),
            unique_local_ports=len(final_round_local_ports),
            reuse_validated_count=reuse_validated_count,
            opened_during_reuse_validation=opened_during_reuse_validation,
        )

    async def send(self, prepared: PreparedInvite) -> dict:
        try:
            response = await self._session(prepared).post(
                f"{self._chatgpt_base_url}{prepared.upstream.path}",
                headers=prepared.upstream.headers,
                json=prepared.upstream.json_body,
                proxy=self._proxy_url(prepared),
                timeout=self._request_timeout_s,
            )
        except CurlTimeout as exc:
            raise OpenAIChatGPTTimeoutError(
                "chatgpt backend request timed out after "
                f"{self._request_timeout_s:g}s: path={prepared.upstream.path}"
            ) from exc
        payload = parse_chatgpt_response_payload(response)
        return validate_invite_member_payload(email=prepared.email, payload=payload)

    async def close(self) -> None:
        sessions = list(self._sessions.values())
        self._sessions.clear()
        self._proxy_url_by_index.clear()
        self._proxy_endpoint_id_by_index.clear()
        self._proxy_routes_by_index.clear()
        self._proxy_route_position_by_index.clear()
        if sessions:
            await asyncio.gather(*(session.close() for session in sessions))

    def proxy_endpoint_id(self, prepared: PreparedInvite) -> str:
        return self._proxy_endpoint_id_by_index.get(
            prepared.index,
            prepared.proxy_assignment.endpoint_id,
        )

    async def _warm_one(self, prepared: PreparedInvite):
        return await self._session(prepared).request(
            "HEAD",
            f"{self._chatgpt_base_url}/",
            headers={
                "accept": "text/html,*/*",
                "user-agent": BROWSER_USER_AGENT,
            },
            proxy=self._proxy_url(prepared),
            timeout=self._prewarm_timeout_s,
            allow_redirects=False,
        )

    def _new_session(self) -> curl_requests.AsyncSession:
        session = curl_requests.AsyncSession(
            max_clients=1,
            impersonate=BROWSER_IMPERSONATE,
            timeout=self._request_timeout_s,
            curl_infos=[CurlInfo.CONN_ID, CurlInfo.NUM_CONNECTS],
        )
        session.acurl.setopt(CurlMOpt.PIPELINING, CURLPIPE_MULTIPLEX)
        session.acurl.setopt(CurlMOpt.MAXCONNECTS, 2)
        session.acurl.setopt(CurlMOpt.MAX_TOTAL_CONNECTIONS, 1)
        session.acurl.setopt(
            CurlMOpt.MAX_CONCURRENT_STREAMS,
            self._max_streams_per_proxy,
        )
        return session

    def _configure_session(
        self,
        prepared: PreparedInvite,
        session: curl_requests.AsyncSession,
    ) -> None:
        return None

    def _session(self, prepared: PreparedInvite) -> curl_requests.AsyncSession:
        try:
            return self._sessions[prepared.index]
        except KeyError as exc:
            raise InviteConnectionPreparationError(
                f"invite transport session is not prepared: index={prepared.index}"
            ) from exc

    async def _warm_after_delay(self, prepared: PreparedInvite, position: int):
        delay_s = position * self._prewarm_start_interval_s
        if delay_s > 0:
            await asyncio.sleep(delay_s)
        return await self._warm_one(prepared)

    async def _establish_and_start_keepalive(
        self,
        prepared: PreparedInvite,
        position: int,
        stop_event: asyncio.Event,
        keepalive_tasks: list[asyncio.Task],
    ):
        delay_s = position * self._prewarm_start_interval_s
        if delay_s > 0:
            await asyncio.sleep(delay_s)
        response = await self._warm_with_retries(prepared)
        keepalive_tasks.append(
            asyncio.create_task(self._keep_connection_alive(prepared, stop_event))
        )
        return response

    async def _warm_with_retries(self, prepared: PreparedInvite):
        last_error: Exception | None = None
        for _ in range(self._prewarm_attempts):
            try:
                return await self._warm_one(prepared)
            except Exception as exc:
                last_error = exc
                self._rotate_gateway(prepared)
        raise InviteConnectionPreparationError(
            "connection request failed after "
            f"{self._prewarm_attempts} attempts: "
            f"error={type(last_error).__name__ if last_error else 'unknown'}"
        ) from last_error

    async def _keep_connection_alive(
        self,
        prepared: PreparedInvite,
        stop_event: asyncio.Event,
    ) -> None:
        while not stop_event.is_set():
            try:
                await asyncio.wait_for(
                    stop_event.wait(),
                    timeout=self._prewarm_keepalive_interval_s,
                )
                return
            except TimeoutError:
                try:
                    await self._warm_one(prepared)
                except Exception:
                    self._rotate_gateway(prepared)

    async def _validate_reuse(
        self,
        prepared: list[PreparedInvite],
    ) -> tuple[int, int]:
        outcomes = await asyncio.gather(
            *(self._warm_with_retries(item) for item in prepared),
            return_exceptions=True,
        )
        errors = [outcome for outcome in outcomes if isinstance(outcome, Exception)]
        if errors:
            raise _connection_stage_error(
                stage="connection reuse validation",
                remaining=len(errors),
                attempts=self._prewarm_attempts,
                errors=errors,
            )
        return len(outcomes), sum(
            int(outcome.infos.get(CurlInfo.NUM_CONNECTS, 0) or 0) for outcome in outcomes
        )

    def _proxy_url(self, prepared: PreparedInvite) -> str:
        return self._proxy_url_by_index.get(
            prepared.index,
            prepared.proxy_assignment.proxy_url,
        )

    def _rotate_gateway(self, prepared: PreparedInvite) -> None:
        routes = self._proxy_routes_by_index.get(prepared.index, ())
        if len(routes) < 2:
            return
        next_position = (self._proxy_route_position_by_index.get(prepared.index, 0) + 1) % len(
            routes
        )
        endpoint_id, proxy_url = routes[next_position]
        self._proxy_route_position_by_index[prepared.index] = next_position
        self._proxy_endpoint_id_by_index[prepared.index] = endpoint_id
        self._proxy_url_by_index[prepared.index] = proxy_url


def _prewarm_waves(prepared: list[PreparedInvite]) -> list[list[PreparedInvite]]:
    by_proxy_slot: dict[int, list[PreparedInvite]] = {}
    for item in prepared:
        by_proxy_slot.setdefault(item.proxy_assignment.slot, []).append(item)
    groups = list(by_proxy_slot.values())
    return [
        [group[offset] for group in groups if offset < len(group)]
        for offset in range(max((len(group) for group in groups), default=0))
    ]


def _proxy_routes(
    assignment: StaticProxyAssignment,
) -> tuple[tuple[str, str], ...]:
    endpoints = (
        StaticProxyEndpoint(
            endpoint_id=assignment.endpoint_id,
            proxy_url=assignment.proxy_url,
            gateway_host=assignment.gateway_host,
            gateway_ip=assignment.gateway_ip,
            gateway_ips=assignment.gateway_ips,
        ),
        *assignment.fallback_endpoints,
    )
    gateway_lists = [_ordered_gateway_ips(endpoint) for endpoint in endpoints]
    routes: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for gateway_offset in range(max(map(len, gateway_lists), default=0)):
        for endpoint, gateway_ips in zip(endpoints, gateway_lists, strict=True):
            if gateway_offset >= len(gateway_ips):
                continue
            route = (
                endpoint.endpoint_id,
                _replace_proxy_host(
                    endpoint.proxy_url,
                    gateway_ips[gateway_offset],
                ),
            )
            if route in seen:
                continue
            seen.add(route)
            routes.append(route)
    if routes:
        return tuple(routes)
    return ((assignment.endpoint_id, assignment.proxy_url),)


def _ordered_gateway_ips(endpoint: StaticProxyEndpoint) -> tuple[str, ...]:
    gateway_ips = list(dict.fromkeys(endpoint.gateway_ips))
    if endpoint.gateway_ip in gateway_ips:
        gateway_ips.remove(endpoint.gateway_ip)
        gateway_ips.insert(0, endpoint.gateway_ip)
    if gateway_ips:
        return tuple(gateway_ips)
    current_host = str(urlsplit(endpoint.proxy_url).hostname or "")
    return (current_host,) if current_host else ()


def _replace_proxy_host(proxy_url: str, host: str) -> str:
    parsed = urlsplit(proxy_url)
    credentials, separator, _ = parsed.netloc.rpartition("@")
    if not separator or parsed.port is None:
        return proxy_url
    return urlunsplit(
        (
            parsed.scheme,
            f"{credentials}@{host}:{parsed.port}",
            parsed.path,
            parsed.query,
            parsed.fragment,
        )
    )


def _connection_stage_error(
    *,
    stage: str,
    remaining: int,
    attempts: int,
    errors: list[Exception],
) -> InviteConnectionPreparationError:
    error_counts = Counter(type(error).__name__ for error in errors)
    error_summary = ",".join(
        f"{error_type}={count}" for error_type, count in sorted(error_counts.items())
    )
    return InviteConnectionPreparationError(
        f"{stage} failed: remaining={remaining} attempts={attempts} "
        f"errors={error_summary or 'unknown'}"
    )
