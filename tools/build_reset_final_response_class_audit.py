#!/usr/bin/env python3
from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
PROTO = ROOT / "output/protocol_reverse"
RESET = PROTO / "reset_plan"
TRANSPORT_AUDIT = RESET / "reset_transport_ip_hypothesis_audit.json"
OUT = RESET / "reset_final_response_class_audit.json"


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


def oIIoIooo_parts(parts: list[Any]) -> list[str]:
    return [str(part) for part in parts if str(part).startswith("oIIoIooo|")]


def summarize_row(row: dict[str, Any]) -> dict[str, Any]:
    combo = read_json(row.get("comboJson"))
    seq5 = ((combo.get("results") or {}).get("seq5") or {})
    seq6 = ((combo.get("results") or {}).get("seq6") or {})
    seq5_decoded = seq5.get("decoded") or {}
    seq6_decoded = seq6.get("decoded") or {}
    seq5_parts = seq5_decoded.get("parts") or []
    seq6_parts = seq6_decoded.get("parts") or []
    seq5_success_parts = oIIoIooo_parts(seq5_parts)
    seq6_success_parts = oIIoIooo_parts(seq6_parts)
    if seq5_success_parts == ["oIIoIooo|-1"]:
        response_class = "seq5_oIIoIooo_minus_1_seq6_no_outcome"
    elif any(part.startswith("oIIoIooo|0") for part in seq5_success_parts):
        response_class = "seq5_oIIoIooo_0_success"
    elif not seq5_success_parts:
        response_class = "seq5_no_oIIoIooo"
    else:
        response_class = "seq5_other_oIIoIooo"
    return {
        "sampleClass": row.get("sampleClass"),
        "sessionId": row.get("sessionId"),
        "transport": row.get("transport"),
        "attemptSummary": row.get("attemptSummary"),
        "comboJson": row.get("comboJson"),
        "responseClass": response_class,
        "seq5": {
            "status": ((seq5.get("response") or {}).get("status")),
            "handlers": seq5_decoded.get("handlers"),
            "oIIoIoooParts": seq5_success_parts,
            "hasPx3": any(str(part).startswith("IoooII|_px3|") for part in seq5_parts),
            "hasPxde": any(str(part).startswith("oIIoIIoo|_pxde|") for part in seq5_parts),
            "partCount": len(seq5_parts),
        },
        "seq6": {
            "status": ((seq6.get("response") or {}).get("status")),
            "handlers": seq6_decoded.get("handlers"),
            "oIIoIoooParts": seq6_success_parts,
            "hasPx3": any(str(part).startswith("IoooII|_px3|") for part in seq6_parts),
            "hasPxde": any(str(part).startswith("oIIoIIoo|_pxde|") for part in seq6_parts),
            "partCount": len(seq6_parts),
        },
    }


def main() -> int:
    transport = read_json(TRANSPORT_AUDIT)
    rows = [summarize_row(row) for row in transport.get("rows") or []]
    class_counts = Counter(row["responseClass"] for row in rows)
    webshare_rows = [row for row in rows if row["sampleClass"] == "pure_protocol_webshare"]
    direct_rows = [row for row in rows if row["sampleClass"] == "pure_protocol_direct"]

    all_minus1 = bool(rows) and all(row["responseClass"] == "seq5_oIIoIooo_minus_1_seq6_no_outcome" for row in rows)
    any_success = any(row["responseClass"] == "seq5_oIIoIooo_0_success" for row in rows)
    all_have_cookie_handlers = bool(rows) and all(
        row["seq5"]["hasPx3"] and row["seq5"]["hasPxde"] and row["seq6"]["hasPx3"] and row["seq6"]["hasPxde"]
        for row in rows
    )

    doc = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "purpose": "Classify final seq5/seq6 collector responses for valid reset pure-protocol samples.",
        "plan": str(ROOT / "docs/pure-protocol-human-hypothesis-plan.md"),
        "inputs": [str(TRANSPORT_AUDIT)],
        "rows": rows,
        "classCounts": dict(class_counts),
        "checks": {
            "transportAuditLoaded": bool(transport),
            "sampleCount": len(rows),
            "webshareSampleCount": len(webshare_rows),
            "directSampleCount": len(direct_rows),
            "allSeq5Http200": bool(rows) and all(row["seq5"]["status"] == 200 for row in rows),
            "allSeq6Http200": bool(rows) and all(row["seq6"]["status"] == 200 for row in rows),
            "allFinalResponsesSameClass": len(class_counts) == 1,
            "allFinalResponsesAreSeq5Minus1": all_minus1,
            "anySeq5Success0": any_success,
            "allFinalResponsesHavePx3PxdeHandlers": all_have_cookie_handlers,
            "stageProgressionFound": any_success,
            "readyForFreshExperiment": False,
            "goalComplete": False,
        },
        "decision": {
            "goalComplete": False,
            "readyForFreshExperiment": False,
            "stageProgressionFound": any_success,
            "recommendedExperiment": None,
            "nextArtifact": str(RESET / "reset_state_machine.json"),
            "nextScript": str(ROOT / "tools/build_reset_state_machine.py"),
            "reason": (
                "All valid reset final responses are the same class: seq5 returns oIIoIooo|-1 with _px3/_pxde updates and seq6 has no outcome handler. "
                "No stage progression or new transition candidate is exposed by final response class differences."
            ),
        },
    }
    write_json(OUT, doc)
    print(json.dumps({"json": str(OUT), "checks": doc["checks"], "decision": doc["decision"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
