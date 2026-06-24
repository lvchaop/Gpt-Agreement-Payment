#!/usr/bin/env python3
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
PLAN = ROOT / "docs/pure-protocol-human-reset-execution-plan.md"
RESET = ROOT / "output/protocol_reverse/reset_plan"
MATRIX = RESET / "reset_sampling_matrix.json"
RUNTIME_REDUCTION = RESET / "reset_runtime_js_candidate_reduction.json"
OUT = RESET / "reset_onecollector_surface_audit.json"


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def iter_jsonl(path: str | Path | None):
    if not path:
        return
    p = Path(path)
    if not p.exists():
        return
    with p.open("r", encoding="utf-8", errors="replace") as fh:
        for idx, line in enumerate(fh, 1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            row["_line"] = idx
            yield row


def write_json(path: Path, doc: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")


def sample_rows(matrix: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for idx, row in enumerate(matrix.get("executedRows") or []):
        if row.get("countsTowardResetMinimum") is not True:
            continue
        if row.get("sampleClass") not in {"browser_success_webshare", "browser_failure_webshare"}:
            continue
        evidence = row.get("evidence") or {}
        cls = row.get("classification") or {}
        rows.append(
            {
                "id": evidence.get("sessionId") or f"{row.get('sampleClass')}_{idx}",
                "sampleClass": row.get("sampleClass"),
                "successLike": cls.get("successLike") is True,
                "stage": cls.get("stage"),
                "runtimeTrace": evidence.get("runtimeTrace") or [],
            }
        )
    return rows


def classify_rows(paths: list[str]) -> dict[str, Any]:
    markers: dict[str, list[dict[str, Any]]] = {
        "oneCollector": [],
        "humanCollector": [],
        "collectorSuccess": [],
        "collectorFailure": [],
        "riskVerifyContinue": [],
        "createAccountRedirect": [],
        "requestFailed": [],
    }
    for path in paths:
        for row in iter_jsonl(path):
            text = json.dumps(row, ensure_ascii=False)
            url = str(row.get("url") or "")
            entry = {
                "source": str(path),
                "line": row.get("_line"),
                "kind": row.get("kind"),
                "t": row.get("t"),
                "url": url,
            }
            if "browser.events.data.microsoft.com/OneCollector/1.0/" in url:
                if row.get("kind") == "requestfailed":
                    markers["requestFailed"].append(entry)
                markers["oneCollector"].append(entry)
            if "collector-pxzc5j78di.hsprotect.net" in url:
                markers["humanCollector"].append(entry)
            if "oIIoIooo" in text and '"0"' in text:
                markers["collectorSuccess"].append(entry)
            if "oIIoIooo" in text and '"-1"' in text:
                markers["collectorFailure"].append(entry)
            if "/api/v1.0/risk/verify" in url and '"state":"continue"' in text:
                markers["riskVerifyContinue"].append(entry)
            if "/API/CreateAccount" in url and "redirectUrl" in text:
                markers["createAccountRedirect"].append(entry)
    return markers


def first_t(rows: list[dict[str, Any]]) -> float | None:
    vals = [row.get("t") for row in rows if isinstance(row.get("t"), (int, float))]
    return min(vals) if vals else None


def build() -> dict[str, Any]:
    matrix = read_json(MATRIX)
    reduction = read_json(RUNTIME_REDUCTION)
    samples = sample_rows(matrix)
    sample_audits = []
    for sample in samples:
        markers = classify_rows(sample["runtimeTrace"])
        one_t = first_t(markers["oneCollector"])
        success_t = first_t(markers["collectorSuccess"])
        failure_t = first_t(markers["collectorFailure"])
        risk_t = first_t(markers["riskVerifyContinue"])
        create_t = first_t(markers["createAccountRedirect"])
        accept_t_candidates = [v for v in [success_t, risk_t, create_t] if v is not None]
        accept_t = min(accept_t_candidates) if accept_t_candidates else None
        after_accept = one_t is not None and accept_t is not None and one_t >= accept_t
        sample_audits.append(
            {
                **sample,
                "counts": {name: len(rows) for name, rows in markers.items()},
                "firstTimes": {
                    "oneCollector": one_t,
                    "collectorSuccess": success_t,
                    "collectorFailure": failure_t,
                    "riskVerifyContinue": risk_t,
                    "createAccountRedirect": create_t,
                },
                "oneCollectorAfterAcceptedChain": after_accept,
                "oneCollectorRows": markers["oneCollector"][:10],
                "requestFailedRows": markers["requestFailed"][:10],
            }
        )

    success_samples = [s for s in sample_audits if s["successLike"]]
    failure_samples = [s for s in sample_audits if not s["successLike"]]
    one_success = [s for s in success_samples if s["counts"]["oneCollector"] > 0]
    one_failure = [s for s in failure_samples if s["counts"]["oneCollector"] > 0]
    one_after_accept = [s for s in one_success if s["oneCollectorAfterAcceptedChain"]]
    network_reduction_rows = [
        row for row in (reduction.get("reductionsSample") or [])
        if row.get("reductionCategory") == "network_surface"
    ]
    checks = {
        "matrixExists": MATRIX.exists(),
        "runtimeReductionExists": RUNTIME_REDUCTION.exists(),
        "countedBrowserSampleCount": len(samples),
        "successSampleCount": len(success_samples),
        "failureSampleCount": len(failure_samples),
        "oneCollectorSuccessSampleCount": len(one_success),
        "oneCollectorFailureSampleCount": len(one_failure),
        "oneCollectorAbsentInAllFailures": len(one_failure) == 0,
        "oneCollectorAfterAcceptedChainCount": len(one_after_accept),
        "allOneCollectorSuccessRowsAfterAcceptedChain": bool(one_success) and len(one_after_accept) == len(one_success),
        "networkSurfaceReductionCount": len(network_reduction_rows),
        "promoteToSingleTransitionCandidate": False,
        "readyForFreshExperiment": False,
        "goalComplete": False,
    }
    return {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "plan": str(PLAN),
        "purpose": "Determine whether the reset runtime/JS network_surface candidates are pre-accept HUMAN transitions or downstream Microsoft telemetry.",
        "inputs": {
            "matrix": str(MATRIX),
            "runtimeJsCandidateReduction": str(RUNTIME_REDUCTION),
        },
        "checks": checks,
        "networkSurfaceRows": network_reduction_rows,
        "sampleAudits": sample_audits,
        "decision": {
            "goalComplete": False,
            "readyForFreshExperiment": False,
            "recommendedExperiment": None,
            "nextArtifact": None,
            "nextScript": None,
            "reason": (
                "The only reset runtime network_surface candidate is browser.events.data.microsoft.com OneCollector telemetry. "
                "It is not a HUMAN collector request and is not proved as a pre-accept constructible transition; do not promote it to Phase 5."
            ),
        },
    }


def main() -> int:
    doc = build()
    write_json(OUT, doc)
    print(json.dumps({"json": str(OUT), "checks": doc["checks"], "decision": doc["decision"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
