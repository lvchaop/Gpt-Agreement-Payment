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
OUT = RESET / "webshare_proxy_auth_gap_audit.json"


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


def cmd_arg(cmd: list[Any], name: str) -> str | None:
    vals = [str(x) for x in cmd]
    if name not in vals:
        return None
    idx = vals.index(name)
    if idx + 1 >= len(vals):
        return None
    return vals[idx + 1]


def main() -> int:
    matrix = read_json(MATRIX)
    rows = matrix.get("executedRows") or []
    webshare_rows = [r for r in rows if r.get("sampleClass") == "pure_protocol_webshare"]
    direct_rows = [r for r in rows if r.get("sampleClass") == "pure_protocol_direct"]
    inspected = []
    for row in webshare_rows:
        cmd = ((row.get("execution") or {}).get("cmd") or [])
        cls = row.get("classification") or {}
        boot = read_json(cls.get("bootstrapArtifact"))
        inspected.append(
            {
                "sessionArg": cmd_arg(cmd, "--session"),
                "classification": cls,
                "bootstrapArtifact": cls.get("bootstrapArtifact"),
                "bootstrapError": boot.get("error"),
                "bootstrapHasResponse": bool(boot.get("response")),
                "bootstrapResponseStatus": ((boot.get("response") or {}).get("status")),
                "bootstrapTransport": ((boot.get("response") or {}).get("transport")),
                "runnerCommand": cmd,
            }
        )
    proxy_407_rows = [
        row for row in inspected
        if "407 Proxy Authentication Required" in str(row.get("bootstrapError"))
    ]
    valid_webshare_rows = [
        row for row in webshare_rows
        if ((row.get("classification") or {}).get("stage") == "final_seq5_seq6_no_success")
    ]

    direct_inspected = []
    for row in direct_rows:
        evidence = row.get("evidence") or {}
        attempt = read_json(evidence.get("attemptSummary"))
        direct_inspected.append(
            {
                "sessionId": evidence.get("sessionId"),
                "attemptSummary": evidence.get("attemptSummary"),
                "transport": attempt.get("transport"),
                "direct": attempt.get("direct"),
                "checks": attempt.get("checks"),
            }
        )

    all_webshare_407 = bool(inspected) and all(
        "407 Proxy Authentication Required" in str(row.get("bootstrapError"))
        for row in inspected
    )
    all_webshare_no_collector_response = bool(inspected) and all(
        row.get("bootstrapHasResponse") is False for row in inspected
    )
    all_direct_reach_final = bool(direct_inspected) and all(
        ((row.get("checks") or {}).get("progression200Pow") is True)
        for row in direct_inspected
    )
    any_direct_success = any(
        ((row.get("checks") or {}).get("comboAnySuccess") is True)
        for row in direct_inspected
    )

    doc = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "purpose": "Audit the reset Webshare bootstrap failure before treating it as HUMAN collector or IP behavior.",
        "plan": str(ROOT / "docs/pure-protocol-human-reset-execution-plan.md"),
        "inputs": [str(MATRIX)],
        "webshareRows": inspected,
        "directRows": direct_inspected,
        "checks": {
            "matrixLoaded": bool(matrix),
            "webshareResetRowCount": len(inspected),
            "webshareProxy407RowCount": len(proxy_407_rows),
            "validWebshareFinalNoSuccessRowCount": len(valid_webshare_rows),
            "directResetRowCount": len(direct_inspected),
            "allWebshareFailuresAreProxy407": all_webshare_407,
            "allWebshareFailuresBeforeCollectorResponse": all_webshare_no_collector_response,
            "allDirectRowsReachProgressionPow": all_direct_reach_final,
            "anyDirectCollectorSuccess": any_direct_success,
            "webshareFailureIsTransportAuthNotHumanCollector": bool(proxy_407_rows) and all(
                row.get("bootstrapHasResponse") is False for row in proxy_407_rows
            ),
            "readyForFreshExperiment": False,
            "goalComplete": False,
        },
        "decision": {
            "goalComplete": False,
            "readyForFreshExperiment": False,
            "recommendedExperiment": None,
            "nextArtifact": str(RESET / "reset_sampling_matrix.json"),
            "nextScript": str(ROOT / "tools/run_reset_sampling_matrix.py"),
            "reason": (
                "Older malformed reset Webshare samples failed before collector bootstrap due to proxy CONNECT 407. "
                "After preserving the historical Webshare username shape, valid Webshare samples are present and should be evaluated via reset_state_machine.json."
            ),
        },
    }
    write_json(OUT, doc)
    print(json.dumps({"json": str(OUT), "checks": doc["checks"], "decision": doc["decision"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
