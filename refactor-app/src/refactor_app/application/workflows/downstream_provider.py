from __future__ import annotations

from refactor_app.infrastructure.db.models import DownstreamChannelModel
from refactor_app.plugins.downstream_cpa.client import CpaClientConfig
from refactor_app.plugins.downstream_cpa.plugin import CpaDownstreamPlugin
from refactor_app.plugins.downstream_custom_http.client import CustomHttpClientConfig
from refactor_app.plugins.downstream_custom_http.plugin import CustomHttpDownstreamPlugin
from refactor_app.plugins.downstream_local_sub2api.client import LocalSub2ApiClientConfig
from refactor_app.plugins.downstream_local_sub2api.plugin import LocalSub2ApiDownstreamPlugin
from refactor_app.plugins.downstream_sub2api.client import Sub2ApiClientConfig
from refactor_app.plugins.downstream_sub2api.plugin import Sub2ApiDownstreamPlugin


class DownstreamProviderFactoryError(RuntimeError):
    pass


def provider_from_channel(channel: DownstreamChannelModel):
    if channel.provider_type == "sub2api":
        return Sub2ApiDownstreamPlugin.from_config(
            Sub2ApiClientConfig(
                base_url=channel.base_url,
                admin_key=channel.admin_key,
                timeout_s=channel.timeout_s,
                update_existing=channel.update_existing,
                concurrency=channel.sub2api_concurrency,
                group_ids=parse_downstream_group_ids(channel.sub2api_group_ids),
            )
        )
    if channel.provider_type == "cpa":
        return CpaDownstreamPlugin.from_config(
            CpaClientConfig(
                base_url=channel.base_url,
                admin_key=channel.admin_key,
                timeout_s=channel.timeout_s,
            )
        )
    if channel.provider_type == "local_sub2api":
        return LocalSub2ApiDownstreamPlugin.from_config(
            LocalSub2ApiClientConfig(
                output_dir=channel.base_url,
                update_existing=channel.update_existing,
                concurrency=channel.sub2api_concurrency,
                group_ids=parse_downstream_group_ids(channel.sub2api_group_ids),
            )
        )
    if channel.provider_type == "custom_http":
        return CustomHttpDownstreamPlugin.from_config(
            CustomHttpClientConfig(
                url=channel.base_url,
                auth_header_name=channel.custom_auth_header_name,
                auth_header_value=channel.custom_auth_header_value,
                payload_type=channel.custom_payload_type,
                timeout_s=channel.timeout_s,
                sub2api_concurrency=channel.sub2api_concurrency,
                sub2api_group_ids=parse_downstream_group_ids(channel.sub2api_group_ids),
            )
        )
    raise DownstreamProviderFactoryError(
        f"unsupported_downstream_provider: {channel.provider_type}"
    )


def parse_downstream_group_ids(value: str) -> tuple[int, ...]:
    group_ids: list[int] = []
    for part in str(value or "").split(","):
        item = part.strip()
        if not item:
            continue
        try:
            group_id = int(item)
        except ValueError as exc:
            raise DownstreamProviderFactoryError(
                f"invalid_sub2api_group_id: {item}"
            ) from exc
        if group_id <= 0:
            raise DownstreamProviderFactoryError(f"invalid_sub2api_group_id: {item}")
        group_ids.append(group_id)
    return tuple(group_ids)
