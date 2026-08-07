from __future__ import annotations

import argparse
from pathlib import Path
from urllib.parse import quote

import uvicorn
from invite_executor.api import create_app
from invite_executor.proxy_pool import (
    StaticProxyAssignment,
    backbone_username_for_country,
)
from invite_executor.replenishment_models import ReplenishmentRegistration
from invite_executor.replenishment_registry import ReplenishmentRegistry
from invite_executor.settings import InviteExecutorSettings
from sqlalchemy import select

from refactor_app.application.workflows.downstream_provider import (
    parse_downstream_group_ids,
)
from refactor_app.application.workflows.proxy import (
    ensure_team_admin_static_proxy_url_in_session,
)
from refactor_app.application.workflows.space_auto_replenish import (
    _team_admin_cookie_header,
)
from refactor_app.config.settings import get_settings
from refactor_app.infrastructure.db.engine import make_engine, make_session_factory
from refactor_app.infrastructure.db.models import (
    DownstreamChannelModel,
    ProxyInventoryModel,
    SpaceModel,
    TeamAdminSessionModel,
)
from refactor_app.plugins.openai_chatgpt.client import decode_access_token_claims


def _country_proxy_url(proxy: ProxyInventoryModel, *, country_code: str) -> str:
    scheme = str(proxy.proxy_scheme or "http").strip() or "http"
    username = backbone_username_for_country(proxy.proxy_username, country_code)
    password = str(proxy.proxy_password or "")
    return (
        f"{scheme}://{quote(username, safe='')}:{quote(password, safe='')}"
        f"@{proxy.proxy_host}:{int(proxy.proxy_port)}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Run one real Space under local invite-executor")
    parser.add_argument("--space-id", required=True)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--interval-seconds", type=float, default=120.0)
    parser.add_argument(
        "--registry-path",
        default="/private/tmp/invite-executor-local-replenishment.json",
    )
    args = parser.parse_args()
    account_proxy_count = 1000

    app_settings = get_settings()
    engine = make_engine(app_settings)
    session_factory = make_session_factory(engine)
    try:
        with session_factory() as session:
            space = session.get(SpaceModel, args.space_id)
            if space is None:
                raise RuntimeError(f"space not found: {args.space_id}")
            if space.space_type != "business" or space.space_status != "active":
                raise RuntimeError("local test requires an active Business space")
            admin = session.get(TeamAdminSessionModel, space.source_admin_session_id)
            if admin is None or not admin.access_token:
                raise RuntimeError("Business space administrator session is incomplete")
            channels = list(
                session.scalars(
                    select(DownstreamChannelModel)
                    .where(DownstreamChannelModel.enabled.is_(True))
                    .order_by(DownstreamChannelModel.created_at)
                ).all()
            )
            compatible_channels = [
                channel
                for channel in channels
                if channel.provider_type == "sub2api"
                or channel.custom_payload_type in {"sub2api", "sub2api_admin_accounts"}
            ]
            if len(compatible_channels) != 1:
                raise RuntimeError(
                    "local test requires exactly one enabled Sub2API-compatible channel: "
                    f"actual={len(compatible_channels)}"
                )
            channel = compatible_channels[0]
            group_ids = parse_downstream_group_ids(channel.sub2api_group_ids)
            if not group_ids:
                raise RuntimeError(
                    f"local test requires at least one Sub2API group ID: actual={group_ids}"
                )
            downstream_key = (
                str(channel.admin_key or "").strip()
                or str(channel.custom_auth_header_value or "").strip()
            )
            if not downstream_key:
                raise RuntimeError("Sub2API-compatible channel has no administrator key")
            admin_proxy_url = ensure_team_admin_static_proxy_url_in_session(
                session=session,
                team_admin_session_id=admin.id,
                bind_reason="local_invite_executor_replenishment_test",
            )
            session.commit()

            admin_user_id = ""
            try:
                admin_user_id = decode_access_token_claims(admin.access_token).account_id
            except Exception:
                pass
            registry = ReplenishmentRegistry(Path(args.registry_path))
            registry.register_from_invitation(
                external_space_id=space.external_space_id,
                registration=ReplenishmentRegistration(
                    admin_key=(admin.admin_email or admin.id).strip().casefold(),
                    admin_email=admin.admin_email,
                    admin_user_id=admin_user_id,
                    name=space.name,
                    enabled=True,
                    credential_type=space.credential_type,
                    seat_limit=max(1, int(space.seat_limit or 1)),
                    admin_proxy_url=admin_proxy_url,
                ),
                access_token=admin.access_token,
                cookie_header=_team_admin_cookie_header(admin),
            )
            external_space_id = space.external_space_id
            channel_base_url = channel.base_url
            channel_header = channel.custom_auth_header_name or "x-api-key"
            group_id = group_ids[0]
            account_proxies = list(
                session.scalars(
                    select(ProxyInventoryModel)
                    .where(
                        ProxyInventoryModel.provider == "webshare",
                        ProxyInventoryModel.proxy_type == "static_proxy",
                        ProxyInventoryModel.proxy_status == "available",
                        ProxyInventoryModel.provider_valid.is_(True),
                    )
                    .order_by(
                        ProxyInventoryModel.updated_at.asc(),
                        ProxyInventoryModel.id.asc(),
                    )
                    .limit(account_proxy_count)
                ).all()
            )
            if len(account_proxies) != account_proxy_count:
                raise RuntimeError(
                    "local test has insufficient usable static account proxies: "
                    f"required={account_proxy_count} actual={len(account_proxies)}"
                )
            local_proxy_assignments = tuple(
                StaticProxyAssignment(
                    slot=index,
                    endpoint_id=proxy.id,
                    proxy_url=_country_proxy_url(proxy, country_code="JP"),
                )
                for index, proxy in enumerate(account_proxies, start=1)
            )
    finally:
        engine.dispose()

    private_settings = InviteExecutorSettings(
        _env_file="packages/invite-executor/.env",
    )
    settings = InviteExecutorSettings(
        api_key=app_settings.session_otp_executor_api_key,
        host=args.host,
        port=args.port,
        chatgpt_base_url=app_settings.openai_chatgpt_base_url,
        static_proxy_gateway_host=account_proxies[0].proxy_host,
        static_proxy_gateway_port=account_proxies[0].proxy_port,
        static_proxy_username=account_proxies[0].proxy_username.rsplit("-", 1)[0],
        static_proxy_password=account_proxies[0].proxy_password,
        static_proxy_country="US",
        auto_replenish_enabled=True,
        auto_replenish_interval_s=args.interval_seconds,
        auto_replenish_max_workers=1,
        auto_replenish_browser_headless=True,
        auto_replenish_registry_path=args.registry_path,
        auto_replenish_account_proxy_count=account_proxy_count,
        auto_replenish_account_proxy_country="JP",
        auto_replenish_candidate_failure_cooldown_s=0,
        auto_replenish_sub2api_base_url=channel_base_url,
        auto_replenish_sub2api_api_key=downstream_key,
        auto_replenish_sub2api_api_key_header=channel_header,
        auto_replenish_sub2api_group_id=group_id,
        auto_replenish_sub2api_group_ids=",".join(str(value) for value in group_ids),
        auto_replenish_mail_base_url=app_settings.external_mail_api_base_url,
        auto_replenish_mail_api_key=app_settings.external_mail_api_key,
        auto_replenish_mail_provider_name=app_settings.external_mail_provider_name,
        auto_replenish_grizzly_sms_api_key=(private_settings.auto_replenish_grizzly_sms_api_key),
        _env_file=None,
    )
    settings.validate_auto_replenishment()
    print(
        "local real replenishment starting: "
        f"space={external_space_id} interval_s={settings.auto_replenish_interval_s} "
        f"grizzly_configured={bool(settings.auto_replenish_grizzly_sms_api_key)}"
    )

    def allocate_local_static_proxies(count: int) -> list[StaticProxyAssignment]:
        required = max(0, int(count))
        if required > len(local_proxy_assignments):
            raise RuntimeError(
                "local static account proxy inventory was exhausted: "
                f"required={required} available={len(local_proxy_assignments)}"
            )
        return list(local_proxy_assignments[:required])

    uvicorn.run(
        create_app(
            settings,
            replenishment_proxy_allocator=allocate_local_static_proxies,
        ),
        host=settings.host,
        port=settings.port,
        workers=1,
        log_level=settings.log_level,
    )


if __name__ == "__main__":
    main()
