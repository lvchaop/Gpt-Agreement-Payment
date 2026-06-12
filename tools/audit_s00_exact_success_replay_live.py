#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


REPO = Path("/Users/chaopenglv/data/me/Gpt-Agreement-Payment")
RUN_ID = "s00ld1lglrw0_1781191381"
PROBE_DIR = REPO / "output/protocol_reverse/collector_live_probe"
VALUE_CHAIN = REPO / "output/protocol_reverse/goal_audit/s00_same_session_px561_value_chain_audit.json"
CONSTRUCTOR_SPEC = REPO / "output/protocol_reverse/goal_audit/s00_success_constructor_spec_audit.json"
OUT_DIR = REPO / "output/protocol_reverse/goal_audit"


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def latest_sent_probe() -> Path | None:
    candidates = sorted(
        PROBE_DIR.glob(f"collector_live_probe_{RUN_ID}_idx5_*.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    for path in candidates:
        try:
            doc = read_json(path)
        except Exception:
            continue
        if doc.get("sent") is True and doc.get("response"):
            return path
    return None


def handler_status(parts: list[str]) -> str | None:
    for part in parts:
        if part == "oIIoIooo|0" or part.startswith("oIIoIooo|0|"):
            return "success"
        if part == "oIIoIooo|-1" or part.startswith("oIIoIooo|-1|"):
            return "failure"
    return None


def main() -> int:
    probe_path = latest_sent_probe()
    probe = read_json(probe_path) if probe_path else {}
    chain = read_json(VALUE_CHAIN)
    spec = read_json(CONSTRUCTOR_SPEC)
    success_chain = chain["chains"][1]
    decoded = probe.get("decoded") or {}
    parts = decoded.get("parts") or []
    live_status = handler_status(parts)
    expected_body_sha = ((spec.get("observedSuccess") or {}).get("request") or {}).get("postDataSha256")
    observed_status = (success_chain.get("nextCollectorHandler") or {}).get("status")
    checks = {
        "probeExists": probe_path is not None,
        "probeSent": probe.get("sent") is True,
        "probeHttp200": (probe.get("response") or {}).get("status") == 200,
        "probeBodyShaMatchesObservedLine933": ((probe.get("probe") or {}).get("bodySha256") == expected_body_sha),
        "observedLine933WasSuccess": observed_status == "0",
        "liveReplayDecodedWithoutError": decoded.get("error") is None and bool(parts),
        "liveReplayHasPx3": decoded.get("hasPx3") is True,
        "liveReplayHasPxde": decoded.get("hasPxde") is True,
        "liveReplayReturnsFailure": live_status == "failure",
        "liveReplayDoesNotReturnSuccess": decoded.get("hasSuccessHandler") is False,
    }
    result = {
        "purpose": "Classify whether the exact observed s00 line 933 success body is replayable later as a collector success control.",
        "evidenceFiles": {
            "probe": str(probe_path) if probe_path else None,
            "valueChain": str(VALUE_CHAIN),
            "constructorSpec": str(CONSTRUCTOR_SPEC),
        },
        "observedSuccess": {
            "requestLine": success_chain.get("request", {}).get("requestLine"),
            "seq": success_chain.get("request", {}).get("params", {}).get("seq"),
            "bodySha256": expected_body_sha,
            "handler": success_chain.get("nextCollectorHandler"),
        },
        "liveReplay": {
            "status": (probe.get("response") or {}).get("status"),
            "bodySha256": (probe.get("probe") or {}).get("bodySha256"),
            "bodyLenBytes": (probe.get("probe") or {}).get("bodyLenBytes"),
            "decodedMode": decoded.get("mode"),
            "handlers": decoded.get("handlers"),
            "parts": parts,
            "handlerStatus": live_status,
            "hasSuccessHandler": decoded.get("hasSuccessHandler"),
            "hasPx3": decoded.get("hasPx3"),
            "hasPxde": decoded.get("hasPxde"),
            "hasPowResult": decoded.get("hasPowResult"),
            "decodeError": decoded.get("error"),
        },
        "checks": checks,
        "conclusion": (
            "The exact observed s00 line 933 body was a success in the original runtime trace, and the later live probe sent a body with the same SHA-256. "
            "The replay reached the collector and decoded cleanly but returned oIIoIooo|-1, not oIIoIooo|0. "
            "Therefore the success body is not replayable as a stale fixed artifact; a live pure-protocol PoC must generate a fresh same-session body and state."
        ),
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_json = OUT_DIR / "s00_exact_success_replay_live_audit.json"
    out_md = OUT_DIR / "s00_exact_success_replay_live_audit.md"
    out_json.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = ["# s00 exact success replay live audit", "", "## Checks", ""]
    lines.extend(f"- {key}: `{value}`" for key, value in checks.items())
    lines += [
        "",
        "## Observed vs live",
        "",
        f"- observed handler: `{success_chain.get('nextCollectorHandler')}`",
        f"- live handler: `{live_status}`",
        f"- bodySha256: `{(probe.get('probe') or {}).get('bodySha256')}`",
        "",
        "## Conclusion",
        "",
        result["conclusion"],
        "",
    ]
    out_md.write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"json": str(out_json), "md": str(out_md), "checks": checks}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
