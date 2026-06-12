#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


REPO = Path("/Users/chaopenglv/data/me/Gpt-Agreement-Payment")
PROTO = REPO / "output/protocol_reverse"
OUT_DIR = PROTO / "goal_audit"


def load_json(path: Path) -> Any | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def check_file(path: Path) -> dict[str, Any]:
    return {"path": str(path.resolve()), "exists": path.exists()}


def collector_request_build_summary() -> dict[str, Any]:
    path = PROTO / "collector_request_build"
    rows = []
    for file in sorted(path.glob("collector_request_build_*.json")):
        data = load_json(file) or {}
        req_rows = data.get("rows") or []
        rows.append(
            {
                "file": str(file.resolve()),
                "run": file.name.removeprefix("collector_request_build_").removesuffix(".json"),
                "rowCount": len(req_rows),
                "allExactBodyMatch": bool(req_rows) and all(r.get("exactBodyMatch") is True for r in req_rows),
                "badRows": [
                    {
                        "index": r.get("index"),
                        "requestLine": r.get("requestLine"),
                        "status": r.get("status"),
                        "firstDiff": r.get("firstDiff"),
                    }
                    for r in req_rows
                    if r.get("exactBodyMatch") is not True
                ],
            }
        )
    return {
        "dir": str(path.resolve()),
        "fileCount": len(rows),
        "rows": rows,
        "allExact": bool(rows) and all(r["allExactBodyMatch"] for r in rows),
    }


def px561_constructor_summary() -> dict[str, Any]:
    path = PROTO / "px561_constructor/px561_pow_tail_constructor_audit.json"
    audit = load_json(path) or {}
    checks = audit.get("checks") or {}
    required = [
        "originalRebuildMatchesObserved",
        "sameValueReplacementMatchesObserved",
        "experimentalUsesLiveOsk",
        "experimentalHasLiveBztEvidence",
        "experimentalHasFreshTbr9Evidence",
        "experimentalSerializedUsesFreshTbr9",
    ]
    return {
        "path": str(path.resolve()),
        "exists": path.exists(),
        "checks": checks,
        "requiredChecksPass": all(checks.get(k) is True for k in required),
        "experimentalTbr9Source": ((audit.get("experimental") or {}).get("tbr9Source")),
    }


def live_probe_summary() -> dict[str, Any]:
    audit_path = PROTO / "px561_constructor/px561_experimental_live_probe_audit.json"
    audit = load_json(audit_path) or {}
    checks = audit.get("checks") or {}
    return {
        "path": str(audit_path.resolve()),
        "exists": audit_path.exists(),
        "checks": checks,
        "conclusion": audit.get("conclusion"),
    }


def experimental_inner_payload_summary() -> dict[str, Any]:
    audit_path = PROTO / "px561_compare/px561_experimental_inner_payload_audit.json"
    audit = load_json(audit_path) or {}
    return {
        "path": str(audit_path.resolve()),
        "exists": audit_path.exists(),
        "checks": audit.get("checks"),
        "conclusion": audit.get("conclusion"),
    }


def value_source_coupling_summary() -> dict[str, Any]:
    audit_path = PROTO / "px561_compare/px561_experimental_value_source_coupling.json"
    audit = load_json(audit_path) or {}
    return {
        "path": str(audit_path.resolve()),
        "exists": audit_path.exists(),
        "sourceRuns": audit.get("sourceRuns"),
        "checks": audit.get("checks"),
        "conclusion": audit.get("conclusion"),
    }


def same_session_material_coverage_summary() -> dict[str, Any]:
    audit_path = PROTO / "goal_audit/same_session_material_coverage_audit.json"
    audit = load_json(audit_path) or {}
    return {
        "path": str(audit_path.resolve()),
        "exists": audit_path.exists(),
        "summary": audit.get("summary"),
        "checks": audit.get("checks"),
    }


def same_session_value_chain_summary() -> dict[str, Any]:
    audit_path = PROTO / "goal_audit/s00_same_session_px561_value_chain_audit.json"
    audit = load_json(audit_path) or {}
    chains = audit.get("chains") or []
    return {
        "path": str(audit_path.resolve()),
        "exists": audit_path.exists(),
        "checks": audit.get("checks"),
        "chainSummary": [
            {
                "cycleIndex": chain.get("cycleIndex"),
                "requestLine": (chain.get("request") or {}).get("requestLine"),
                "seq": ((chain.get("request") or {}).get("params") or {}).get("seq"),
                "powLine": (chain.get("precedingPowChallenge") or {}).get("lineNo"),
                "nqLine": (chain.get("nqRuntimeSample") or {}).get("line"),
                "handler": chain.get("nextCollectorHandler"),
            }
            for chain in chains
        ],
        "conclusion": audit.get("conclusion"),
    }


def success_constructor_spec_summary() -> dict[str, Any]:
    audit_path = PROTO / "goal_audit/s00_success_constructor_spec_audit.json"
    audit = load_json(audit_path) or {}
    spec = audit.get("constructorSpec") or {}
    return {
        "path": str(audit_path.resolve()),
        "exists": audit_path.exists(),
        "checks": audit.get("checks"),
        "px561TargetStatuses": {
            key: value.get("status")
            for key, value in ((spec.get("px561TargetSources") or {}).items())
            if isinstance(value, dict)
        },
        "remainingGaps": audit.get("remainingGaps"),
        "conclusion": audit.get("conclusion"),
    }


def exact_success_replay_summary() -> dict[str, Any]:
    audit_path = PROTO / "goal_audit/s00_exact_success_replay_live_audit.json"
    audit = load_json(audit_path) or {}
    return {
        "path": str(audit_path.resolve()),
        "exists": audit_path.exists(),
        "checks": audit.get("checks"),
        "observedSuccess": audit.get("observedSuccess"),
        "liveReplay": {
            key: (audit.get("liveReplay") or {}).get(key)
            for key in ["status", "bodySha256", "handlerStatus", "hasSuccessHandler", "hasPx3", "hasPxde", "hasPowResult", "decodeError"]
        },
        "conclusion": audit.get("conclusion"),
    }


def success_session_state_boundary_summary() -> dict[str, Any]:
    audit_path = PROTO / "goal_audit/s00_success_session_state_boundary_audit.json"
    audit = load_json(audit_path) or {}
    return {
        "path": str(audit_path.resolve()),
        "exists": audit_path.exists(),
        "checks": audit.get("checks"),
        "remainingGaps": audit.get("remainingGaps"),
        "conclusion": audit.get("conclusion"),
    }


def fresh_state_param_sources_summary() -> dict[str, Any]:
    audit_path = PROTO / "goal_audit/s00_fresh_state_param_sources_audit.json"
    audit = load_json(audit_path) or {}
    return {
        "path": str(audit_path.resolve()),
        "exists": audit_path.exists(),
        "checks": audit.get("checks"),
        "remainingFreshStateGaps": audit.get("remainingFreshStateGaps"),
        "conclusion": audit.get("conclusion"),
    }


def fresh_bootstrap_live_probe_summary() -> dict[str, Any]:
    audit_path = PROTO / "goal_audit/fresh_bootstrap_live_probe_audit.json"
    audit = load_json(audit_path) or {}
    return {
        "path": str(audit_path.resolve()),
        "exists": audit_path.exists(),
        "checks": audit.get("checks"),
        "freshState": audit.get("freshState"),
        "response": {
            key: (audit.get("response") or {}).get(key)
            for key in ["status", "bodyLen", "elapsedSeconds", "handlers"]
        },
        "remainingGaps": audit.get("remainingGaps"),
        "conclusion": audit.get("conclusion"),
    }


def fresh_second_live_probe_summary() -> dict[str, Any]:
    audit_path = PROTO / "goal_audit/fresh_second_live_probe_audit.json"
    audit = load_json(audit_path) or {}
    return {
        "path": str(audit_path.resolve()),
        "exists": audit_path.exists(),
        "checks": audit.get("checks"),
        "response": {
            key: (audit.get("response") or {}).get(key)
            for key in ["status", "bodyLen", "elapsedSeconds", "handlers"]
        },
        "remainingGaps": audit.get("remainingGaps"),
        "conclusion": audit.get("conclusion"),
    }


def fresh_sequence_live_probe_summary() -> dict[str, Any]:
    audit_path = PROTO / "goal_audit/fresh_sequence_live_probe_audit.json"
    audit = load_json(audit_path) or {}
    return {
        "path": str(audit_path.resolve()),
        "exists": audit_path.exists(),
        "checks": audit.get("checks"),
        "stepChecks": audit.get("stepChecks"),
        "remainingGaps": audit.get("remainingGaps"),
        "conclusion": audit.get("conclusion"),
    }


def fresh_bundle_live_probe_summary() -> dict[str, Any]:
    audit_path = PROTO / "goal_audit/fresh_bundle_live_probe_audit.json"
    audit = load_json(audit_path) or {}
    return {
        "path": str(audit_path.resolve()),
        "exists": audit_path.exists(),
        "checks": audit.get("checks"),
        "pow": audit.get("pow"),
        "remainingGaps": audit.get("remainingGaps"),
        "conclusion": audit.get("conclusion"),
    }


def latest_fresh_px561_probe_summary(aeax_source: str | None = None) -> dict[str, Any]:
    probe_dir = PROTO / "fresh_px561_probe"
    candidates = sorted(probe_dir.glob("fresh_px561_probe_*.json"))
    rows = []
    for path in candidates:
        doc = load_json(path) or {}
        meta = ((doc.get("material") or {}).get("meta") or {})
        if aeax_source is not None and meta.get("aeaxSource") != aeax_source:
            continue
        decoded = doc.get("decoded") or {}
        rows.append(
            {
                "path": str(path.resolve()),
                "sent": doc.get("sent"),
                "status": (doc.get("response") or {}).get("status"),
                "handlers": decoded.get("handlers"),
                "hasSuccessHandler": decoded.get("hasSuccessHandler"),
                "hasPowResult": decoded.get("hasPowResult"),
                "hasPx3": decoded.get("hasPx3"),
                "hasPxde": decoded.get("hasPxde"),
                "checks": (doc.get("material") or {}).get("checks"),
                "aeaxSource": meta.get("aeaxSource"),
                "bodySha256": (doc.get("material") or {}).get("bodySha256"),
                "pc": meta.get("pc"),
                "newPxTail": meta.get("newPxTail"),
                "boundary": meta.get("boundary"),
                "error": doc.get("error"),
            }
        )
    latest = rows[-1] if rows else None
    return {
        "dir": str(probe_dir.resolve()),
        "exists": probe_dir.exists(),
        "filterAeaxSource": aeax_source,
        "matchingProbeCount": len(rows),
        "latest": latest,
        "allMatching": rows,
    }


def latest_fresh_px561_diff_summary() -> dict[str, Any]:
    diff_dir = PROTO / "px561_compare"
    candidates = sorted(diff_dir.glob("fresh_px561_probe_*_diff_vs_s00.json"))
    path = candidates[-1] if candidates else diff_dir / "fresh_px561_probe_*_diff_vs_s00.json"
    audit = load_json(path) or {}
    return {
        "path": str(path.resolve()),
        "exists": path.exists(),
        "checks": audit.get("checks"),
        "freshRequest": ((audit.get("freshProbe") or {}).get("request") or {}),
        "comparisonLabels": [
            item.get("against")
            for item in audit.get("comparisons") or []
            if isinstance(item, dict)
        ],
    }


def latest_fresh_bundle_progression_summary() -> dict[str, Any]:
    probe_dir = PROTO / "fresh_bundle_progression_probe"
    candidates = sorted(probe_dir.glob("fresh_bundle_progression_probe_*.json"))
    path = candidates[-1] if candidates else probe_dir / "fresh_bundle_progression_probe_*.json"
    doc = load_json(path) or {}
    steps = doc.get("steps") or []
    return {
        "path": str(path.resolve()),
        "exists": path.exists(),
        "sent": doc.get("sent"),
        "statuses": [(step.get("response") or {}).get("status") for step in steps],
        "handlers": [(step.get("decoded") or {}).get("handlers") for step in steps],
        "hasPow": [(step.get("decoded") or {}).get("hasPowResult") for step in steps],
        "finalState": {
            key: (doc.get("finalState") or {}).get(key)
            for key in ["uuid", "jo", "ci", "cs", "powChallenge"]
        },
        "boundary": doc.get("boundary"),
    }


def progression_px561_convergence_summary() -> dict[str, Any]:
    path = PROTO / "goal_audit/progression_px561_convergence_audit.json"
    audit = load_json(path) or {}
    return {
        "path": str(path.resolve()),
        "exists": path.exists(),
        "checks": audit.get("checks"),
        "fieldDiffs": audit.get("fieldDiffs"),
        "activityDiffs": audit.get("activityDiffs"),
        "conclusion": audit.get("conclusion"),
    }


def exact_activities_outer_request_diff_summary() -> dict[str, Any]:
    path = PROTO / "goal_audit/exact_activities_outer_request_diff_audit.json"
    audit = load_json(path) or {}
    return {
        "path": str(path.resolve()),
        "exists": path.exists(),
        "checks": audit.get("checks"),
        "outer": {
            "paramDiffCount": ((audit.get("outer") or {}).get("paramDiffCount")),
            "paramDiffKeys": [row.get("key") for row in ((audit.get("outer") or {}).get("paramDiffs") or [])],
            "sameParams": ((audit.get("outer") or {}).get("sameParams")),
            "bodyLen": ((audit.get("outer") or {}).get("bodyLen")),
        },
        "conclusion": audit.get("conclusion"),
    }


def outer_binding_controls_summary() -> dict[str, Any]:
    path = PROTO / "goal_audit/outer_binding_controls_audit.json"
    audit = load_json(path) or {}
    return {
        "path": str(path.resolve()),
        "exists": path.exists(),
        "checks": audit.get("checks"),
        "controls": {
            name: {
                "sent": row.get("sent"),
                "status": row.get("status"),
                "hasSuccessHandler": row.get("hasSuccessHandler"),
                "meta": row.get("meta"),
                "activityChecks": row.get("activityChecks"),
                "bodySha256": row.get("bodySha256"),
            }
            for name, row in ((audit.get("controls") or {}).items())
        },
        "conclusion": audit.get("conclusion"),
    }


def px561_stateful_retry_summary() -> dict[str, Any]:
    path = PROTO / "goal_audit/px561_stateful_retry_audit.json"
    audit = load_json(path) or {}
    return {
        "path": str(path.resolve()),
        "exists": path.exists(),
        "checks": audit.get("checks"),
        "stateUpdate": audit.get("stateUpdate"),
        "retry": audit.get("retry"),
        "conclusion": audit.get("conclusion"),
    }


def post_px_retry_fresh_pow_attempt_summary() -> dict[str, Any]:
    path = PROTO / "goal_audit/post_px_retry_fresh_pow_attempt_audit.json"
    audit = load_json(path) or {}
    return {
        "path": str(path.resolve()),
        "exists": path.exists(),
        "checks": audit.get("checks"),
        "progression": audit.get("progression"),
        "attempt": audit.get("attempt"),
        "conclusion": audit.get("conclusion"),
    }


def aeax_control_after_post_retry_summary() -> dict[str, Any]:
    path = PROTO / "goal_audit/aeax_control_after_post_retry_audit.json"
    audit = load_json(path) or {}
    return {
        "path": str(path.resolve()),
        "exists": path.exists(),
        "checks": audit.get("checks"),
        "s00NgEvidence": audit.get("s00NgEvidence"),
        "attempts": audit.get("attempts"),
        "conclusion": audit.get("conclusion"),
    }


def fresh_first_failure_history_summary() -> dict[str, Any]:
    path = PROTO / "goal_audit/fresh_first_failure_history_audit.json"
    audit = load_json(path) or {}
    return {
        "path": str(path.resolve()),
        "exists": path.exists(),
        "checks": audit.get("checks"),
        "firstPx": audit.get("firstPx"),
        "postProgression": audit.get("postProgression"),
        "secondPx": audit.get("secondPx"),
        "conclusion": audit.get("conclusion"),
    }



def clean_history_line922_guard_summary() -> dict[str, Any]:
    path = PROTO / "goal_audit/clean_history_line922_guard_audit.json"
    audit = load_json(path) or {}
    return {
        "path": str(path.resolve()),
        "exists": path.exists(),
        "checks": audit.get("checks"),
        "probe": audit.get("probe"),
        "activityDiff": audit.get("activityDiff"),
        "conclusion": audit.get("conclusion"),
    }



def clean_history_controls_summary() -> dict[str, Any]:
    path = PROTO / "goal_audit/clean_history_controls_audit.json"
    audit = load_json(path) or {}
    return {
        "path": str(path.resolve()),
        "exists": path.exists(),
        "checks": audit.get("checks"),
        "controls": audit.get("controls"),
        "conclusion": audit.get("conclusion"),
    }



def clean_history_exact_px561_control_summary() -> dict[str, Any]:
    path = PROTO / "goal_audit/clean_history_exact_px561_control_audit.json"
    audit = load_json(path) or {}
    return {
        "path": str(path.resolve()),
        "exists": path.exists(),
        "checks": audit.get("checks"),
        "probe": audit.get("probe"),
        "activityDiff": audit.get("activityDiff"),
        "conclusion": audit.get("conclusion"),
    }



def clean_history_exact_whole_activities_summary() -> dict[str, Any]:
    path = PROTO / "goal_audit/clean_history_exact_whole_activities_audit.json"
    audit = load_json(path) or {}
    return {
        "path": str(path.resolve()),
        "exists": path.exists(),
        "checks": audit.get("checks"),
        "probe": audit.get("probe"),
        "activityDiff": audit.get("activityDiff"),
        "conclusion": audit.get("conclusion"),
    }



def clean_history_outer_binding_summary() -> dict[str, Any]:
    path = PROTO / "goal_audit/clean_history_outer_binding_audit.json"
    audit = load_json(path) or {}
    return {
        "path": str(path.resolve()),
        "exists": path.exists(),
        "checks": audit.get("checks"),
        "exactWholeActivitiesControl": audit.get("exactWholeActivitiesControl"),
        "proxyAuthorizationControl": audit.get("proxyAuthorizationControl"),
        "conclusion": audit.get("conclusion"),
    }



def clean_history_payload_pc_controls_summary() -> dict[str, Any]:
    path = PROTO / "goal_audit/clean_history_payload_pc_controls_audit.json"
    audit = load_json(path) or {}
    return {
        "path": str(path.resolve()),
        "exists": path.exists(),
        "checks": audit.get("checks"),
        "exactPayloadPcFreshOuter": audit.get("exactPayloadPcFreshOuter"),
        "templateMarkerFreshUuid": audit.get("templateMarkerFreshUuid"),
        "conclusion": audit.get("conclusion"),
    }



def clean_history_pc_uuid_controls_summary() -> dict[str, Any]:
    path = PROTO / "goal_audit/clean_history_pc_uuid_controls_audit.json"
    audit = load_json(path) or {}
    return {
        "path": str(path.resolve()),
        "exists": path.exists(),
        "checks": audit.get("checks"),
        "exactPayloadFreshPc": audit.get("exactPayloadFreshPc"),
        "freshPayloadTemplatePc": audit.get("freshPayloadTemplatePc"),
        "conclusion": audit.get("conclusion"),
    }



def clean_history_form_outer_controls_summary() -> dict[str, Any]:
    path = PROTO / "goal_audit/clean_history_form_outer_controls_audit.json"
    audit = load_json(path) or {}
    return {
        "path": str(path.resolve()),
        "exists": path.exists(),
        "checks": audit.get("checks"),
        "freshPayloadTemplateOuter": audit.get("freshPayloadTemplateOuter"),
        "exactBodyTemplateOuter": audit.get("exactBodyTemplateOuter"),
        "conclusion": audit.get("conclusion"),
    }


def captcha_head_control_summary() -> dict[str, Any]:
    path = PROTO / "goal_audit/captcha_head_control_audit.json"
    audit = load_json(path) or {}
    return {
        "path": str(path.resolve()),
        "exists": path.exists(),
        "checks": audit.get("checks"),
        "evidence": audit.get("evidence"),
        "conclusion": audit.get("conclusion"),
    }


def captcha_head_delay_control_summary() -> dict[str, Any]:
    path = PROTO / "goal_audit/captcha_head_delay_control_audit.json"
    audit = load_json(path) or {}
    return {
        "path": str(path.resolve()),
        "exists": path.exists(),
        "checks": audit.get("checks"),
        "s00Timing": audit.get("s00Timing"),
        "control": audit.get("control"),
        "activityDiff": audit.get("activityDiff"),
        "conclusion": audit.get("conclusion"),
    }


def wasm_ng_runtime_random_replay_summary() -> dict[str, Any]:
    path = PROTO / "wasm/wasm_ng_runtime_random_replay_audit_gwyi06rpe015_1781208840.json"
    audit = load_json(path) or {}
    cycle = audit.get("cycle1") or {}
    return {
        "path": str(path.resolve()),
        "exists": path.exists(),
        "checks": audit.get("checks"),
        "evidence": audit.get("evidence"),
        "cycle1": {
            "pxUuid": cycle.get("pxUuid"),
            "nInput": cycle.get("nInput"),
            "randomLens": cycle.get("randomLens"),
            "randomHexCount": len(cycle.get("randomHexSeq") or []),
            "runtimeAeax": cycle.get("runtimeAeax"),
            "offlineNg": cycle.get("offlineNg"),
            "runtimeTbr9": cycle.get("runtimeTbr9"),
            "offlineNq": cycle.get("offlineNq"),
        },
    }


def direct_webshare_ip_hypothesis_summary() -> dict[str, Any]:
    path = PROTO / "goal_audit/direct_webshare_ip_hypothesis_audit.json"
    audit = load_json(path) or {}
    rows = audit.get("rows") or []
    return {
        "path": str(path.resolve()),
        "exists": path.exists(),
        "checks": audit.get("checks"),
        "rows": [
            {
                "session": row.get("session"),
                "proxyEndpoint": row.get("proxyEndpoint"),
                "egressIp": ((row.get("egressProbe") or {}).get("body") or "").strip(),
                "comboChecks": row.get("comboChecks"),
                "seq5Handlers": row.get("seq5Handlers"),
            }
            for row in rows
        ],
        "conclusion": audit.get("conclusion"),
    }


def collector_request_context_diff_summary() -> dict[str, Any]:
    path = PROTO / "goal_audit/collector_request_context_diff_s00_line933_vs_direct_header_order_parity_seq5.json"
    audit = load_json(path) or {}
    return {
        "path": str(path.resolve()),
        "exists": path.exists(),
        "checks": audit.get("checks"),
        "diffs": {
            "formValueDiffKeys": ((audit.get("diffs") or {}).get("formValueDiffKeys")),
            "bodyLenDiff": ((audit.get("diffs") or {}).get("bodyLenDiff")),
            "contentLengthHeaderDiff": ((audit.get("diffs") or {}).get("contentLengthHeaderDiff")),
        },
        "accepted": {
            "source": ((audit.get("accepted") or {}).get("source")),
            "decodedHandlers": ((audit.get("accepted") or {}).get("decodedHandlers")),
            "hasSuccessHandler": ((audit.get("accepted") or {}).get("hasSuccessHandler")),
        },
        "rejected": {
            "source": ((audit.get("rejected") or {}).get("source")),
            "decodedHandlers": ((audit.get("rejected") or {}).get("decodedHandlers")),
            "hasSuccessHandler": ((audit.get("rejected") or {}).get("hasSuccessHandler")),
        },
    }


def seq5_seq6_timing_control_summary() -> dict[str, Any]:
    path = PROTO / "goal_audit/seq5_seq6_timing_control_audit.json"
    audit = load_json(path) or {}
    return {
        "path": str(path.resolve()),
        "exists": path.exists(),
        "checks": audit.get("checks"),
        "s00": {
            "seq6RequestGapSeconds": ((audit.get("s00") or {}).get("seq6RequestGapSeconds")),
            "requestsOverlappedBeforeFirstResponse": ((audit.get("s00") or {}).get("requestsOverlappedBeforeFirstResponse")),
        },
        "control": {
            "mode": ((audit.get("control") or {}).get("mode")),
            "gapSeconds": ((audit.get("control") or {}).get("gapSeconds")),
            "combo": ((audit.get("control") or {}).get("combo")),
            "comboChecks": ((audit.get("control") or {}).get("checks")),
            "derivedTiming": (((audit.get("control") or {}).get("timing") or {}).get("derived")),
        },
        "conclusion": audit.get("conclusion"),
    }


def direct_exact_whole_activities_seq5_summary() -> dict[str, Any]:
    combo_path = PROTO / "seq5_seq6_combo_probe/seq5_seq6_combo_probe_5175be02-660b-11f1-b71b-62666cc2b93d_1781233443.json"
    activity_diff_path = PROTO / "px561_compare/seq5_seq6_combo_probe_5175be02-660b-11f1-b71b-62666cc2b93d_1781233443_seq5_full_activity_diff.json"
    field_diff_path = PROTO / "px561_compare/seq5_seq6_combo_probe_5175be02-660b-11f1-b71b-62666cc2b93d_1781233443_seq5_full_field_diff.json"
    combo = load_json(combo_path) or {}
    seq5 = ((combo.get("results") or {}).get("seq5") or {})
    seq6 = ((combo.get("results") or {}).get("seq6") or {})
    activity_diff = load_json(activity_diff_path) or {}
    field_diff = load_json(field_diff_path) or {}
    seq5_meta = ((seq5.get("material") or {}).get("meta") or {})
    return {
        "comboPath": str(combo_path.resolve()),
        "comboExists": combo_path.exists(),
        "activityDiffPath": str(activity_diff_path.resolve()),
        "activityDiffExists": activity_diff_path.exists(),
        "fieldDiffPath": str(field_diff_path.resolve()),
        "fieldDiffExists": field_diff_path.exists(),
        "comboChecks": combo.get("checks"),
        "seq5": {
            "status": ((seq5.get("response") or {}).get("status")),
            "handlers": ((seq5.get("decoded") or {}).get("handlers")),
            "bodySha256": ((seq5.get("material") or {}).get("bodySha256")),
            "meta": {
                key: seq5_meta.get(key)
                for key in [
                    "templateRuntimeRequestLine",
                    "seq",
                    "rsc",
                    "aeaxSource",
                    "bztSource",
                    "stackSource",
                    "tailSource",
                    "innerUuidSource",
                    "nonPxActivitySource",
                    "payloadUuidSource",
                    "pcUuidSource",
                    "markerSource",
                    "formOuterSource",
                ]
            },
        },
        "seq6": {
            "status": ((seq6.get("response") or {}).get("status")),
            "error": seq6.get("error"),
        },
        "activityChecks": activity_diff.get("checks"),
        "fieldChecks": field_diff.get("checks"),
        "fieldDiffCountVsS00Success": field_diff.get("diffCountVsS00Success"),
        "diffsByClass": field_diff.get("diffsByClass"),
    }


def cookie_session_lineage_gap_summary() -> dict[str, Any]:
    path = PROTO / "goal_audit/cookie_session_lineage_gap_audit.json"
    audit = load_json(path) or {}
    return {
        "path": str(path.resolve()),
        "exists": path.exists(),
        "checks": audit.get("checks"),
        "s00": {
            "decodedPreSuccessCount": (((audit.get("s00") or {}).get("decodedPreSuccess") or {}).get("count")),
            "parentPreSuccessCount": (((audit.get("s00") or {}).get("parentPreSuccess") or {}).get("count")),
            "correlationCountPreSuccess": ((audit.get("s00") or {}).get("correlationCountPreSuccess")),
            "lastCorrelations": ((audit.get("s00") or {}).get("lastCorrelations")),
        },
        "freshDirect": {
            "decodedEventCount": (((audit.get("freshDirect") or {}).get("decodedEvents") or {}).get("count")),
            "comboChecks": ((audit.get("freshDirect") or {}).get("comboChecks")),
            "fieldDiffCountVsS00Success": ((audit.get("freshDirect") or {}).get("fieldDiffCountVsS00Success")),
        },
        "conclusion": audit.get("conclusion"),
    }


def stk_ns_control_summary() -> dict[str, Any]:
    path = PROTO / "goal_audit/stk_ns_control_audit.json"
    audit = load_json(path) or {}
    return {
        "path": str(path.resolve()),
        "exists": path.exists(),
        "checks": audit.get("checks"),
        "s00": {
            "stkRequestsBeforeAcceptedLine933": ((audit.get("s00") or {}).get("stkRequestsBeforeAcceptedLine933")),
        },
        "control": {
            "preStkSummary": ((audit.get("control") or {}).get("preStkSummary")),
            "comboChecks": ((audit.get("control") or {}).get("comboChecks")),
            "fieldDiffCountVsS00Success": ((audit.get("control") or {}).get("fieldDiffCountVsS00Success")),
        },
        "conclusion": audit.get("conclusion"),
    }


def s00_unreplayed_event_matrix_summary() -> dict[str, Any]:
    path = PROTO / "goal_audit/s00_unreplayed_event_matrix_audit.json"
    audit = load_json(path) or {}
    return {
        "path": str(path.resolve()),
        "exists": path.exists(),
        "checks": audit.get("checks"),
        "s00RequestCountsByClassBeforeLine933": ((audit.get("s00") or {}).get("requestCountsByClassBeforeLine933")),
        "unreplayedEventClasses": audit.get("unreplayedEventClasses"),
        "conclusion": audit.get("conclusion"),
    }


def captcha_asset_combo_control_summary() -> dict[str, Any]:
    path = PROTO / "goal_audit/captcha_asset_combo_control_audit.json"
    audit = load_json(path) or {}
    return {
        "path": str(path.resolve()),
        "exists": path.exists(),
        "checks": audit.get("checks"),
        "control": {
            "directChecks": ((audit.get("control") or {}).get("directChecks")),
            "comboChecks": ((audit.get("control") or {}).get("comboChecks")),
            "fieldDiffCountVsS00Success": ((audit.get("control") or {}).get("fieldDiffCountVsS00Success")),
        },
        "conclusion": audit.get("conclusion"),
    }


def asset_lineage_combo_control_summary() -> dict[str, Any]:
    path = PROTO / "goal_audit/asset_lineage_combo_control_audit.json"
    audit = load_json(path) or {}
    return {
        "path": str(path.resolve()),
        "exists": path.exists(),
        "checks": audit.get("checks"),
        "control": {
            "directChecks": ((audit.get("control") or {}).get("directChecks")),
            "comboChecks": ((audit.get("control") or {}).get("comboChecks")),
            "fieldDiffCountVsS00Success": ((audit.get("control") or {}).get("fieldDiffCountVsS00Success")),
        },
        "conclusion": audit.get("conclusion"),
    }


def sendbeacon_temporal_boundary_summary() -> dict[str, Any]:
    path = PROTO / "goal_audit/sendbeacon_temporal_boundary_audit.json"
    audit = load_json(path) or {}
    return {
        "path": str(path.resolve()),
        "exists": path.exists(),
        "checks": audit.get("checks"),
        "js": {
            "firstSuccessJsLine": ((audit.get("js") or {}).get("firstSuccessJsLine")),
            "firstBeaconJsLine": ((audit.get("js") or {}).get("firstBeaconJsLine")),
            "firstBeaconMinusFirstSuccessSeconds": ((audit.get("js") or {}).get("firstBeaconMinusFirstSuccessSeconds")),
        },
        "runtimeBeaconRequestLines": (((audit.get("runtime") or {}).get("beaconRequestLines"))),
        "conclusion": audit.get("conclusion"),
    }


def crcldu_sync_message_boundary_summary() -> dict[str, Any]:
    path = PROTO / "goal_audit/crcldu_sync_message_boundary_audit.json"
    audit = load_json(path) or {}
    return {
        "path": str(path.resolve()),
        "exists": path.exists(),
        "checks": audit.get("checks"),
        "js": {
            "firstSuccessDispatchLine": ((audit.get("js") or {}).get("firstSuccessDispatchLine")),
            "crclduMessageCount": len(((audit.get("js") or {}).get("crclduMessages")) or []),
            "preSuccessCrclduMessageCount": len(((audit.get("js") or {}).get("preSuccessCrclduMessages")) or []),
        },
        "runtime": {
            "crclduNetworkRows": ((audit.get("runtime") or {}).get("crclduNetworkRows")),
        },
        "conclusion": audit.get("conclusion"),
    }


def latest_asset_lineage_encoded_boundary_summary() -> dict[str, Any]:
    path = PROTO / "goal_audit/latest_asset_lineage_encoded_boundary_audit.json"
    audit = load_json(path) or {}
    return {
        "path": str(path.resolve()),
        "exists": path.exists(),
        "checks": audit.get("checks"),
        "diff": audit.get("diff"),
        "acceptedS00": {
            "bodyLenBytes": ((audit.get("acceptedS00") or {}).get("bodyLenBytes")),
            "bodySha256": ((audit.get("acceptedS00") or {}).get("bodySha256")),
            "payloadSha256": ((audit.get("acceptedS00") or {}).get("payloadSha256")),
        },
        "freshRejected": {
            "bodyLenBytes": ((audit.get("freshRejected") or {}).get("bodyLenBytes")),
            "bodySha256": ((audit.get("freshRejected") or {}).get("bodySha256")),
            "payloadSha256": ((audit.get("freshRejected") or {}).get("payloadSha256")),
        },
        "conclusion": audit.get("conclusion"),
    }


def latest_exact_payload_body_controls_summary() -> dict[str, Any]:
    path = PROTO / "goal_audit/latest_exact_payload_body_controls_audit.json"
    audit = load_json(path) or {}
    return {
        "path": str(path.resolve()),
        "exists": path.exists(),
        "checks": audit.get("checks"),
        "exactPayloadPcFreshOuter": {
            "session": ((audit.get("exactPayloadPcFreshOuter") or {}).get("session")),
            "assetLineageChecksOk": ((audit.get("exactPayloadPcFreshOuter") or {}).get("assetLineageChecksOk")),
            "comboChecks": ((audit.get("exactPayloadPcFreshOuter") or {}).get("comboChecks")),
            "materialChecks": ((audit.get("exactPayloadPcFreshOuter") or {}).get("materialChecks")),
            "seq5": {
                key: (((audit.get("exactPayloadPcFreshOuter") or {}).get("seq5") or {}).get(key))
                for key in ["status", "bodyText", "handlers", "hasSuccessHandler"]
            },
        },
        "exactWholeBody": {
            "session": ((audit.get("exactWholeBody") or {}).get("session")),
            "assetLineageChecksOk": ((audit.get("exactWholeBody") or {}).get("assetLineageChecksOk")),
            "comboChecks": ((audit.get("exactWholeBody") or {}).get("comboChecks")),
            "materialChecks": ((audit.get("exactWholeBody") or {}).get("materialChecks")),
            "seq5": {
                key: (((audit.get("exactWholeBody") or {}).get("seq5") or {}).get(key))
                for key in ["status", "bodyText", "handlers", "hasSuccessHandler"]
            },
        },
        "conclusion": audit.get("conclusion"),
    }


def s00_line933_state_window_summary() -> dict[str, Any]:
    path = PROTO / "goal_audit/s00_line933_state_window_audit.json"
    audit = load_json(path) or {}
    runtime = (((audit.get("s00Window") or {}).get("runtime")) or [])
    decoded = (((audit.get("s00Window") or {}).get("collectorDecoded")) or [])
    return {
        "path": str(path.resolve()),
        "exists": path.exists(),
        "checks": audit.get("checks"),
        "runtime": [
            {
                key: row.get(key)
                for key in ["line", "t", "kind", "urlClass", "method", "status", "seq", "rsc", "hasCookieHeader"]
            }
            for row in runtime
        ],
        "collectorDecoded": [
            {
                "collectorLine": row.get("collectorLine"),
                "handlers": row.get("handlers"),
                "successParts": row.get("successParts"),
            }
            for row in decoded
        ],
        "conclusion": audit.get("conclusion"),
    }


def seq6_response_first_control_summary() -> dict[str, Any]:
    path = PROTO / "goal_audit/seq6_response_first_control_audit.json"
    audit = load_json(path) or {}
    return {
        "path": str(path.resolve()),
        "exists": path.exists(),
        "checks": audit.get("checks"),
        "s00": audit.get("s00"),
        "control": {
            "session": ((audit.get("control") or {}).get("session")),
            "comboChecks": ((audit.get("control") or {}).get("comboChecks")),
            "timing": ((audit.get("control") or {}).get("timing")),
            "seq5": ((audit.get("control") or {}).get("seq5")),
        },
        "conclusion": audit.get("conclusion"),
    }


def h2_multiplex_control_summary() -> dict[str, Any]:
    path = PROTO / "goal_audit/h2_multiplex_control_audit.json"
    audit = load_json(path) or {}
    return {
        "path": str(path.resolve()),
        "exists": path.exists(),
        "checks": audit.get("checks"),
        "s00Evidence": audit.get("s00Evidence"),
        "control": {
            "comboChecks": ((audit.get("control") or {}).get("comboChecks")),
            "timing": ((audit.get("control") or {}).get("timing")),
            "seq5Transport": (((audit.get("control") or {}).get("seq5") or {}).get("transport")),
            "seq6Transport": (((audit.get("control") or {}).get("seq6") or {}).get("transport")),
            "seq5Handlers": (((audit.get("control") or {}).get("seq5") or {}).get("handlers")),
            "seq5HasSuccessHandler": (((audit.get("control") or {}).get("seq5") or {}).get("hasSuccessHandler")),
            "activityChecks": ((audit.get("control") or {}).get("activityChecks")),
            "fieldChecks": ((audit.get("control") or {}).get("fieldChecks")),
            "fieldDiffCountVsS00Success": ((audit.get("control") or {}).get("fieldDiffCountVsS00Success")),
        },
        "conclusion": audit.get("conclusion"),
    }


def h2_dual_activity_equal_control_summary() -> dict[str, Any]:
    path = PROTO / "goal_audit/h2_dual_activity_equal_control_audit.json"
    audit = load_json(path) or {}
    return {
        "path": str(path.resolve()),
        "exists": path.exists(),
        "checks": audit.get("checks"),
        "directChecks": audit.get("directChecks"),
        "comboChecks": audit.get("comboChecks"),
        "timing": audit.get("timing"),
        "activityEvidence": audit.get("activityEvidence"),
        "seq5": {
            "status": ((audit.get("seq5") or {}).get("status")),
            "transport": ((audit.get("seq5") or {}).get("transport")),
            "handlers": ((audit.get("seq5") or {}).get("handlers")),
            "successParts": ((audit.get("seq5") or {}).get("successParts")),
        },
        "seq6": {
            "status": ((audit.get("seq6") or {}).get("status")),
            "transport": ((audit.get("seq6") or {}).get("transport")),
            "handlers": ((audit.get("seq6") or {}).get("handlers")),
            "successParts": ((audit.get("seq6") or {}).get("successParts")),
        },
        "conclusion": audit.get("conclusion"),
    }


def h2_first_failure_dual_activity_control_summary() -> dict[str, Any]:
    path = PROTO / "goal_audit/h2_first_failure_dual_activity_control_audit.json"
    audit = load_json(path) or {}
    return {
        "path": str(path.resolve()),
        "exists": path.exists(),
        "checks": audit.get("checks"),
        "directChecks": audit.get("directChecks"),
        "comboChecks": audit.get("comboChecks"),
        "timing": audit.get("timing"),
        "activityEvidence": audit.get("activityEvidence"),
        "seq5": {
            "status": ((audit.get("seq5") or {}).get("status")),
            "transport": ((audit.get("seq5") or {}).get("transport")),
            "handlers": ((audit.get("seq5") or {}).get("handlers")),
            "successParts": ((audit.get("seq5") or {}).get("successParts")),
        },
        "seq6": {
            "status": ((audit.get("seq6") or {}).get("status")),
            "transport": ((audit.get("seq6") or {}).get("transport")),
            "handlers": ((audit.get("seq6") or {}).get("handlers")),
            "successParts": ((audit.get("seq6") or {}).get("successParts")),
        },
        "conclusion": audit.get("conclusion"),
    }


def h2_first_failure_head_delay_control_summary() -> dict[str, Any]:
    path = PROTO / "goal_audit/h2_first_failure_head_delay_control_audit.json"
    audit = load_json(path) or {}
    return {
        "path": str(path.resolve()),
        "exists": path.exists(),
        "checks": audit.get("checks"),
        "directChecks": audit.get("directChecks"),
        "delayAfterPreCaptchaHead": audit.get("delayAfterPreCaptchaHead"),
        "comboChecks": audit.get("comboChecks"),
        "timing": audit.get("timing"),
        "activityEvidence": audit.get("activityEvidence"),
        "seq5": {
            "status": ((audit.get("seq5") or {}).get("status")),
            "transport": ((audit.get("seq5") or {}).get("transport")),
            "handlers": ((audit.get("seq5") or {}).get("handlers")),
            "successParts": ((audit.get("seq5") or {}).get("successParts")),
        },
        "seq6": {
            "status": ((audit.get("seq6") or {}).get("status")),
            "transport": ((audit.get("seq6") or {}).get("transport")),
            "handlers": ((audit.get("seq6") or {}).get("handlers")),
            "successParts": ((audit.get("seq6") or {}).get("successParts")),
        },
        "conclusion": audit.get("conclusion"),
    }


def h2_fresh_tail_strongest_control_summary() -> dict[str, Any]:
    path = PROTO / "goal_audit/h2_fresh_tail_strongest_control_audit.json"
    audit = load_json(path) or {}
    return {
        "path": str(path.resolve()),
        "exists": path.exists(),
        "checks": audit.get("checks"),
        "directChecks": audit.get("directChecks"),
        "delayAfterPreCaptchaHead": audit.get("delayAfterPreCaptchaHead"),
        "comboChecks": audit.get("comboChecks"),
        "timing": audit.get("timing"),
        "seq5Sources": audit.get("seq5Sources"),
        "activityEvidence": audit.get("activityEvidence"),
        "seq5": {
            "status": ((audit.get("seq5") or {}).get("status")),
            "transport": ((audit.get("seq5") or {}).get("transport")),
            "handlers": ((audit.get("seq5") or {}).get("handlers")),
            "successParts": ((audit.get("seq5") or {}).get("successParts")),
        },
        "seq6": {
            "status": ((audit.get("seq6") or {}).get("status")),
            "transport": ((audit.get("seq6") or {}).get("transport")),
            "handlers": ((audit.get("seq6") or {}).get("handlers")),
            "successParts": ((audit.get("seq6") or {}).get("successParts")),
        },
        "conclusion": audit.get("conclusion"),
    }


def build_audit() -> dict[str, Any]:
    classifier = load_json(PROTO / "trace_classification_v2/human_trace_classifier_v2_summary.json") or {}
    decoder = load_json(PROTO / "collector_decode/collector_decoder_coverage_audit.json") or {}
    pow_audit = load_json(PROTO / "pow/pow_to_px561_osk_audit.json") or {}
    cookie_audit = load_json(PROTO / "cookie_jar/px_cookie_jar_updater_multi_audit.json") or {}
    risk_build = load_json(PROTO / "risk_verify_build/risk_verify_build_ni109xdjp5zp_1780948211.json") or {}
    wasm_nq_legacy = load_json(PROTO / "wasm/captcha_wasm_nq_replay_tuisye6ib170_1781129289.json") or {}
    wasm_nq_pxuuid = load_json(PROTO / "wasm/captcha_wasm_nq_replay_s00ld1lglrw0_1781191381.json") or {}
    wasm_import_pxuuid = load_json(PROTO / "wasm/wasm_import_calls_s00ld1lglrw0_1781191381.json") or {}

    classifier_runs = classifier.get("runs") or []
    stage_counts: dict[str, int] = {}
    for run in classifier_runs:
        stage = run.get("stage") or "unknown"
        stage_counts[stage] = stage_counts.get(stage, 0) + 1

    collector_build = collector_request_build_summary()
    px561_constructor = px561_constructor_summary()
    live_probe = live_probe_summary()
    inner_payload = experimental_inner_payload_summary()
    coupling = value_source_coupling_summary()
    same_session_coverage = same_session_material_coverage_summary()
    same_session_value_chain = same_session_value_chain_summary()
    success_constructor_spec = success_constructor_spec_summary()
    exact_success_replay = exact_success_replay_summary()
    success_session_state_boundary = success_session_state_boundary_summary()
    fresh_state_param_sources = fresh_state_param_sources_summary()
    fresh_bootstrap_live_probe = fresh_bootstrap_live_probe_summary()
    fresh_second_live_probe = fresh_second_live_probe_summary()
    fresh_sequence_live_probe = fresh_sequence_live_probe_summary()
    fresh_bundle_live_probe = fresh_bundle_live_probe_summary()
    fresh_px561_template_probe = latest_fresh_px561_probe_summary("template")
    fresh_px561_offline_ng_probe = latest_fresh_px561_probe_summary("offline-ng")
    fresh_px561_diff = latest_fresh_px561_diff_summary()
    fresh_bundle_progression = latest_fresh_bundle_progression_summary()
    progression_convergence = progression_px561_convergence_summary()
    exact_activities_outer_diff = exact_activities_outer_request_diff_summary()
    outer_binding_controls = outer_binding_controls_summary()
    px561_stateful_retry = px561_stateful_retry_summary()
    post_px_retry_fresh_pow_attempt = post_px_retry_fresh_pow_attempt_summary()
    aeax_control_after_post_retry = aeax_control_after_post_retry_summary()
    fresh_first_failure_history = fresh_first_failure_history_summary()
    clean_history_line922_guard = clean_history_line922_guard_summary()
    clean_history_controls = clean_history_controls_summary()
    clean_history_exact_px561_control = clean_history_exact_px561_control_summary()
    clean_history_exact_whole_activities = clean_history_exact_whole_activities_summary()
    clean_history_outer_binding = clean_history_outer_binding_summary()
    clean_history_payload_pc_controls = clean_history_payload_pc_controls_summary()
    clean_history_pc_uuid_controls = clean_history_pc_uuid_controls_summary()
    clean_history_form_outer_controls = clean_history_form_outer_controls_summary()
    captcha_head_control = captcha_head_control_summary()
    captcha_head_delay_control = captcha_head_delay_control_summary()
    wasm_ng_runtime_random_replay = wasm_ng_runtime_random_replay_summary()
    direct_webshare_ip_hypothesis = direct_webshare_ip_hypothesis_summary()
    collector_request_context_diff = collector_request_context_diff_summary()
    seq5_seq6_timing_control = seq5_seq6_timing_control_summary()
    direct_exact_whole_activities_seq5 = direct_exact_whole_activities_seq5_summary()
    cookie_session_lineage_gap = cookie_session_lineage_gap_summary()
    stk_ns_control = stk_ns_control_summary()
    s00_unreplayed_event_matrix = s00_unreplayed_event_matrix_summary()
    captcha_asset_combo_control = captcha_asset_combo_control_summary()
    asset_lineage_combo_control = asset_lineage_combo_control_summary()
    sendbeacon_temporal_boundary = sendbeacon_temporal_boundary_summary()
    crcldu_sync_message_boundary = crcldu_sync_message_boundary_summary()
    latest_asset_lineage_encoded_boundary = latest_asset_lineage_encoded_boundary_summary()
    latest_exact_payload_body_controls = latest_exact_payload_body_controls_summary()
    s00_line933_state_window = s00_line933_state_window_summary()
    seq6_response_first_control = seq6_response_first_control_summary()
    h2_multiplex_control = h2_multiplex_control_summary()
    h2_dual_activity_equal_control = h2_dual_activity_equal_control_summary()
    h2_first_failure_dual_activity_control = h2_first_failure_dual_activity_control_summary()
    h2_first_failure_head_delay_control = h2_first_failure_head_delay_control_summary()
    h2_fresh_tail_strongest_control = h2_fresh_tail_strongest_control_summary()

    requirements = [
        {
            "id": "trace_classifier",
            "requirement": "成功/失败 trace 分类器可复现，并区分 accepted success、tf failure、AEAx-only negative control 等阶段。",
            "status": "proved",
            "evidence": [
                check_file(PROTO / "trace_classification_v2/human_trace_classifier_v2_summary.json"),
                {
                    "runCount": classifier.get("runCount"),
                    "stageCounts": stage_counts,
                    "observationControlCount": classifier.get("observationControlCount"),
                },
            ],
        },
        {
            "id": "collector_response_decoder",
            "requirement": "collector response 离线解码器可复现，并能用 decoded oIIoIooo success handler 区分成功/失败样本。",
            "status": "proved" if (decoder.get("checks") or {}).get("allRowsMatchExpectedSuccessHandler") else "incomplete",
            "evidence": [
                check_file(PROTO / "collector_decode/collector_decoder_coverage_audit.json"),
                {"checks": decoder.get("checks")},
            ],
        },
        {
            "id": "collector_payload_constructor",
            "requirement": "collector payload 构造可离线复现浏览器已发送 body，并可构造带 live OSk/Bzt/fresh TBR9 的实验性 encoded body。",
            "status": "proved" if collector_build["allExact"] and px561_constructor["requiredChecksPass"] else "partly_proved",
            "evidence": [
                collector_build,
                px561_constructor,
                {
                    "limitation": (
                        "现有证据证明已观测 collector 请求 body 可精确重建，且 PX561 实验 body 已使用 live OSk/Bzt/fresh TBR9；"
                        "但 collector accepted 仍属于 end_to_end_pure_protocol_poc 要求，不能由构造器单独证明。"
                    )
                },
            ],
        },
        {
            "id": "pow_recompute",
            "requirement": "POW 可复算并写入 PX561 OSkIb39DDA。",
            "status": "proved" if all((pow_audit.get("checks") or {}).get(k) for k in [
                "acceptedRowsHaveValidOsk",
                "acceptedRowsMatchPowHit",
                "acceptedRowsMatchCollectorChallengeHash",
            ]) else "incomplete",
            "evidence": [
                check_file(PROTO / "pow/pow_to_px561_osk_audit.json"),
                {"checks": pow_audit.get("checks")},
            ],
        },
        {
            "id": "px_cookie_token_update",
            "requirement": "_px cookie/token 更新可由 decoded collector handlers 离线回放，并匹配 Microsoft risk/verify 请求。",
            "status": "partly_proved" if (cookie_audit.get("checks") or {}).get("anyRunProvesContinueRiskVerifyMatchesJar") else "incomplete",
            "evidence": [
                check_file(PROTO / "cookie_jar/px_cookie_jar_updater_multi_audit.json"),
                {"checks": cookie_audit.get("checks")},
            ],
        },
        {
            "id": "risk_verify_rebuild",
            "requirement": "Microsoft risk/verify 与 CreateAccount 请求体可离线重建到 runtime 等价。",
            "status": "proved" if all((risk_build.get("checks") or {}).values()) else "incomplete",
            "evidence": [
                check_file(PROTO / "risk_verify_build/risk_verify_build_ni109xdjp5zp_1780948211.json"),
                {"checks": risk_build.get("checks")},
            ],
        },
        {
            "id": "fresh_tbr9_ws_nq",
            "requirement": "可离线复现 fresh TBR9Ugl7emA= / Ws.NQ(n)，用于替换 stale template TBR9。",
            "status": "proved" if (
                (wasm_nq_pxuuid.get("checks") or {}).get("pxUuidReplayMatchesAnyTrace")
                and (wasm_import_pxuuid.get("checks") or {}).get("nqGetPropIsPxUuid")
                and (wasm_import_pxuuid.get("checks") or {}).get("nqStringGetReturnsUuid")
                and (wasm_import_pxuuid.get("checks") or {}).get("nqReturnMatchesTbrAfterNq")
            ) else "blocked_by_missing_evidence",
            "evidence": [
                check_file(PROTO / "wasm/captcha_wasm_nq_replay_s00ld1lglrw0_1781191381.json"),
                check_file(PROTO / "wasm/wasm_import_calls_s00ld1lglrw0_1781191381.json"),
                {
                    "pxUuidReplayChecks": wasm_nq_pxuuid.get("checks"),
                    "importChecks": wasm_import_pxuuid.get("checks"),
                    "wrapperMapping": (wasm_nq_pxuuid.get("wrapperMapping") or {}).get("decoded"),
                    "legacyNoPxUuidReplayChecks": wasm_nq_legacy.get("checks"),
                    "interpretation": (
                        "Runtime import hooks prove Ws.NQ reads global _pxUuid and __wbindgen_string_get returns the captcha URL UUID. "
                        "Offline replay with that protocol-visible _pxUuid reproduces the runtime Ws.NQ/TBR9 value."
                    ),
                },
            ],
        },
        {
            "id": "fresh_aeax_ws_ng",
            "requirement": "可离线复现 Ws.Ng/AEAx：给定 captcha wasm、_pxUuid 和 runtime crypto random bytes，offline Ng 输出必须等于 runtime AEAx。",
            "status": "proved" if all((wasm_ng_runtime_random_replay.get("checks") or {}).get(k) is True for k in [
                "hasNineRandomHex",
                "randomLensMatchOfflineNgShape",
                "offlineNgMatchesRuntimeAeax",
                "offlineNqMatchesRuntimeTbr9",
                "offlineNqExpectMatches",
                "usedPxUuidImportPath",
                "allReplayRandomSourcesProvided",
            ]) else "blocked_by_missing_evidence",
            "evidence": [
                wasm_ng_runtime_random_replay,
                {
                    "interpretation": (
                        "Browser runtime hook now captures the bytes written by the wasm random imports during Ws.Ng. "
                        "Using those nine captured random buffers, the extracted captcha wasm, and the observed _pxUuid, "
                        "offline replay reproduces both runtime AEAx/Ng and TBR9/NQ exactly. "
                        "This closes the previous AEAx determinism gap; it does not by itself prove collector acceptance of a no-browser fresh PX561."
                    )
                },
            ],
        },
        {
            "id": "end_to_end_pure_protocol_poc",
            "requirement": "端到端纯协议 PoC 不依赖浏览器/Camoufox/鼠标/视觉/外部打码，能复现 HUMAN 成功包。",
            "status": "not_proved",
            "evidence": [
                live_probe,
                inner_payload,
                coupling,
                same_session_coverage,
                same_session_value_chain,
                success_constructor_spec,
                success_session_state_boundary,
                fresh_state_param_sources,
                fresh_bootstrap_live_probe,
                fresh_second_live_probe,
                fresh_sequence_live_probe,
                fresh_bundle_live_probe,
                {
                    "freshBundleProgressionProbe": fresh_bundle_progression,
                    "interpretation": (
                        "A no-browser non-PX561 bundle progression probe sent seq1, seq3, and seq4 templates after the fresh first bundle. "
                        "All three returned HTTP 200; seq4 returned a new IooIIo POW challenge plus fresh Jo/ci state. "
                        "This proves collector state progression can be advanced further without browser rendering, but it does not by itself prove accepted PX561."
                    ),
                },
                {
                    "freshPx561TemplateAeaxProbe": fresh_px561_template_probe,
                    "interpretation": (
                        "This same-session no-browser PX561 probe used fresh OSk/TBR9/Bzt and fresh uuid/p1/ci/cs, "
                        "but left AEAx/Ew9i/KVk/behavior arrays from the s00 template. Collector returned HTTP 200 and decoded _px3/_pxde, "
                        "but hasSuccessHandler=false and oIIoIooo|-1, so copied AEAx/material is not sufficient."
                    ),
                },
                {
                    "freshPx561OfflineNgAeaxProbe": fresh_px561_offline_ng_probe,
                    "interpretation": (
                        "This same-session no-browser PX561 probe additionally replaced AEAxBkUsPjQ= with fresh offline Ws.Ng output. "
                        "Collector still returned HTTP 200, decoded _px3/_pxde, score|1|binary, and oIIoIooo|-1. "
                        "Therefore current evidence disproves 'fresh OSk + fresh TBR9 + fresh offline Ng AEAx + copied behavior arrays' as a sufficient success packet."
                    ),
                },
                {
                    "freshPx561FailureDiff": fresh_px561_diff,
                    "interpretation": (
                        "Decoded fresh PX561 failure payload now proves marker decoding is valid and the payload key order is still identical to s00 line566 failure template, "
                        "not s00 line922 success. The diff proves Ew9iCVZkZD4=, KVkYX28zG2o=, and behavior arrays DzN+dUlTekE=/GUloT18mZ3U=/JnpXfGMUUUc= remain copied from the failure template; "
                        "s00 success adds LVUcU2s1Gmc= near the DOM/pointer field block and changes Ew9i/KVk/DzN+dUlTekE=. "
                        "This is evidence that remaining live-accepted gap is outside the already-fresh OSk/TBR9/offline-Ng tail."
                    ),
                },
                {
                    "progressionPx561Convergence": progression_convergence,
                    "interpretation": (
                        "The latest convergence controls prove three facts. First, a progression+line922 control can make the PX561 activity field-equivalent to s00 accepted line922 "
                        "while collector still returns oIIoIooo|-1. Second, that exact-inner control still had non-PX561 activity diffs. Third, a stricter live control then kept "
                        "the whole decoded activity array equal to s00 accepted line922 and was still rejected. Therefore standalone decoded activity-array equivalence is not sufficient; "
                        "the remaining gap is outside decoded activities and must be tested in outer form/session/cookie/history state, request context, or prior server-side state."
                    ),
                },
                {
                    "exactActivitiesOuterRequestDiff": exact_activities_outer_diff,
                    "interpretation": (
                        "After decoded activity-array equality was proved and still rejected, the outer request diff identifies the remaining observable variable set: "
                        "payload encoding string plus uuid/cs/pc/sid/p1/vid/ci/cts differ, while appId/tag/ft/seq/en/rsc and URL are equal. "
                        "This moves the next proof target to payload encoding marker/pc binding, outer session params, headers/cookies, or accumulated server-side state."
                    ),
                },
                {
                    "outerBindingControls": outer_binding_controls,
                    "interpretation": (
                        "Marker/qi choice was tested as an outer binding variable while decoded activities remained equal to s00 line922. "
                        "Fresh outer state failed with both fresh and template marker encodings, and the fully stale exact body is already known to fail on live replay. "
                        "Thus marker choice alone is not sufficient; the next boundary is coherent live session/cookie/server-side state, not payload activity content or marker alone."
                    ),
                },
                {
                    "px561StatefulRetry": px561_stateful_retry,
                    "interpretation": (
                        "A rejected exact-activity PX561 response returned updated _px3/_pxde; a follow-up exact-activity PX561 request used those updated values and still returned oIIoIooo|-1. "
                        "This disproves a single rejected-PX561 token update round as sufficient for success."
                    ),
                },
                {
                    "postPxRetryFreshPowAttempt": post_px_retry_fresh_pow_attempt,
                    "interpretation": (
                        "After a rejected exact-activity PX561 response, non-PX seq3/seq4 still advanced state and returned a new POW. "
                        "A follow-up PX561 using that new solved POW, fresh Ws.NQ TBR9, and offline Ng still returned oIIoIooo|-1. "
                        "This disproves a post-rejection fresh POW/TBR9/Ng cycle as sufficient with the current template-derived activity material."
                    ),
                },
                {
                    "aeaxControlAfterPostRetry": aeax_control_after_post_retry,
                    "interpretation": (
                        "Older s00 traces did not capture the random bytes needed to deterministically replay that accepted s00 AEAx, so the old audit could not reproduce s00 AEAx exactly. "
                        "The newer runtime-random replay audit below closes the general Ws.Ng determinism gap on a fresh browser cycle by matching runtime AEAx and TBR9 exactly. "
                        "A post-retry template-AEAx control still failed while holding accepted AEAx and fresh OSk/TBR9, so the latest failure is not explained solely by offline Ng."
                    ),
                },
                {
                    "wasmNgRuntimeRandomReplay": wasm_ng_runtime_random_replay,
                    "interpretation": (
                        "Runtime randomHex capture plus offline wasm replay proves AEAx/Ws.Ng can be generated coherently outside the browser when the same random bytes are supplied. "
                        "Therefore the remaining no-browser rejection cannot be reported as an unresolved Ng algorithm-mapping issue; the remaining accepted-PX561 gap is collector/session/state/material acceptance."
                    ),
                },
                {
                    "directWebshareIpHypothesis": direct_webshare_ip_hypothesis,
                    "interpretation": (
                        "Three fresh no-browser attempts used direct Webshare p.webshare.io:80 sessions, each reached progression POW and seq5 collector, and each returned the normal oIIoIooo rejection shape. "
                        "The egress probes succeeded and showed three distinct exit IPs. This does not prove IP reputation is irrelevant globally, but it disproves simple same-IP/sticky-session reuse as the observed blocker for these attempts."
                    ),
                },
                {
                    "collectorRequestContextDiff": collector_request_context_diff,
                    "interpretation": (
                        "A strict header-order parity control sent a fresh direct-Webshare seq5 request with the same method, URL, header order, and form parameter order as s00 accepted line933. "
                        "The only header value difference was content-length, while form value differences remained ci/cs/cts/p1/payload/pc/sid/uuid/vid. "
                        "Collector still returned the normal oIIoIooo rejection. Therefore HTTP header value/order and form-order parity are not sufficient; the remaining boundary is body/session/server-side state."
                    ),
                },
                {
                    "seq5Seq6TimingControl": seq5_seq6_timing_control,
                    "interpretation": (
                        "s00 accepted line933 had an overlapping seq5/seq6 request pattern: seq6 started about 0.1816s after seq5 and before the first response. "
                        "A no-browser parallel control reproduced that overlap and gap within 50ms while preserving strict header parity. It still returned normal rejection. "
                        "Therefore seq5/seq6 overlap timing is not sufficient."
                    ),
                },
                {
                    "directExactWholeActivitiesSeq5": direct_exact_whole_activities_seq5,
                    "interpretation": (
                        "A later direct-Webshare fresh session set the seq5 decoded activity array byte-for-byte equivalent to s00 accepted line922/line933 material: "
                        "activity diff checks show wholeActivitiesEqual=true, px561ActivityEqual=true, nonPx561ActivitiesAllEqual=true; "
                        "field diff count vs s00 success is 0 and key order equals s00 success. The seq5 collector request still returned the normal oIIoIooo|-1 handler. "
                        "In this run the paired seq6 also reached collector with HTTP 200 in parallel mode at the s00-observed 0.1816s gap, while no success handler was returned. "
                        "This proves decoded seq5 payload equality plus delivered seq6-pair timing is still not sufficient."
                    ),
                },
                {
                    "cookieSessionLineageGap": cookie_session_lineage_gap,
                    "interpretation": (
                        "With seq5 decoded whole activities equal to s00 success and seq6 delivered, the next observable boundary is cookie/session lineage. "
                        "The s00 browser trace has correlated parent postMessage cookie bridge events for decoded _px3/_pxde/_pxvid before success and a parent challenge_success message. "
                        "The direct no-browser run preserves protocol-side decoded cookie/token updates but has no browser parent bridge artifact and still rejects. "
                        "Both s00 line933 and fresh seq5 have no collector Cookie request header, so this is not a simple missing Cookie header difference. "
                        "This does not prove the bridge causes success; it makes parent/cookie/session bridge lineage a concrete next target rather than decoded payload content."
                    ),
                },
                {
                    "stkNsControl": stk_ns_control,
                    "interpretation": (
                        "s00 has stk.hsprotect.net/ns?c=<uuid> requests before the accepted line933. "
                        "A direct no-browser control replayed the initial stk/ns GET with the same fresh uuid before bootstrap and received HTTP 200, "
                        "then sent delivered seq5+seq6 with seq5 decoded activities and fields exactly equal to s00 success. It still returned oIIoIooo|-1. "
                        "Therefore stk/ns replay alone is not sufficient."
                    ),
                },
                {
                    "s00UnreplayedEventMatrix": s00_unreplayed_event_matrix,
                    "interpretation": (
                        "After stk/ns, captcha.js GET/HEAD, iframe GET, main.js GET, and main.js HEAD were tested, a matrix of s00 runtime and JS events before accepted line933 shows the latest direct control still does not replay sendBeacon internals. "
                        "The next narrow target is therefore sendBeacon/internal message dispatch or deeper collector server-side state not represented by simple asset hits."
                    ),
                },
                {
                    "captchaAssetComboControl": captcha_asset_combo_control,
                    "interpretation": (
                        "A combined direct lineage replayed stk/ns, captcha.js GET, and captcha.js HEAD with fresh uuid/vid, then delivered seq5+seq6 with seq5 decoded activities and fields exactly equal to s00 success. "
                        "It still returned oIIoIooo|-1, so captcha.js GET/HEAD placement plus stk/ns is not sufficient."
                    ),
                },
                {
                    "assetLineageComboControl": asset_lineage_combo_control,
                    "interpretation": (
                        "The latest direct Webshare control additionally replayed iframe.hsprotect.net line171 with fresh sid and fresh _px cookies, "
                        "client.hsprotect.net main.min.js line185 with fresh _px cookies, line265 main HEAD, captcha GET with fresh _px cookies, captcha HEAD, and stk/ns. "
                        "All returned OK/cacheable status, seq5/seq6 were delivered, and seq5 decoded whole activities/fields remained equal to s00 success. "
                        "Collector still returned oIIoIooo|-1, so simple iframe/main/captcha asset-load lineage is not sufficient."
                    ),
                },
                {
                    "sendBeaconTemporalBoundary": sendbeacon_temporal_boundary,
                    "interpretation": (
                        "s00 sendBeacon events are observed after the oIIoIooo|0 success handler by JS line order and wall time, and runtime beacon POSTs appear after the success console events. "
                        "Therefore current evidence does not support sendBeacon as a pre-success prerequisite for accepted line933; the remaining missing condition is more likely pre-success server/session/material state not captured by decoded activity equality or simple asset hits."
                    ),
                },
                {
                    "crclduSyncMessageBoundary": crcldu_sync_message_boundary,
                    "interpretation": (
                        "s00 has crcldu.com/bd/sync.html opaque window.message.recv events, including one before the accepted collector window. "
                        "The runtime trace shows these as console-observed postMessage events only and has no crcldu request/response rows after the messages. "
                        "This makes crcldu a browser/third-frame state artifact to track, but current evidence does not show a direct collector server-side mutation through crcldu network traffic."
                    ),
                },
                {
                    "latestAssetLineageEncodedBoundary": latest_asset_lineage_encoded_boundary,
                    "interpretation": (
                        "For the latest direct Webshare asset-lineage control, decoded seq5 activities and fields equal s00 success and body/payload lengths match s00 line933, yet collector rejects. "
                        "The only form differences are payload, pc, and live session params uuid/cs/sid/p1/vid/ci/cts. "
                        "This makes encoded payload/pc/session/server-state binding the current narrow boundary."
                    ),
                },
                {
                    "latestExactPayloadBodyControls": latest_exact_payload_body_controls,
                    "interpretation": (
                        "Two new direct Webshare sessions used the full asset-lineage preload set. "
                        "Exact s00 payload+pc with fresh outer session params was verified by material checks payloadEqualsTemplate=true, pcEqualsTemplate=true, bodyEqualsTemplate=false and returned {do:[]}. "
                        "Exact whole s00 body was verified by bodyEqualsTemplate=true and returned oIIoIooo|-1. "
                        "Both had HTTP 200 and no success handler. This confirms the current boundary is not solved by byte-identical body replay or by exact payload+pc alone; "
                        "the missing condition remains live collector/session/server-side state binding."
                    ),
                },
                {
                    "s00Line933StateWindow": s00_line933_state_window,
                    "interpretation": (
                        "The accepted s00 state window is now pinned to concrete events: line933 seq5 request has no Cookie header, "
                        "line937 seq6 request follows, line938 seq6 response is decoded at collector line926 with _px3/_pxde, "
                        "parent bridge lines946/947 carry those values, and line961/collector line948 returns oIIoIooo|0. "
                        "This shows a real browser lineage transition immediately before success without relying on source comments or guesses."
                    ),
                },
                {
                    "seq6ResponseFirstControl": seq6_response_first_control,
                    "interpretation": (
                        "A new direct Webshare control reduced the seq5/seq6 gap to force seq6 response completion before seq5, matching the observed s00 response order. "
                        "Full asset-lineage preloads were OK and both collector requests returned HTTP 200, but seq5 still returned oIIoIooo|-1. "
                        "Therefore response order alone is not sufficient; the remaining boundary is deeper collector/session state or browser bridge state, not just request/response timing."
                    ),
                },
                {
                    "h2MultiplexControl": h2_multiplex_control,
                    "interpretation": (
                        "s00 response headers show x-firefox-spdy=h2 for the seq6 and seq5 bundle responses. "
                        "A new h2 control negotiated ALPN h2 through Webshare and sent seq5/seq6 as streams 1 and 3 on one TLS session, with seq6 completing first. "
                        "Its seq5 decoded activity array equals s00 accepted line922 and PX561 field diff count vs s00 success is 0. "
                        "Seq5 still returned oIIoIooo|-1. Therefore the missing condition is not explained by HTTP/1.1 vs HTTP/2, lack of multiplexing, response order, or decoded payload equality alone."
                    ),
                },
                {
                    "h2DualActivityEqualControl": h2_dual_activity_equal_control,
                    "interpretation": (
                        "A stronger direct Webshare control now combines full asset-lineage preloads, one h2 TLS session, stream 1/3 seq5/seq6, seq6 response first, "
                        "seq5 decoded whole-activity equality to s00 line922, seq5 PX561 field diff count 0, and seq6 decoded whole-activity equality to s00 line925. "
                        "The collector still returned seq5 oIIoIooo|-1. This rules out the previous remaining possibility that seq6 request-body content mismatch caused the h2 rejection."
                    ),
                },
                {
                    "h2FirstFailureDualActivityControl": h2_first_failure_dual_activity_control,
                    "interpretation": (
                        "The previously uncombined boundary was tested in one fresh direct Webshare session: s00-style first rejected PX561 history was included and updated state, "
                        "full asset-lineage preloads were OK, seq5/seq6 used one h2 TLS session with streams 1/3, seq6 completed first, seq5 decoded whole activities equaled s00 line922 with PX561 field diff count 0, "
                        "and seq6 decoded whole activity equaled s00 line925. Seq5 still returned oIIoIooo|-1. "
                        "Therefore the remaining gap is not the missing first-failure lineage combined with h2 dual decoded-body equality."
                    ),
                },
                {
                    "h2FirstFailureHeadDelayControl": h2_first_failure_head_delay_control,
                    "interpretation": (
                        "The captcha HEAD delay boundary was also combined into the strongest no-browser control. "
                        "In one fresh Webshare session, the run included first-failure history, full asset-lineage, captcha HEAD, an observed 52.8s delay, one h2 seq5/seq6 TLS session, seq6 response first, "
                        "seq5 decoded equality to s00 line922 with PX561 field diff count 0, and seq6 decoded equality to s00 line925. Seq5 still returned oIIoIooo|-1. "
                        "Therefore HEAD timing is not the sufficient missing condition when combined with the other narrowed variables."
                    ),
                },
                {
                    "h2FreshTailStrongestControl": h2_fresh_tail_strongest_control,
                    "interpretation": (
                        "A fresh server-bound variant was tested after the static decoded-equality controls: it used fresh POW OSk, offline Ws.Ng/Ws.NQ AEAx/TBR9, solved Bzt, fresh session fields, "
                        "first-failure history, full asset-lineage, the observed HEAD delay, one h2 TLS session, seq6-body-first ordering, and seq6 response first. "
                        "Seq6 decoded activity still equaled s00 line925, while seq5 returned oIIoIooo|-1. "
                        "This proves that the current pure-protocol POW/WASM material path is live and server-bound, but still insufficient for HUMAN acceptance."
                    ),
                },
                {
                    "freshFirstFailureHistory": fresh_first_failure_history,
                    "interpretation": (
                        "A clean fresh no-browser session explicitly mirrored the observed first failure shape: bootstrap, second request, req2/req3, first bundle POW, "
                        "line566-shaped PX561 with solved POW and offline Ws.NQ TBR9, rejected response state update, then seq3/seq4 to a new POW, followed by line922-shaped PX561. "
                        "The final line922-shaped request still returned oIIoIooo|-1. Therefore the missing condition is not simply the presence of a prior first-failure PX561 history."
                    ),
                },
                {
                    "cleanHistoryLine922Guard": clean_history_line922_guard,
                    "interpretation": (
                        "The line922 probe builder was corrected to avoid adding line566-only first-activity state keys when those keys are absent in the line922 template. "
                        "A fresh guarded line922 attempt still returned oIIoIooo|-1, while preserving line922 first-activity key order. "
                        "This removes one constructor-artifact explanation for the clean-history rejection."
                    ),
                },
                {
                    "cleanHistoryControls": clean_history_controls,
                    "interpretation": (
                        "Single-variable controls in the same clean-history state show that using the accepted template stack string still fails, and using template Bzt still fails. "
                        "Thus neither W0shQR0nJHc= stack content nor Bzt2fUFRcw== timing alone is the sufficient missing variable."
                    ),
                },
                {
                    "cleanHistoryExactPx561Control": clean_history_exact_px561_control,
                    "interpretation": (
                        "A stronger clean-history control made the decoded PX561 activity exactly equal to s00 accepted line922 by holding template stack, tail, and inner uuid. "
                        "The request still returned oIIoIooo|-1. This moves the remaining boundary outside the PX561 activity itself."
                    ),
                },
                {
                    "cleanHistoryExactWholeActivities": clean_history_exact_whole_activities,
                    "interpretation": (
                        "The strongest clean-history activity-content control kept the entire decoded activity array equal to s00 accepted line922 and still returned oIIoIooo|-1. "
                        "This proves, in a clean first-failure-history session, that decoded activity content is not sufficient; remaining variables are encoded payload/pc, outer params, cookies/headers, or server-side state."
                    ),
                },
                {
                    "cleanHistoryOuterBinding": clean_history_outer_binding,
                    "interpretation": (
                        "Outer/body audit for the exact-whole-activities control shows same URL and body length as s00 accepted line933, but payload/body sha and outer session params differ. "
                        "A proxy-authorization header control still failed while decoded activities remained equal, so proxy-authorization/header parity is not sufficient."
                    ),
                },
                {
                    "cleanHistoryPayloadPcControls": clean_history_payload_pc_controls,
                    "interpretation": (
                        "Exact s00 payload+pc with fresh outer session params returned {do:[]} instead of oIIoIooo|-1, while template-marker/fresh-uuid still rejected with equal decoded activities. "
                        "This proves payload/pc/uuid/session binding affects collector handler generation before success can be reached."
                    ),
                },
                {
                    "cleanHistoryPcUuidControls": clean_history_pc_uuid_controls,
                    "interpretation": (
                        "Splitting payload encoding uuid from pc HMAC uuid shows exact s00 payload with fresh pc still returns {do:[]}, while fresh payload with template pc still reaches oIIoIooo|-1. "
                        "Thus pc uuid mismatch is not the isolated cause; payload encoding uuid/marker must cohere with outer session/server state."
                    ),
                },
                {
                    "cleanHistoryFormOuterControls": clean_history_form_outer_controls,
                    "interpretation": (
                        "Fresh payload/pc with template outer params returns {do:[]} when only payload and pc differ from s00 line933. "
                        "Exact s00 body with template outer params is byte-identical to s00 line933 but now returns oIIoIooo|-1. "
                        "This proves static exact body is not enough; collector server-side state/time/history remains in scope."
                    ),
                },
                {
                    "captchaHeadControl": captcha_head_control,
                    "interpretation": (
                        "s00 runtime has a captcha.js HEAD request before the accepted line933 collector request. "
                        "A fresh no-browser run sent the same HEAD shape patched to fresh uuid/vid and received HTTP 200, then sent an exact-whole-activities line922 control. "
                        "The collector still returned oIIoIooo|-1, so captcha HEAD replay alone is not sufficient."
                    ),
                },
                {
                    "captchaHeadDelayControl": captcha_head_delay_control,
                    "interpretation": (
                        "s00 runtime has about 52.8 seconds from captcha.js HEAD to accepted line933. "
                        "A fresh no-browser control sent captcha HEAD, waited the same interval within one second, then sent an exact-whole-activities line922 request. "
                        "The collector still returned oIIoIooo|-1, so HEAD plus observed delay is not sufficient."
                    ),
                },
                exact_success_replay,
                {
                    "limitation": (
                        "现有 live probe 已使用 live OSk、live Bzt 和 fresh TBR9，并且 collector 返回了 HTTP 200 且 decoded cleanly，"
                        "inner bundle payload 也能解码且 PX561 target tail index 与 accepted j0t8 对齐；"
                        "早期实验体是跨 run 拼接：outer/session 仍来自 j0t8，POW 来自 hcx，TBR9 来自 s00，handler 仍是 oIIoIooo|-1；"
                        "现在 s00 已证明存在同 session coherent 成功值链：line 933 的 OSk/TBR9 分别匹配同 session POW/Ws.NQ，并随后返回 oIIoIooo|0。"
                        "line 933 constructor spec 进一步证明 encoding/pc/marker/OSk/TBR9 可构造边界，并标出 AEAx、Bzt timing、session params、非 tail PX561 material 仍未 live-accepted。"
                        "line 933 session-state boundary audit 证明该成功请求的 cs/sid/vid/cts/ci/rsc/p1 均能从 prior decoded collector state/runtime tf material 对上，"
                        "uuid/tag/ft/seq/en 则仍只是 runtime observed。"
                        "fresh-state param source audit 已把 appId/tag/ft/en、uuid、seq、rsc 映射到静态 JS 和 runtime counter 证据，"
                        "但尚未证明无浏览器 live session 使用 fresh 生成状态后被 collector accepted。"
                        "fresh bootstrap live probe 已证明无浏览器 fresh uuid/p1 初始 /api/v2/msft 请求可本地解码、live HTTP 200、返回 decodable sid/cs/vid/cts/Jo/_px3/_pxde 初始状态；"
                        "但该响应没有 oIIoIooo|0，也没有 POW challenge。"
                        "fresh second live probe 已证明 bootstrap 返回的 sid/cs/vid/cts/Jo/_px3 可用于第二个无浏览器 /api/v2/msft 请求并获得新的 _px3/_pxde；"
                        "但仍没有 POW challenge 或 success handler。"
                        "fresh sequence live probe 进一步用 req2/req3 模板推进 /api/v2/msft，多步 HTTP 200 且响应可解码，仍未返回 POW。"
                        "fresh bundle live probe 已证明第一个无浏览器 /assets/js/bundle 请求返回 live POW challenge，且离线 solver 已解出 POW。"
                        "fresh bundle progression probe 已证明非 PX561 seq1/seq3/seq4 可在无浏览器条件下推进，并在 seq4 返回新 POW、Jo、ci。"
                        "随后基于 progression finalState、新 POW、新 offline Ng/NQ 构造的 line922 成功模板 PX561 仍 HTTP 200、可解码、返回 _px3/_pxde，但仍为 oIIoIooo|-1。"
                        "进一步的 convergence audit 证明，PX561 activity 可以被控制到与 s00 accepted line922 字段全等但仍失败；"
                        "随后更严格的 live 控制包证明 decoded activity array 整包等同 s00 accepted line922 也仍然失败。"
                        "因此当前已排除 standalone decoded activities equivalence 作为充分条件，剩余 gap 指向 outer form/session/cookie/history、request context 或 prior server-side state。"
                        "fresh PX561 live probe 已证明同一 fresh session 可构造并发送 PX561-bearing bundle："
                        "template-AEAx 版本、offline-Ng-AEAx+solve-Bzt 版本、offline-Ng-AEAx+template-Bzt 版本、progression+line922 版本均未 accepted。"
                        "fresh failure diff 进一步证明当前 payload 仍等同 s00 line566 failure key order，并复用 Ew9i/KVk/DzN 行为材料；"
                        "s00 line922 success 则多出 LVUcU2s1Gmc=，且 Ew9i/KVk/DzN 有变化。"
                        "这把缺口进一步收窄到 AEAx/OSk/TBR9 之外的 PX561 DOM/行为/状态材料或 state progression。"
                        "精确重放 s00 line 933 observed-success body 的 live probe 到达 collector 且 bodySha256 相同，但返回 oIIoIooo|-1，证明 stale fixed artifact 不能作为成功 PoC。"
                        "最新 clean fresh history audit 进一步证明：先发 line566-shaped first failure、吸收 _px3/_pxde、再推进 seq3/seq4 到新 POW、再发 line922-shaped second PX561 仍返回 oIIoIooo|-1。"
                        "随后 line922 guarded control 修正了构造器对 line922 首个 activity 误加 line566-only keys 的问题；修正后 key order 与 s00 line922 保持一致，但仍 rejected。"
                        "同一 clean-history state 下的 template-stack 与 template-Bzt 单变量对照也仍 rejected，排除了 stack 字符串或 Bzt timing 单独解释。"
                        "进一步把 PX561 activity 控制到与 s00 accepted line922 完全相等仍 rejected。"
                        "最新 clean-history exact-whole-activities control 证明整组 decoded activities 等于 s00 accepted line922 仍 rejected，因此剩余缺口不在 decoded activity content，而在 encoded payload/pc、outer params、cookies/headers 或 server-side state。"
                        "clean-history outer binding audit 进一步列出剩余 outer param keys: payload/uuid/cs/pc/sid/p1/vid/ci/cts；proxy-authorization 对照仍 rejected。"
                        "payload/pc controls 显示 exact s00 payload+pc 搭配 fresh outer 只返回 {do:[]}，template marker 搭配 fresh uuid 仍 rejected。"
                        "pc-uuid split controls 进一步显示 exact s00 payload + fresh pc 仍 {do:[]}，fresh payload + template pc 仍走 oIIoIooo|-1；因此关键不是 pc 单点，而是 payload encoding uuid/marker 与 outer session/server state 的耦合。"
                        "form-outer controls 显示 fresh payload/pc + template outer 在仅 payload/pc 不同于 s00 时返回 {do:[]}；exact s00 body byte-identical 重放则返回 oIIoIooo|-1，证明 server-side state/time/history 是剩余边界。"
                        "captcha HEAD control 进一步证明：s00 accepted line933 前观察到 captcha.hsprotect.net/PXzC5j78di/captcha.js HEAD；fresh session 发送同形 HEAD 且 HTTP 200 后，exact-whole-activities line922 仍返回 oIIoIooo|-1。"
                        "captcha HEAD delay control 再证明：按 s00 HEAD→success 约 52.8s 间隔等待后，exact-whole-activities line922 仍 rejected。"
                        "最新 wasm runtime-random replay 证明：AEAx/Ws.Ng 已能在给定 runtime randomHex 的情况下离线精确复现，"
                        "所以当前缺口不再是 Ng/NQ glue 映射或 wasm instantiate 能力本身。"
                        "direct Webshare IP/session audit 进一步证明：三个新 session、三个不同出口 IP 均同形 rejected，"
                        "所以当前证据不支持“只要换 IP/session 即可成功”的解释。"
                        "严格 header-order parity control 又证明：method、URL、header order、form order 与 s00 accepted 对齐后仍 rejected，"
                        "剩余可观测差异集中在 ci/cs/cts/p1/payload/pc/sid/uuid/vid 及 server-side state。"
                        "seq5/seq6 parallel timing control 进一步复现了 s00 约 0.1816s 重叠请求形态，但仍 rejected。"
                        "最新 direct-Webshare seq5/seq6 完整并行控制进一步证明：seq6 已 HTTP 200 送达，且 seq5 解码后的 whole activity array 与 s00 accepted 完全一致、field diff count=0、key order 相同，"
                        "但 seq5 仍返回 oIIoIooo|-1；因此 decoded payload/content equality 加已送达 seq6 pair timing 仍不充分。"
                        "cookie/session lineage audit 进一步显示 s00 accepted 前存在 decoded _px3/_pxde/_pxvid 到 parent postMessage cookie bridge 的关联事件以及 parent challenge_success，"
                        "而 direct no-browser run 只有协议内 decoded token 更新、没有 parent bridge artifact；同时 s00 line933 和 fresh seq5 都没有 collector Cookie request header，"
                        "所以这不是简单缺 Cookie header。stk/ns control 又证明 pre-bootstrap stk.hsprotect.net/ns?c=<uuid> 单点 replay HTTP 200 后仍 rejected。"
                        "同 lineage captcha asset combo control 又证明 stk/ns + captcha.js GET + captcha.js HEAD 均 HTTP 200 后，"
                        "exact-whole-activities+delivered seq6 仍 rejected。最新 asset-lineage control 进一步证明 iframe/main/captcha 带 fresh cookie 的简单 asset hits 也不充分。"
                        "未复现事件矩阵剩余 sendBeacon internals，但 sendBeacon temporal boundary audit 证明它在 oIIoIooo|0 之后发生，当前证据不支持它是 pre-success 必要条件。"
                        "crcldu sync message boundary audit 又证明 success 前存在 opaque third-frame postMessage，但 runtime 未观察到 crcldu request/response 网络副作用。"
                        "latest asset-lineage encoded boundary audit 进一步证明：在 decoded 内容全等且 body/payload 长度相等时，剩余表单差异只剩 payload、pc 和 live session params。"
                        "这些不能当作原因结论，但把下一步证据边界落到 encoded payload/pc/session/server-state binding。"
                        "最新 exact payload/body controls 进一步在新的 full asset-lineage Webshare sessions 中证明：exact s00 payload+pc + fresh outer 返回 {do:[]}，"
                        "exact whole s00 body 返回 oIIoIooo|-1，二者均无 success handler；因此 byte-identical body 或 exact payload+pc 都不是充分条件，"
                        "剩余边界仍是 live collector/session/server-side state binding。"
                        "s00 line933 state window audit 进一步把成功窗口精确钉到 line933/937 请求、line938 seq6 响应、line946/947 parent cookie bridge、line961/948 success response；"
                        "新的 seq6-response-first control 已复现 seq6 响应先于 seq5 的时序，但仍返回 oIIoIooo|-1。"
                        "h2 multiplex control 又证明：通过 Webshare 协商 ALPN h2，并在同一 TLS session 的 stream 1/3 上发送 seq5/seq6，且 seq6 先完成；"
                        "同时 seq5 decoded whole activities 与 s00 accepted 相等、PX561 field diff count=0，但仍返回 oIIoIooo|-1。"
                        "更强的 h2 dual-activity control 又证明：seq6 decoded activity 也与 s00 line925 完全相等，full asset-lineage preload 全部 OK，仍返回 oIIoIooo|-1。"
                        "最新 h2 first-failure dual-activity control 进一步把 first rejected PX561 history 也合入同一 fresh Webshare session，"
                        "并保持 full asset-lineage、h2 stream 1/3、seq6 response first、seq5/seq6 decoded bodies 全等，仍返回 oIIoIooo|-1。"
                        "随后 h2 first-failure HEAD-delay control 又把 s00 约 52.8s captcha HEAD→line933 间隔合入同一控制，仍返回 oIIoIooo|-1。"
                        "fresh server-bound strongest control 再使用 fresh POW OSk、offline Ws.Ng/Ws.NQ AEAx/TBR9、solved Bzt、fresh session fields、seq6-body-first 和 seq6 response first，仍返回 oIIoIooo|-1。"
                        "因此这仍是已观测浏览器 session artifact，不是无浏览器端到端纯协议 live PoC。"
                    )
                },
            ],
        },
    ]

    blocking = [
        r for r in requirements
        if r["status"] in {"blocked_by_missing_evidence", "not_proved", "incomplete"}
    ]
    partial = [r for r in requirements if r["status"] == "partly_proved"]
    proved = [r for r in requirements if r["status"] == "proved"]
    result = {
        "purpose": "Goal-level evidence audit for pure-protocol HUMAN success replay.",
        "repo": str(REPO),
        "requirements": requirements,
        "summary": {
            "proved": [r["id"] for r in proved],
            "partlyProved": [r["id"] for r in partial],
            "blockingOrMissing": [r["id"] for r in blocking],
            "goalComplete": not blocking and not partial,
        },
        "nextEvidenceTargets": [
            "Map server-side state effects of the captcha challenge lifecycle beyond the observed HEAD request: worker POW/captcha message events, HEAD response timing, and any collector state transitions not represented in decoded activities.",
            "Minimize and classify PX561 non-tail fields by comparing accepted success vs fresh oIIoIooo|-1 probes, prioritizing LVUcU2s1Gmc=, Ew9iCVZkZD4=, KVkYX28zG2o=, DzN+dUlTekE=, and state progression.",
            "Because exact body replay is rejected while mixed fresh/template payload+outer combinations can return {do:[]}, next map collector server-side state/time/history transitions and cookie/session lineage around accepted line933.",
            "After strict header-order parity still rejects, prioritize body/session/server-state coupling across ci/cs/cts/p1/payload/pc/sid/uuid/vid, especially how browser accepted state evolves immediately before line933.",
            "Since seq5/seq6 overlap timing is not sufficient, next isolate whether accepted browser line933 depends on a hidden browser-side worker/message state not represented in the two collector request bodies.",
            "Because direct seq5 decoded whole-activity equality plus delivered seq6-pair timing still rejects, next isolate server-side lineage/cookie/session state that changes before accepted browser line933 but is not represented in decoded request bodies.",
            "Use cookie_session_lineage_gap_audit to decide whether no-browser protocol must emulate parent cookie bridge side effects before the accepted seq5/seq6 window, then test a minimal stateful cookie-bridge replay if evidence supports it.",
            "After stk/ns replay alone still rejects, map all non-collector browser/network events between first-failure line574 and success line933, especially captcha HEAD/GET and postMessage-triggered internal dispatches, against no-browser state transitions.",
            "After stk/ns plus captcha.js/iframe/main asset hits still reject and sendBeacon is shown post-success, isolate pre-success collector server-side state or browser/internal material not represented by decoded activities and simple network hits.",
            "Classify pre-success third-frame/browser messages such as crcldu sync against collector state changes; if no network/server-side edge exists, deprioritize them and focus on collector response lineage and hidden request-body binding.",
            "For the latest asset-lineage control, reduce encoded payload/pc/session binding by generating fresh controls that keep payload equal while varying pc/session params, and controls that keep pc equal while varying payload/session params, using one fresh Webshare session per attempt.",
            "Because latest full asset-lineage exact payload+pc returns {do:[]} and exact whole body returns oIIoIooo|-1, test collector/server-side state lineage immediately before line933 rather than replaying static body artifacts again.",
            "Because seq6-response-first timing is now reproduced and still rejected, isolate whether the parent cookie bridge state after seq6 response but before seq5 response has an observable request-body or server-side equivalent.",
            "Because HTTP/2 multiplexing on one TLS session is now reproduced and still rejected, stop treating transport/session multiplexing as the primary blocker; focus on state material produced before line933 or server-side lineage established earlier.",
            "Because seq5 and seq6 decoded request bodies are now both equal to the s00 accepted-window bodies and still reject, focus on server-side/session lineage established before the seq5/seq6 window or hidden material outside decoded request bodies.",
            "Because first-failure history plus full asset-lineage plus h2 seq5/seq6 decoded equality still rejects, stop treating first-failure lineage as the primary missing combined variable; focus on hidden browser material or server-side session binding outside decoded collector bodies.",
            "Because captcha HEAD plus the observed HEAD-to-line933 delay also rejects when combined with first-failure history and h2 decoded equality, stop treating HEAD timing as the primary missing variable.",
            "Because fresh server-bound POW/WASM tail material plus first-failure history, asset lineage, HEAD delay, h2, and seq6-first still rejects, map hidden browser state or server-side session binding not represented by current collector bodies rather than repeating static-template or tail-only controls.",
            "Generate or substitute fresh candidates for the remaining non-tail/timing fields one at a time while using the now-proved offline Ws.Ng/Ws.NQ replay path, then live-probe the same-session PX561 body.",
            "Verify collector decoder returns oIIoIooo|0 for a no-browser fresh PX561 request before claiming HUMAN success replay.",
            "Then replay decoded _px jar into risk/verify + CreateAccount using the existing risk_verify_build exact-body builder and verify redirectUrl without browser.",
        ],
    }
    return result


def write_markdown(result: dict[str, Any], path: Path) -> None:
    lines = [
        "# Pure protocol HUMAN goal gap audit",
        "",
        f"- repo: `{result['repo']}`",
        f"- goalComplete: `{result['summary']['goalComplete']}`",
        "",
        "## Requirement status",
        "",
        "| id | status | requirement |",
        "|---|---|---|",
    ]
    for req in result["requirements"]:
        lines.append(f"| `{req['id']}` | `{req['status']}` | {req['requirement']} |")
    lines += [
        "",
        "## Summary",
        "",
        f"- proved: `{result['summary']['proved']}`",
        f"- partlyProved: `{result['summary']['partlyProved']}`",
        f"- blockingOrMissing: `{result['summary']['blockingOrMissing']}`",
        "",
        "## Next evidence targets",
        "",
        *[f"- {x}" for x in result["nextEvidenceTargets"]],
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    result = build_audit()
    json_path = OUT_DIR / "pure_protocol_goal_gap_audit.json"
    md_path = OUT_DIR / "pure_protocol_goal_gap_audit.md"
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    write_markdown(result, md_path)
    print(json.dumps({"json": str(json_path), "md": str(md_path), "summary": result["summary"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
