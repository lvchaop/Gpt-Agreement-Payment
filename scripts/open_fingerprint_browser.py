#!/usr/bin/env python3
"""Open a standalone Camoufox browser using the project's register-browser rules."""
from __future__ import annotations

import argparse
import logging
import os
import shutil
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REG_DIR = ROOT / "CTF-reg"
if str(REG_DIR) not in sys.path:
    sys.path.insert(0, str(REG_DIR))

from browser_register import _camoufox_headless, _parse_proxy  # noqa: E402
from config import Config  # noqa: E402


LOG = logging.getLogger("open_fingerprint_browser")


def _env_is_set(*names: str) -> bool:
    return any(os.environ.get(name) is not None for name in names)


def _load_proxy(config_path: str | None, proxy_override: str | None) -> str:
    if proxy_override:
        return proxy_override
    if not config_path:
        return ""
    cfg = Config.from_file(config_path)
    return str(cfg.proxy or "")


def _make_profile(mode: str) -> str:
    prefix = "chatgpt_phone_reg_" if mode == "phone" else "chatgpt_reg_"
    return tempfile.mkdtemp(prefix=prefix)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Open a standalone Camoufox window with the same launch parameters "
            "used by CTF-reg/browser_register.py and CTF-reg/phone_register.py."
        )
    )
    parser.add_argument(
        "--mode",
        choices=("browser", "phone"),
        default="browser",
        help="Profile prefix to mirror: browser=chatgpt_reg_, phone=chatgpt_phone_reg_.",
    )
    parser.add_argument(
        "--url",
        default="https://chatgpt.com/",
        help="Initial URL. Defaults to the same ChatGPT home used by the register flow.",
    )
    parser.add_argument(
        "--config",
        help="Optional CTF-reg JSON config. When provided, its top-level proxy is used.",
    )
    parser.add_argument(
        "--proxy",
        help="Override proxy URL. Uses the same _parse_proxy() logic as browser_register.py.",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Force REG_HEADLESS=1 before calling the project's _camoufox_headless().",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Print debug logs.",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    if args.headless:
        os.environ["REG_HEADLESS"] = "1"
    elif not _env_is_set("REG_HEADLESS", "CAMOUFOX_HEADLESS", "HEADLESS", "REG_VISIBLE", "CAMOUFOX_VISIBLE"):
        os.environ["REG_VISIBLE"] = "1"

    proxy_url = _load_proxy(args.config, args.proxy)
    cf_proxy = _parse_proxy(proxy_url) if proxy_url else None
    headless = _camoufox_headless()
    tmp_profile = _make_profile(args.mode)

    LOG.info("project: %s", ROOT)
    LOG.info("mode: %s", args.mode)
    LOG.info("url: %s", args.url)
    LOG.info("Camoufox headless=%s", headless)
    LOG.info("temporary profile: %s", tmp_profile)
    if proxy_url:
        LOG.info("proxy: %s", proxy_url)

    from browserforge.fingerprints import Screen
    from camoufox.sync_api import Camoufox

    try:
        with Camoufox(
            headless=headless,
            humanize=True,
            persistent_context=True,
            user_data_dir=tmp_profile,
            os="windows",
            screen=Screen(max_width=1920, max_height=1080),
            proxy=cf_proxy,
            geoip=True,
            locale="en-US",
        ) as ctx:
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            LOG.info("opening page ...")
            page.goto(args.url, wait_until="domcontentloaded", timeout=60000)
            LOG.info("opened: %s", page.url)
            if sys.stdin.isatty():
                input("Camoufox is open. Press Enter to close ...")
            else:
                LOG.info("stdin is not interactive; keep running until Ctrl-C or browser close.")
                while True:
                    page.wait_for_timeout(1000)
    finally:
        shutil.rmtree(tmp_profile, ignore_errors=True)
        LOG.info("temporary profile removed: %s", tmp_profile)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
