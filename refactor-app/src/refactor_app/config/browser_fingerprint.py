from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, replace

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
    sec_ch_ua_platform_version: str = '"15.7.0"'
    sec_ch_ua_arch: str = '"arm"'
    sec_ch_ua_bitness: str = '"64"'
    screen_width: int = 1800
    screen_height: int = 1169
    hardware_concurrency: int = 12
    device_memory: int = 8
    device_pixel_ratio: float = 2
    js_heap_size_limit: int = 4_395_630_592


@dataclass(frozen=True)
class _BrowserOsProfile:
    name: str
    user_agent_platform: str
    sec_ch_ua_platform: str
    navigator_platform: str
    platform_version: str
    architecture: str


@dataclass(frozen=True)
class _BrowserScreenProfile:
    screen_width: int
    screen_height: int
    device_pixel_ratio: float


@dataclass(frozen=True)
class _BrowserBrand:
    name: str
    fixed_version: str = ""


_BROWSER_OS_PROFILES = (
    _BrowserOsProfile(
        name="windows",
        user_agent_platform="Windows NT 10.0; Win64; x64",
        sec_ch_ua_platform='"Windows"',
        navigator_platform="Win32",
        platform_version='"15.0.0"',
        architecture='"x86"',
    ),
    _BrowserOsProfile(
        name="macos-intel",
        user_agent_platform="Macintosh; Intel Mac OS X 10_15_7",
        sec_ch_ua_platform='"macOS"',
        navigator_platform="MacIntel",
        platform_version='"15.7.0"',
        architecture='"x86"',
    ),
    _BrowserOsProfile(
        name="macos-arm",
        user_agent_platform="Macintosh; Intel Mac OS X 10_15_7",
        sec_ch_ua_platform='"macOS"',
        navigator_platform="MacIntel",
        platform_version='"15.7.0"',
        architecture='"arm"',
    ),
    _BrowserOsProfile(
        name="linux",
        user_agent_platform="X11; Linux x86_64",
        sec_ch_ua_platform='"Linux"',
        navigator_platform="Linux x86_64",
        platform_version='"6.8.0"',
        architecture='"x86"',
    ),
)

# Keep this list limited to concrete curl_cffi profiles available in the
# bundled runtime.  A mailbox deterministically selects one version and OS.
_STABLE_EMAIL_CHROME_PROFILES = (
    "chrome136",
    "chrome142",
    "chrome145",
    "chrome145",
    "chrome146",
    "chrome146",
    "chrome146",
    "chrome146",
)

_CHROME_BRANDS = {
    "chrome136": (
        _BrowserBrand("Chromium"),
        _BrowserBrand("Google Chrome"),
        _BrowserBrand("Not.A/Brand", "99"),
    ),
    "chrome142": (
        _BrowserBrand("Chromium"),
        _BrowserBrand("Google Chrome"),
        _BrowserBrand("Not_A Brand", "99"),
    ),
    "chrome145": (
        _BrowserBrand("Not:A-Brand", "99"),
        _BrowserBrand("Google Chrome"),
        _BrowserBrand("Chromium"),
    ),
    "chrome146": (
        _BrowserBrand("Chromium"),
        _BrowserBrand("Not-A.Brand", "24"),
        _BrowserBrand("Google Chrome"),
    ),
}

_STABLE_EMAIL_OS_PROFILES = (
    "windows",
    "windows",
    "windows",
    "windows",
    "macos-intel",
    "macos-arm",
    "macos-arm",
    "linux",
)

_STABLE_EMAIL_SCREEN_PROFILES = {
    "windows": (
        _BrowserScreenProfile(1920, 1080, 1),
        _BrowserScreenProfile(1536, 864, 1.25),
        _BrowserScreenProfile(1366, 768, 1),
        _BrowserScreenProfile(1280, 720, 1.5),
        _BrowserScreenProfile(1600, 900, 1),
        _BrowserScreenProfile(1707, 960, 1.5),
        _BrowserScreenProfile(2048, 1152, 1.25),
    ),
    "macos-intel": (
        _BrowserScreenProfile(1280, 800, 2),
        _BrowserScreenProfile(1440, 900, 2),
        _BrowserScreenProfile(1680, 1050, 2),
    ),
    "macos-arm": (
        _BrowserScreenProfile(1440, 900, 2),
        _BrowserScreenProfile(1470, 956, 2),
        _BrowserScreenProfile(1512, 982, 2),
        _BrowserScreenProfile(1728, 1117, 2),
    ),
    "linux": (
        _BrowserScreenProfile(1366, 768, 1),
        _BrowserScreenProfile(1536, 864, 1.25),
        _BrowserScreenProfile(1600, 900, 1),
        _BrowserScreenProfile(1920, 1080, 1),
        _BrowserScreenProfile(1920, 1200, 1),
        _BrowserScreenProfile(2560, 1440, 1),
    ),
}

_STABLE_EMAIL_HARDWARE_CONCURRENCY = {
    "windows": (4, 6, 8, 12, 16, 20),
    "macos-intel": (4, 8, 12),
    "macos-arm": (8, 10, 12, 14),
    "linux": (4, 8, 12, 16),
}

_STABLE_EMAIL_DEVICE_MEMORY = {
    "windows": (4, 8),
    "macos-intel": (4, 8),
    "macos-arm": (8,),
    "linux": (4, 8),
}


def browser_fingerprint_for(
    impersonate: str,
    *,
    os_profile: str = "macos-arm",
) -> BrowserFingerprint:
    normalized = str(impersonate or "").strip().lower()
    match = _CHROME_IMPERSONATE_PATTERN.fullmatch(normalized)
    if match is None:
        raise ValueError(f"unsupported browser impersonate value: {impersonate}")
    selected_os = next(
        (profile for profile in _BROWSER_OS_PROFILES if profile.name == os_profile),
        None,
    )
    if selected_os is None:
        raise ValueError(f"unsupported browser OS profile: {os_profile}")
    major = int(match.group("major"))
    full_version = f"{major}.0.0.0"
    brands = _CHROME_BRANDS.get(
        normalized,
        (
            _BrowserBrand("Chromium"),
            _BrowserBrand("Google Chrome"),
            _BrowserBrand("Not_A Brand", "99"),
        ),
    )
    sec_ch_ua = ", ".join(f'"{brand.name}";v="{brand.fixed_version or major}"' for brand in brands)
    full_brand_versions = (
        (brand, f"{brand.fixed_version}.0.0.0" if brand.fixed_version else full_version)
        for brand in brands
    )
    sec_ch_ua_full_version_list = ", ".join(
        f'"{brand.name}";v="{brand_version}"' for brand, brand_version in full_brand_versions
    )
    return BrowserFingerprint(
        impersonate=normalized,
        major_version=major,
        user_agent=(
            f"Mozilla/5.0 ({selected_os.user_agent_platform}) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            f"Chrome/{full_version} Safari/537.36"
        ),
        sec_ch_ua=sec_ch_ua,
        sec_ch_ua_full_version=f'"{full_version}"',
        sec_ch_ua_full_version_list=sec_ch_ua_full_version_list,
        sec_ch_ua_platform=selected_os.sec_ch_ua_platform,
        navigator_platform=selected_os.navigator_platform,
        sec_ch_ua_platform_version=selected_os.platform_version,
        sec_ch_ua_arch=selected_os.architecture,
    )


def _stable_choice[Choice](
    values: tuple[Choice, ...],
    digest: bytes,
    *,
    offset: int,
) -> Choice:
    value = int.from_bytes(digest[offset : offset + 4], "big")
    return values[value % len(values)]


def browser_fingerprint_for_email(email: str) -> BrowserFingerprint:
    """Generate one complete, stable browser identity for a normalized mailbox."""

    normalized = str(email or "").strip().casefold()
    if not normalized or "@" not in normalized:
        raise ValueError("email is required for a stable browser fingerprint")
    digest = hashlib.sha256(f"session-browser-v2\0{normalized}".encode()).digest()
    impersonate = _stable_choice(
        _STABLE_EMAIL_CHROME_PROFILES,
        digest,
        offset=0,
    )
    os_profile = _stable_choice(
        _STABLE_EMAIL_OS_PROFILES,
        digest,
        offset=4,
    )
    screen = _stable_choice(
        _STABLE_EMAIL_SCREEN_PROFILES[os_profile],
        digest,
        offset=8,
    )
    hardware_concurrency = _stable_choice(
        _STABLE_EMAIL_HARDWARE_CONCURRENCY[os_profile],
        digest,
        offset=12,
    )
    device_memory = _stable_choice(
        _STABLE_EMAIL_DEVICE_MEMORY[os_profile],
        digest,
        offset=16,
    )
    return replace(
        browser_fingerprint_for(impersonate, os_profile=os_profile),
        screen_width=screen.screen_width,
        screen_height=screen.screen_height,
        hardware_concurrency=hardware_concurrency,
        device_memory=device_memory,
        device_pixel_ratio=screen.device_pixel_ratio,
    )


BROWSER_FINGERPRINT = browser_fingerprint_for(get_settings().browser_impersonate)
BROWSER_IMPERSONATE = BROWSER_FINGERPRINT.impersonate
BROWSER_USER_AGENT = BROWSER_FINGERPRINT.user_agent
BROWSER_SEC_CH_UA = BROWSER_FINGERPRINT.sec_ch_ua
BROWSER_SEC_CH_UA_PLATFORM = BROWSER_FINGERPRINT.sec_ch_ua_platform
BROWSER_NAVIGATOR_PLATFORM = BROWSER_FINGERPRINT.navigator_platform
