#!/usr/bin/env python3
from __future__ import annotations

import json
import hashlib
from pathlib import Path
from typing import Any

from replay_human_collector_state import HumanState, apply_handler


REPO = Path("/Users/chaopenglv/data/me/Gpt-Agreement-Payment")
RESET_DIR = REPO / "output/protocol_reverse/reset_plan"
FINAL_AUDIT = RESET_DIR / "reset_final_response_class_audit.json"
OUT = RESET_DIR / "reset_cookie_mutation_audit.json"


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def part_cookie_value(part: str, cookie_name: str) -> str | None:
    fields = str(part).split("|")
    if len(fields) >= 4 and fields[1] == cookie_name:
        return fields[3]
    return None


def summarize_cookie(cookie: dict[str, Any] | None) -> dict[str, Any] | None:
    if not cookie:
        return None
    value = str(cookie.get("value") or "")
    source = cookie.get("source") or {}
    return {
        "valueSha256": sha256_text(value),
        "valueLen": len(value),
        "valuePrefix": value[:32],
        "ttl": cookie.get("ttl"),
        "domain": cookie.get("domain"),
        "source": source,
        "sourceRawSha256": sha256_text(str(source.get("raw") or "")),
    }


def decoded_parts(combo: dict[str, Any], seq_name: str) -> list[str]:
    decoded = ((combo.get("results") or {}).get(seq_name) or {}).get("decoded") or {}
    return [str(part) for part in decoded.get("parts") or []]


def cookie_values_by_seq(combo: dict[str, Any], seq_name: str) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for idx, part in enumerate(decoded_parts(combo, seq_name)):
        for name in ("_px3", "_pxde", "_pxvid"):
            value = part_cookie_value(part, name)
            if value is not None:
                out[name] = {
                    "partIndex": idx,
                    "valueSha256": sha256_text(value),
                    "valueLen": len(value),
                    "rawSha256": sha256_text(part),
                }
    return out


def row_audit(row: dict[str, Any], idx: int) -> dict[str, Any]:
    combo_path = Path(row["comboJson"])
    combo = load_json(combo_path)
    state = HumanState()
    events: list[dict[str, Any]] = []

    for line_no, seq_name in ((5, "seq5"), (6, "seq6")):
        for part_index, part in enumerate(decoded_parts(combo, seq_name)):
            event = apply_handler(state, line_no=line_no, part_index=part_index, part=part)
            event["seqName"] = seq_name
            if event.get("value"):
                event["valueSha256"] = sha256_text(str(event["value"]))
                event["valueLen"] = len(str(event["value"]))
                event.pop("value", None)
            events.append(event)

    seq_values = {
        "seq5": cookie_values_by_seq(combo, "seq5"),
        "seq6": cookie_values_by_seq(combo, "seq6"),
    }
    final_cookies = {
        name: summarize_cookie(state.cookies.get(name))
        for name in ("_px3", "_pxde", "_pxvid")
    }
    success_values = [ev.get("args", [""])[0] for ev in events if ev.get("handler") == "oIIoIooo"]
    final_matches_seq6 = {
        name: (
            bool(final_cookies.get(name))
            and bool(seq_values["seq6"].get(name))
            and final_cookies[name]["valueSha256"] == seq_values["seq6"][name]["valueSha256"]
        )
        for name in ("_px3", "_pxde")
    }
    final_matches_seq5 = {
        name: (
            bool(final_cookies.get(name))
            and bool(seq_values["seq5"].get(name))
            and final_cookies[name]["valueSha256"] == seq_values["seq5"][name]["valueSha256"]
        )
        for name in ("_px3", "_pxde")
    }
    cookie_events = [
        {
            key: ev.get(key)
            for key in (
                "seqName",
                "collectorLine",
                "partIndex",
                "handler",
                "effect",
                "name",
                "ttl",
                "domain",
                "semantic",
                "valueSha256",
                "valueLen",
                "evidence",
            )
            if key in ev
        }
        for ev in events
        if ev.get("effect") in {"set_cookie", "set_cookie_and_storage"}
    ]

    return {
        "index": idx,
        "transport": row.get("transport"),
        "sampleId": row.get("sampleId"),
        "comboJson": str(combo_path.resolve()),
        "seqCookieValues": seq_values,
        "finalCookies": final_cookies,
        "cookieEvents": cookie_events,
        "successValues": success_values,
        "checks": {
            "seq5HasPx3Pxde": all(name in seq_values["seq5"] for name in ("_px3", "_pxde")),
            "seq6HasPx3Pxde": all(name in seq_values["seq6"] for name in ("_px3", "_pxde")),
            "finalJarHasPx3Pxde": all(final_cookies.get(name) for name in ("_px3", "_pxde")),
            "finalJarUsesSeq6Px3Pxde": all(final_matches_seq6.values()),
            "finalJarStillUsesSeq5Px3Pxde": any(final_matches_seq5.values()),
            "hasPxvidInFinalResponse": bool(final_cookies.get("_pxvid")),
            "hasSuccess0": "0" in success_values,
            "hasFailureMinus1": "-1" in success_values,
            "cookieEventCount": len(cookie_events),
        },
    }


def main() -> int:
    final_audit = load_json(FINAL_AUDIT)
    rows = [row_audit(row, idx) for idx, row in enumerate(final_audit.get("rows") or [])]
    checks = {
        "finalResponseClassAuditExists": FINAL_AUDIT.exists(),
        "sampleCount": len(rows),
        "webshareSampleCount": sum(1 for row in rows if row.get("transport") == "webshare"),
        "directSampleCount": sum(1 for row in rows if row.get("transport") == "direct"),
        "allSeq5HasPx3Pxde": bool(rows) and all(row["checks"]["seq5HasPx3Pxde"] for row in rows),
        "allSeq6HasPx3Pxde": bool(rows) and all(row["checks"]["seq6HasPx3Pxde"] for row in rows),
        "allOfflineJarHasPx3Pxde": bool(rows) and all(row["checks"]["finalJarHasPx3Pxde"] for row in rows),
        "allFinalJarUsesSeq6Values": bool(rows) and all(row["checks"]["finalJarUsesSeq6Px3Pxde"] for row in rows),
        "anyFinalJarStillUsesSeq5Values": any(row["checks"]["finalJarStillUsesSeq5Px3Pxde"] for row in rows),
        "anyFinalResponseHasPxvid": any(row["checks"]["hasPxvidInFinalResponse"] for row in rows),
        "anySuccess0": any(row["checks"]["hasSuccess0"] for row in rows),
        "allHaveFailureMinus1": bool(rows) and all(row["checks"]["hasFailureMinus1"] for row in rows),
    }
    checks["riskVerifyCandidateComplete"] = (
        checks["allOfflineJarHasPx3Pxde"]
        and checks["anyFinalResponseHasPxvid"]
        and checks["anySuccess0"]
    )
    checks["readyForRiskVerifyReplay"] = checks["riskVerifyCandidateComplete"]
    checks["readyForFreshExperiment"] = False
    checks["goalComplete"] = False

    result = {
        "input": str(FINAL_AUDIT.resolve()),
        "rows": rows,
        "checks": checks,
        "decision": {
            "goalComplete": False,
            "readyForFreshExperiment": False,
            "readyForRiskVerifyReplay": checks["readyForRiskVerifyReplay"],
            "nextArtifact": str((RESET_DIR / "reset_state_machine.json").resolve()),
            "nextScript": str((REPO / "tools/build_reset_state_machine.py").resolve()),
            "reason": (
                "Offline handler replay proves the decoded final failure responses mutate _px3/_pxde into the jar, "
                "and seq6 overwrites seq5 values. The same evidence also shows no oIIoIooo|0 success event and no "
                "_pxvid handler in the final responses, so this is not a complete risk/verify success-cookie candidate."
            ),
        },
        "handlerEvidence": [
            "tools/replay_human_collector_state.py apply_handler maps IoooII to set_cookie/bake",
            "tools/replay_human_collector_state.py apply_handler maps oIIoIIoo to set_cookie/enrich",
            "tools/replay_human_collector_state.py apply_handler maps oIIoIooo value 0 to challenge_success and other values to challenge_terminal",
        ],
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"out": str(OUT), "checks": checks}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
