#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


REPO = Path("/Users/chaopenglv/data/me/Gpt-Agreement-Payment")
OUT_DIR = REPO / "output/protocol_reverse/px561_constructor"
PROBE_DIR = REPO / "output/protocol_reverse/collector_live_probe"
CONSTRUCTOR = OUT_DIR / "px561_pow_tail_constructor_audit.json"


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def latest_sent_probe() -> Path | None:
    candidates = sorted(
        PROBE_DIR.glob("collector_live_probe_j0t8van4qyhm_1781119142_idx5_*.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    for path in candidates:
        try:
            doc = read_json(path)
        except Exception:
            continue
        if doc.get("sent") is True:
            return path
    return None


def handler_status(parts: list[str]) -> str | None:
    for part in parts:
        if part == "oIIoIooo|0" or part.startswith("oIIoIooo|0|"):
            return "success"
        if part == "oIIoIooo|-1" or part.startswith("oIIoIooo|-1|"):
            return "failure"
    return None


def main() -> None:
    constructor = read_json(CONSTRUCTOR)
    probe_path = latest_sent_probe()
    probe = read_json(probe_path) if probe_path else {}
    decoded = probe.get("decoded") or {}
    response = probe.get("response") or {}
    parts = decoded.get("parts") or []
    handlers = decoded.get("handlers") or []

    experimental = constructor.get("experimental") or {}
    checks = {
        "constructorExperimentalBodyBuilt": bool((constructor.get("checks") or {}).get("experimentalBodyBuilt")),
        "constructorUsesLiveOsk": bool((constructor.get("checks") or {}).get("experimentalUsesLiveOsk")),
        "constructorUsesLiveBzt": bool((constructor.get("checks") or {}).get("experimentalHasLiveBztEvidence")),
        "constructorHasFreshTbr9": bool((constructor.get("checks") or {}).get("experimentalHasFreshTbr9Evidence")),
        "sentProbeExists": probe_path is not None,
        "sentProbeUsedConstructorBody": (probe.get("probe") or {}).get("source", {}).get("bodySource") == str(CONSTRUCTOR.relative_to(REPO)),
        "sentProbeStatus200": response.get("status") == 200,
        "decodedWithoutError": decoded.get("error") is None and bool(parts),
        "decodedHasPxde": bool(decoded.get("hasPxde")),
        "decodedHasSuccessHandler": bool(decoded.get("hasSuccessHandler")),
        "decodedHasFailureHandler": handler_status(parts) == "failure",
    }

    result = {
        "purpose": "Classify the live collector response for the experimental PX561 body that uses live POW OSk and live Bzt but stale template TBR9.",
        "evidenceFiles": {
            "constructor": str(CONSTRUCTOR),
            "sentProbe": str(probe_path) if probe_path else None,
        },
        "experimentalInputs": {
            "oskSource": experimental.get("oskSource"),
            "bztSource": experimental.get("bztSource"),
            "bzt": experimental.get("bzt"),
            "tbr9Source": experimental.get("tbr9Source"),
            "bodySha256": (probe.get("probe") or {}).get("bodySha256"),
            "bodyLenBytes": (probe.get("probe") or {}).get("bodyLenBytes"),
        },
        "liveResponse": {
            "status": response.get("status"),
            "bodyLen": response.get("bodyLen"),
            "decodedMode": decoded.get("mode"),
            "handlers": handlers,
            "parts": parts,
            "handlerStatus": handler_status(parts),
            "hasPx3": decoded.get("hasPx3"),
            "hasPxde": decoded.get("hasPxde"),
            "hasPowResult": decoded.get("hasPowResult"),
            "hasSuccessHandler": decoded.get("hasSuccessHandler"),
            "decodeError": decoded.get("error"),
        },
        "checks": checks,
        "conclusion": (
            "The experimental PX561 live probe reached the collector and decoded cleanly, but returned oIIoIooo|-1 rather than oIIoIooo|0. "
            "Because this body uses live POW OSk and live Bzt while retaining stale template TBR9, this is a negative-control result for the current constructor; it does not prove TBR9 alone is the only missing acceptance condition."
        ),
        "nextEvidenceRequired": "Generate a fresh TBR9 value from runtime micro hooks or its exact producer before treating the PX561 constructor as success-ready.",
    }

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_json = OUT_DIR / "px561_experimental_live_probe_audit.json"
    out_md = OUT_DIR / "px561_experimental_live_probe_audit.md"
    out_json.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = [
        "# PX561 experimental live probe audit",
        "",
        f"constructor={CONSTRUCTOR}",
        f"sentProbe={probe_path}",
        "",
        "## checks",
    ]
    lines.extend(f"- {key}: `{value}`" for key, value in checks.items())
    lines.extend(
        [
            "",
            "## response",
            f"- status: `{response.get('status')}`",
            f"- handlers: `{', '.join(handlers)}`",
            f"- handlerStatus: `{handler_status(parts)}`",
            f"- hasSuccessHandler: `{decoded.get('hasSuccessHandler')}`",
            f"- hasPxde: `{decoded.get('hasPxde')}`",
            "",
            "## conclusion",
            result["conclusion"],
            "",
            "## next",
            result["nextEvidenceRequired"],
        ]
    )
    out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"json": str(out_json), "md": str(out_md), "checks": checks}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
