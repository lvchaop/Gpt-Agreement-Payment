#!/usr/bin/env python3
"""Probe whether the SEPA WebExtension registers in Camoufox."""

from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path

from browserforge.fingerprints import Screen
from camoufox import DefaultAddons
from camoufox.sync_api import Camoufox


EXTENSION = Path(
    "/Users/chaopenglv/Downloads/claude-sepa-helper-v1.0.8-protected"
)


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="camoufox_extension_probe_") as profile:
        extension_copy = Path(profile).parent / f"{Path(profile).name}_extension"
        shutil.copytree(EXTENSION, extension_copy)
        manifest_path = extension_copy / "manifest.json"
        manifest = json.loads(manifest_path.read_text())
        manifest.pop("minimum_chrome_version", None)
        manifest["browser_specific_settings"] = {
            "gecko": {"id": "claude-sepa-helper@local"}
        }
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=True, indent=2) + "\n")
        with Camoufox(
            headless=False,
            humanize=True,
            persistent_context=True,
            user_data_dir=profile,
            os="windows",
            screen=Screen(max_width=1920, max_height=1080),
            addons=[str(extension_copy)],
            exclude_addons=[DefaultAddons.UBO],
        ) as context:
            page = context.pages[0] if context.pages else context.new_page()
            page.goto("data:text/html,<title>probe</title><body>probe</body>", wait_until="load")
            page.wait_for_timeout(2_000)
            result = {
                "url": page.url,
                "title": page.title(),
                "fingerprint": page.evaluate(
                    """() => ({
                              userAgent: navigator.userAgent,
                              webdriver: navigator.webdriver,
                              platform: navigator.platform,
                              languages: navigator.languages,
                              screen: [screen.width, screen.height],
                              hardwareConcurrency: navigator.hardwareConcurrency,
                            })"""
                ),
            }
        extensions_file = Path(profile) / "extensions.json"
        extensions = json.loads(extensions_file.read_text()) if extensions_file.exists() else {}
        result["extensions"] = [
            {
                "id": addon.get("id"),
                "name": addon.get("defaultLocale", {}).get("name"),
                "active": addon.get("active"),
                "type": addon.get("type"),
                "path": addon.get("path"),
            }
            for addon in extensions.get("addons", [])
        ]
        print(json.dumps(result, ensure_ascii=False, indent=2))
        shutil.rmtree(extension_copy, ignore_errors=True)


if __name__ == "__main__":
    main()
