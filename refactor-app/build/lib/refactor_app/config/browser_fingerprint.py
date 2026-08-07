from __future__ import annotations

import re
from dataclasses import dataclass

from refactor_app.config.settings import get_settings

_CHROME_IMPERSONATE_PATTERN = re.compile(r"^chrome(?P<major>\d+)[a-z]*$")


@dataclass(frozen=True)
class BrowserFingerprint:
    impersonate: str
    major_version: int
    user_agent: str
    sec_ch_ua: str
    sec_ch_ua_full_version: str
    sec_ch_ua_full_version_list: str
    sec_ch_ua_platform: str = '"macOS"'
    navigator_platform: str = "MacIntel"


def browser_fingerprint_for(impersonate: str) -> BrowserFingerprint:
    normalized = str(impersonate or "").strip().lower()
    match = _CHROME_IMPERSONATE_PATTERN.fullmatch(normalized)
    if match is None:
        raise ValueError(f"unsupported browser impersonate value: {impersonate}")
    major = int(match.group("major"))
    full_version = f"{major}.0.0.0"
    return BrowserFingerprint(
        impersonate=normalized,
        major_version=major,
        user_agent=(
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            f"Chrome/{full_version} Safari/537.36"
        ),
        sec_ch_ua=(
            f'"Chromium";v="{major}", "Google Chrome";v="{major}", '
            '"Not_A Brand";v="99"'
        ),
        sec_ch_ua_full_version=f'"{full_version}"',
        sec_ch_ua_full_version_list=(
            f'"Chromium";v="{full_version}", '
            f'"Google Chrome";v="{full_version}", '
            '"Not_A Brand";v="99.0.0.0"'
        ),
    )


BROWSER_FINGERPRINT = browser_fingerprint_for(get_settings().browser_impersonate)
BROWSER_IMPERSONATE = BROWSER_FINGERPRINT.impersonate
BROWSER_USER_AGENT = BROWSER_FINGERPRINT.user_agent
BROWSER_SEC_CH_UA = BROWSER_FINGERPRINT.sec_ch_ua
BROWSER_SEC_CH_UA_PLATFORM = BROWSER_FINGERPRINT.sec_ch_ua_platform
BROWSER_NAVIGATOR_PLATFORM = BROWSER_FINGERPRINT.navigator_platform
