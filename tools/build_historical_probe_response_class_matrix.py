#!/usr/bin/env python3
from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


REPO = Path("/Users/chaopenglv/data/me/Gpt-Agreement-Payment")
PROTO = REPO / "output/protocol_reverse"
BASE = PROTO / "hypothesis_reframe"
OUT = BASE / "historical_probe_response_class_matrix.json"


def load_json(path: Path) -> Any | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def handler_sig(handlers: Any) -> str:
    if not isinstance(handlers, list):
        return ""
    if handlers and isinstance(handlers[0], list):
        return " || ".join("|".join(str(x) for x in row) for row in handlers)
    return "|".join(str(x) for x in handlers)


def decoded_class(decoded: dict[str, Any] | None) -> dict[str, Any]:
    decoded = decoded or {}
    parts = decoded.get("parts") or []
    success_parts = [p for p in parts if isinstance(p, str) and p.startswith("oIIoIooo|")]
    return {
        "handlers": decoded.get("handlers") or [],
        "handlerSig": handler_sig(decoded.get("handlers") or []),
        "hasSuccess0": "oIIoIooo|0" in success_parts,
        "hasFailureMinus1": "oIIoIooo|-1" in success_parts,
        "hasAnyOIIoIooo": bool(success_parts),
        "hasPowResult": decoded.get("hasPowResult") is True,
        "hasPx3": decoded.get("hasPx3") is True,
        "hasPxde": decoded.get("hasPxde") is True,
        "error": decoded.get("error"),
    }


def summarize_step_summary(summary: dict[str, Any] | None) -> dict[str, Any]:
    summary = summary or {}
    handlers = summary.get("handlers")
    statuses = summary.get("statuses")
    return {
        "json": summary.get("json"),
        "sent": summary.get("sent"),
        "status": summary.get("status"),
        "statuses": statuses,
        "handlerSig": handler_sig(handlers),
        "hasPowResult": summary.get("hasPowResult") is True or any(summary.get("hasPow") or []),
        "hasSuccessHandler": summary.get("hasSuccessHandler") is True,
        "error": summary.get("error") or summary.get("errors"),
    }


def collect_attempt_files(kind: str, paths: list[Path]) -> tuple[list[dict[str, Any]], Counter]:
    rows = []
    classes: Counter = Counter()
    for path in paths:
        data = load_json(path) or {}
        steps = data.get("steps") or {}
        checks = data.get("checks") or {}
        step_rows = {}
        for name, step in steps.items():
            step_rows[name] = summarize_step_summary((step or {}).get("summary") or {})
            sig = step_rows[name]["handlerSig"]
            if sig:
                classes[(kind, name, sig, step_rows[name]["hasPowResult"], step_rows[name]["hasSuccessHandler"])] += 1
        row = {
            "kind": kind,
            "path": str(path.resolve()),
            "session": data.get("session"),
            "checks": checks,
            "stepRows": step_rows,
            "anySuccess": any(v.get("hasSuccessHandler") for v in step_rows.values()) or any(
                value is True and "Success" in key for key, value in checks.items()
            ),
            "bundlePow": checks.get("bundle200Pow") is True,
            "finalComboAnySuccess": checks.get("finalComboAnySuccess") is True or checks.get("comboAnySuccess") is True,
        }
        rows.append(row)
    return rows, classes


def collect_combo_files(paths: list[Path]) -> tuple[list[dict[str, Any]], Counter]:
    rows = []
    classes: Counter = Counter()
    for path in paths:
        data = load_json(path) or {}
        checks = data.get("checks") or {}
        results = data.get("results") or {}
        result_rows = {}
        for name, result in results.items():
            if not isinstance(result, dict):
                continue
            decoded = decoded_class(result.get("decoded") or {})
            response = result.get("response") or {}
            material = result.get("material") or {}
            result_rows[name] = {
                "status": response.get("status"),
                "bodyLen": response.get("bodyLen") or response.get("body_len"),
                "contentLength": (material.get("headers") or {}).get("content-length"),
                **decoded,
            }
            classes[(name, decoded["handlerSig"], decoded["hasSuccess0"], decoded["hasFailureMinus1"], decoded["hasPowResult"])] += 1
        rows.append(
            {
                "path": str(path.resolve()),
                "checks": checks,
                "mode": data.get("mode"),
                "gapSeconds": data.get("gapSeconds"),
                "inputs": data.get("inputs"),
                "resultRows": result_rows,
                "anySuccess0": any(row.get("hasSuccess0") for row in result_rows.values()),
                "anyFailureMinus1": any(row.get("hasFailureMinus1") for row in result_rows.values()),
                "seq5FailureMinus1": (result_rows.get("seq5") or {}).get("hasFailureMinus1") is True,
                "seq6HasAnyOIIoIooo": (result_rows.get("seq6") or {}).get("hasAnyOIIoIooo") is True,
            }
        )
    return rows, classes


def summarize_px561_diffs(paths: list[Path]) -> dict[str, Any]:
    by_kind = Counter()
    sample = []
    for path in paths:
        name = path.name
        if "_full_activity_diff" in name:
            by_kind["activity_diff"] += 1
        elif "_full_field_diff" in name:
            by_kind["field_diff"] += 1
        else:
            by_kind["other"] += 1
        if len(sample) < 8:
            sample.append(str(path.resolve()))
    return {
        "count": len(paths),
        "byKind": dict(by_kind),
        "sample": sample,
    }


def build() -> dict[str, Any]:
    direct_paths = sorted((PROTO / "direct_webshare_attempt").glob("direct_webshare_attempt_*.json"))
    overlap_paths = sorted((PROTO / "first_failure_overlap_attempt").glob("first_failure_overlap_attempt_*.json"))
    combo_paths = sorted((PROTO / "seq5_seq6_combo_probe").glob("seq5_seq6_combo_probe_*.json"))
    px561_diff_paths = sorted((PROTO / "px561_compare").glob("seq5_seq6_combo_probe_*_seq*_full_*_diff.json"))

    direct_rows, direct_classes = collect_attempt_files("direct_webshare", direct_paths)
    overlap_rows, overlap_classes = collect_attempt_files("first_failure_overlap", overlap_paths)
    combo_rows, combo_classes = collect_combo_files(combo_paths)

    direct_combo_success = sum(1 for row in direct_rows if row["finalComboAnySuccess"])
    overlap_combo_success = sum(1 for row in overlap_rows if row["finalComboAnySuccess"])
    combo_success = sum(1 for row in combo_rows if row["anySuccess0"])
    combo_seq5_failures = sum(1 for row in combo_rows if row["seq5FailureMinus1"])
    combo_seq6_oiio = sum(1 for row in combo_rows if row["seq6HasAnyOIIoIooo"])

    class_rows = []
    for counter_name, counter in [
        ("directStepClasses", direct_classes),
        ("overlapStepClasses", overlap_classes),
        ("comboResultClasses", combo_classes),
    ]:
        for key, count in counter.most_common():
            class_rows.append({"classGroup": counter_name, "key": list(key), "count": count})

    near_success_classes = [
        row for row in combo_rows
        if row["seq5FailureMinus1"] is True and row["seq6HasAnyOIIoIooo"] is False
    ]

    checks = {
        "directAttemptCount": len(direct_rows),
        "firstFailureOverlapAttemptCount": len(overlap_rows),
        "seq5Seq6ComboProbeCount": len(combo_rows),
        "px561DiffFileCount": len(px561_diff_paths),
        "allDirectReachBundlePow": bool(direct_rows) and all(row["bundlePow"] for row in direct_rows),
        "allOverlapReachBundlePow": bool(overlap_rows) and all(row["bundlePow"] for row in overlap_rows),
        "directFinalComboSuccessCount": direct_combo_success,
        "overlapFinalComboSuccessCount": overlap_combo_success,
        "seq5Seq6ComboSuccess0Count": combo_success,
        "seq5Seq6ComboSeq5FailureMinus1Count": combo_seq5_failures,
        "seq5Seq6ComboSeq6AnyOIIoIoooCount": combo_seq6_oiio,
        "hasHistoricalNoBrowserSuccess0": (direct_combo_success + overlap_combo_success + combo_success) > 0,
        "hasNearSuccessFailureMinus1Class": bool(near_success_classes),
        "readyForFreshExperiment": False,
    }

    decision = {
        "readyForFreshExperiment": False,
        "recommendedExperiment": None,
        "reason": (
            "Historical no-browser probes repeatedly reach bootstrap/sequence/bundle POW and seq5 oIIoIooo|-1 classes, "
            "but no existing direct, overlap, or seq5/seq6 combo artifact contains oIIoIooo|0. "
            "The observed near-success class is still final acceptance failure, not a replayable success transition."
        ),
        "nextArtifact": str((BASE / "server_internal_unobserved_state_final_gap.json").resolve()),
        "nextScript": str((REPO / "tools/build_server_internal_unobserved_state_final_gap.py").resolve()),
    }

    return {
        "artifact": str(OUT.resolve()),
        "purpose": "Cluster existing no-browser probe attempts by response class before allowing any fresh-session experiment.",
        "inputs": {
            "crossSampleServerStateProxyMatrix": str((BASE / "cross_sample_server_state_proxy_matrix.json").resolve()),
            "directWebshareAttempts": [str(p.resolve()) for p in direct_paths],
            "firstFailureOverlapAttempts": [str(p.resolve()) for p in overlap_paths],
            "seq5Seq6ComboProbes": [str(p.resolve()) for p in combo_paths],
            "px561Diffs": [str(p.resolve()) for p in px561_diff_paths],
        },
        "summary": {
            "directAttemptCount": len(direct_rows),
            "firstFailureOverlapAttemptCount": len(overlap_rows),
            "seq5Seq6ComboProbeCount": len(combo_rows),
            "classRowCount": len(class_rows),
            "nearSuccessClassCount": len(near_success_classes),
        },
        "classRows": class_rows,
        "directAttempts": direct_rows,
        "firstFailureOverlapAttempts": overlap_rows,
        "seq5Seq6ComboProbes": combo_rows,
        "px561DiffSummary": summarize_px561_diffs(px561_diff_paths),
        "decision": decision,
        "checks": checks,
    }


def main() -> int:
    result = build()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"wrote": str(OUT), "checks": result["checks"], "decision": result["decision"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
