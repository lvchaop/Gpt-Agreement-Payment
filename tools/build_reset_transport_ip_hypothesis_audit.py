#!/usr/bin/env python3
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
PROTO = ROOT / "output/protocol_reverse"
RESET = PROTO / "reset_plan"
MATRIX = RESET / "reset_sampling_matrix.json"
STATE = RESET / "reset_state_machine.json"
OUT = RESET / "reset_transport_ip_hypothesis_audit.json"


def read_json(path: Path | str | None) -> dict[str, Any]:
    if not path:
        return {}
    p = Path(str(path))
    if not p.is_absolute():
        p = ROOT / p
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))


def write_json(path: Path, doc: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")


def combo_summary(attempt: dict[str, Any]) -> dict[str, Any]:
    combo = (((attempt.get("steps") or {}).get("seq5Seq6Combo") or {}).get("summary") or {})
    return {
        "json": combo.get("json"),
        "checks": combo.get("checks") or {},
    }


def attempt_row(row: dict[str, Any]) -> dict[str, Any]:
    evidence = row.get("evidence") or {}
    attempt = read_json(evidence.get("attemptSummary"))
    combo = combo_summary(attempt)
    checks = row.get("checks") or attempt.get("checks") or {}
    return {
        "sampleClass": row.get("sampleClass"),
        "sessionId": evidence.get("sessionId"),
        "attemptSummary": evidence.get("attemptSummary"),
        "transport": attempt.get("transport") or ("direct" if attempt.get("direct") else "webshare"),
        "proxyEndpoint": attempt.get("proxyEndpoint"),
        "proxySessionUser": attempt.get("proxySessionUser"),
        "direct": attempt.get("direct") is True,
        "stage": ((row.get("classification") or {}).get("stage")),
        "checks": checks,
        "comboJson": combo.get("json"),
        "comboChecks": combo.get("checks"),
        "reachedFinalSeq5Seq6": (
            checks.get("progression200Pow") is True
            and (combo.get("checks") or {}).get("seq5Http200") is True
            and (combo.get("checks") or {}).get("seq6Http200") is True
        ),
        "collectorSuccess": checks.get("comboAnySuccess") is True,
    }


def main() -> int:
    matrix = read_json(MATRIX)
    state = read_json(STATE)
    executed = matrix.get("executedRows") or []
    valid = [
        attempt_row(row)
        for row in executed
        if row.get("countsTowardResetMinimum") is True
        and row.get("sampleClass") in {"pure_protocol_webshare", "pure_protocol_direct"}
    ]
    webshare = [row for row in valid if row["sampleClass"] == "pure_protocol_webshare"]
    direct = [row for row in valid if row["sampleClass"] == "pure_protocol_direct"]
    success = [row for row in valid if row["collectorSuccess"]]
    reached_final = [row for row in valid if row["reachedFinalSeq5Seq6"]]

    doc = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "purpose": "Evaluate whether reset transport/IP class alone is sufficient for pure-protocol HUMAN collector success.",
        "plan": str(ROOT / "docs/pure-protocol-human-hypothesis-plan.md"),
        "inputs": [str(MATRIX), str(STATE)],
        "rows": valid,
        "transportGroups": {
            "webshare": webshare,
            "direct": direct,
        },
        "checks": {
            "matrixLoaded": bool(matrix),
            "stateMachineLoaded": bool(state),
            "validPureProtocolSampleCount": len(valid),
            "validWebshareSampleCount": len(webshare),
            "validDirectSampleCount": len(direct),
            "allValidSamplesReachedFinalSeq5Seq6": bool(valid) and len(reached_final) == len(valid),
            "allValidWebshareReachedFinalSeq5Seq6": bool(webshare) and all(row["reachedFinalSeq5Seq6"] for row in webshare),
            "allValidDirectReachedFinalSeq5Seq6": bool(direct) and all(row["reachedFinalSeq5Seq6"] for row in direct),
            "anyCollectorSuccess": bool(success),
            "webshareAnyCollectorSuccess": any(row["collectorSuccess"] for row in webshare),
            "directAnyCollectorSuccess": any(row["collectorSuccess"] for row in direct),
            "transportIpAloneSupported": False,
            "readyForFreshExperiment": False,
            "goalComplete": False,
        },
        "decision": {
            "goalComplete": False,
            "readyForFreshExperiment": False,
            "transportIpAloneSupported": False,
            "recommendedExperiment": None,
            "nextArtifact": str(RESET / "reset_state_machine.json"),
            "nextScript": str(ROOT / "tools/build_reset_state_machine.py"),
            "reason": (
                "Valid reset Webshare and direct pure-protocol samples both reach final seq5/seq6, and neither group contains collector success. "
                "Transport/IP class alone is not sufficient evidence for HUMAN success and should not be the next standalone experiment axis."
            ),
        },
    }
    write_json(OUT, doc)
    print(json.dumps({"json": str(OUT), "checks": doc["checks"], "decision": doc["decision"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
