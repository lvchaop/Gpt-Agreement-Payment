from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any


class SpaceUsageError(RuntimeError):
    pass


WINDOW_SECONDS_TO_KIND = {
    18_000: "five_hour",
    604_800: "weekly",
    2_592_000: "monthly",
}


@dataclass(frozen=True)
class WhamUsageWindow:
    quota_window_kind: str
    used_percent: int
    limit_window_seconds: int
    reset_after_seconds: int
    reset_at: datetime | None
    raw_window: dict[str, Any]


def parse_wham_usage_windows(payload: dict[str, Any]) -> list[WhamUsageWindow]:
    rate_limit = payload.get("rate_limit")
    if not isinstance(rate_limit, dict):
        raise SpaceUsageError("usage payload missing rate_limit")

    windows: list[WhamUsageWindow] = []
    for key in ("primary_window", "secondary_window"):
        raw_window = rate_limit.get(key)
        if raw_window is None:
            continue
        if not isinstance(raw_window, dict):
            raise SpaceUsageError(f"{key} must be an object or null")
        window = _parse_window(raw_window)
        if window is not None:
            windows.append(window)
    if not windows:
        raise SpaceUsageError("usage payload has no supported rate limit windows")
    return windows


def infer_credential_type(*, space_type: str, usage_payload: dict[str, Any]) -> str:
    normalized_space_type = str(space_type or "").strip()
    if normalized_space_type == "personal":
        return "personal_account"
    if normalized_space_type != "business":
        raise SpaceUsageError(f"unsupported space_type: {space_type}")

    window_seconds = {item.limit_window_seconds for item in parse_wham_usage_windows(usage_payload)}
    if {18_000, 604_800}.issubset(window_seconds):
        return "team_5h_weekly"
    if 2_592_000 in window_seconds:
        return "team_monthly"
    raise SpaceUsageError(f"unsupported business usage windows: {sorted(window_seconds)}")


def usage_status_from_percent(used_percent: int, *, threshold_percent: int = 95) -> str:
    percent = _int_value(used_percent, field_name="used_percent")
    threshold = max(1, min(_int_value(threshold_percent, field_name="threshold_percent"), 100))
    if percent >= threshold:
        return "used"
    if percent >= max(1, threshold - 10):
        return "near_limit"
    return "active"


def _parse_window(raw_window: dict[str, Any]) -> WhamUsageWindow | None:
    limit_window_seconds = _int_value(
        raw_window.get("limit_window_seconds"),
        field_name="limit_window_seconds",
    )
    quota_window_kind = WINDOW_SECONDS_TO_KIND.get(limit_window_seconds)
    if quota_window_kind is None:
        return None
    return WhamUsageWindow(
        quota_window_kind=quota_window_kind,
        used_percent=max(
            0,
            min(100, _int_value(raw_window.get("used_percent"), field_name="used_percent")),
        ),
        limit_window_seconds=limit_window_seconds,
        reset_after_seconds=max(
            0,
            _int_value(raw_window.get("reset_after_seconds"), field_name="reset_after_seconds"),
        ),
        reset_at=_epoch_seconds(raw_window.get("reset_at")),
        raw_window=dict(raw_window),
    )


def _int_value(value: Any, *, field_name: str) -> int:
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise SpaceUsageError(f"{field_name} must be integer-like") from exc


def _epoch_seconds(value: Any) -> datetime | None:
    if value is None or value == "":
        return None
    try:
        timestamp = int(value)
    except (TypeError, ValueError) as exc:
        raise SpaceUsageError("reset_at must be integer epoch seconds") from exc
    if timestamp <= 0:
        return None
    return datetime.fromtimestamp(timestamp, tz=UTC)
