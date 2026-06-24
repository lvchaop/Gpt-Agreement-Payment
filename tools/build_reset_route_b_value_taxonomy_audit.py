#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
RESET = ROOT / "output/protocol_reverse/reset_plan"
MATRIX = RESET / "reset_route_b_resampling_matrix.json"
PLAN = ROOT / "docs/pure-protocol-human-methodological-execution-plan.md"
OUT = RESET / "reset_route_b_value_taxonomy_audit.json"

ROUTE_B_HOOK_KINDS = {
    "webkit.messageHandlers.pxMobileData.wrap",
    "webkit.messageHandlers.pxMobileData.postMessage",
    "OfflineAudioContext.wrap",
    "OfflineAudioContext.new",
    "OfflineAudioContext.startRendering",
    "OfflineAudioContext.startRendering.resolved",
    "serviceWorker.snapshot",
    "serviceWorker.register",
    "caches.wrap",
    "caches.open",
    "caches.match",
}

LINEAGE_KINDS = {
    "document.cookie.set",
    "window.message.recv",
    "hsprotect.main.jl.item",
    "hsprotect.main.jl.queue",
    "hsprotect.main.jl.dispatch",
    "hsprotect.main.tf.payload",
    "hsprotect.sendBeacon.internal",
    "fetch.call",
    "xhr.send",
    "sendBeacon.call",
}

ENVIRONMENT_ONLY_KINDS = {
    "performance.snapshot",
    "crypto.snapshot",
    "performance.now.call",
    "addEventListener",
    "dispatchEvent",
    "hook_installed",
    "hook_error",
}

HSPROTECT_PREFIX = "hsprotect."


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, doc: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")


def sha256_text(value: Any) -> str:
    text = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def short_value(value: Any, limit: int = 180) -> Any:
    if isinstance(value, str):
        return value if len(value) <= limit else value[:limit] + f"...<len={len(value)}>"
    if isinstance(value, list):
        return [short_value(v, limit) for v in value[:8]] + ([f"...<len={len(value)}>"] if len(value) > 8 else [])
    if isinstance(value, dict):
        return {k: short_value(v, limit) for k, v in list(value.items())[:16]}
    return value


def parse_cookie_name(raw: str) -> str:
    return raw.split("=", 1)[0].strip() if isinstance(raw, str) and "=" in raw else ""


def normalize_message_data(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, str):
        return {"kind": type(raw).__name__, "len": None, "sha256": sha256_text(raw)}
    if raw == "":
        return {"kind": "empty", "len": 0}
    if raw.startswith("dfp:"):
        return {"kind": raw, "len": len(raw)}
    try:
        obj = json.loads(raw)
    except Exception:
        return {"kind": "string", "len": len(raw), "sha256": hashlib.sha256(raw.encode()).hexdigest()}
    if isinstance(obj, dict):
        out = {"kind": "json_object", "keys": sorted(obj.keys()), "sha256": sha256_text(obj)}
        if obj.get("type") == "cookie":
            out.update({"messageType": "cookie", "cookieName": obj.get("name"), "valueLen": len(str(obj.get("value") or ""))})
        return out
    return {"kind": "json", "sha256": sha256_text(obj)}


def normalize_args(args: Any) -> list[dict[str, Any]]:
    out = []
    if not isinstance(args, list):
        return out
    for arg in args:
        item: dict[str, Any] = {"type": type(arg).__name__}
        if isinstance(arg, str):
            item["len"] = len(arg)
            item["sha256"] = hashlib.sha256(arg.encode()).hexdigest()
            if arg in {"_px3", "_pxde", "_pxvid", "score", "cu", "cc", "fed"}:
                item["literal"] = arg
            elif len(arg) <= 40:
                item["value"] = arg
            elif ":" in arg:
                item["colonParts"] = len(arg.split(":"))
        else:
            item["sha256"] = sha256_text(arg)
            if isinstance(arg, (int, float, bool)) or arg is None:
                item["value"] = arg
        out.append(item)
    return out


def summarize_tf_payload(data: dict[str, Any]) -> dict[str, Any]:
    acts = data.get("activities") if isinstance(data, dict) else None
    if not isinstance(acts, list):
        return {"activityCount": None, "sha256": sha256_text(data)}
    first_types = []
    key_counts = []
    for act in acts[:8]:
        if isinstance(act, dict):
            first_types.append(act.get("t"))
            d = act.get("d")
            key_counts.append(len(d) if isinstance(d, dict) else None)
    return {
        "activityCount": len(acts),
        "firstTypes": first_types,
        "activityKeyCounts": key_counts,
        "sha256": sha256_text(data),
    }


def load_events(path: Path) -> list[dict[str, Any]]:
    rows = []
    with path.open(encoding="utf-8") as fh:
        for line_no, line in enumerate(fh, 1):
            if not line.strip():
                continue
            obj = json.loads(line)
            obj["_line"] = line_no
            rows.append(obj)
    return rows


def summarize_trace(path: Path) -> dict[str, Any]:
    rows = load_events(path)
    kind_counts = Counter(str(row.get("kind")) for row in rows)
    origin_counts = Counter(str(row.get("origin")) for row in rows)
    first_line: dict[str, int] = {}
    first_perf: dict[str, Any] = {}
    for row in rows:
        kind = str(row.get("kind"))
        first_line.setdefault(kind, row["_line"])
        first_perf.setdefault(kind, row.get("perf_t"))

    route_b_values: dict[str, Any] = defaultdict(list)
    message_patterns = Counter()
    cookie_sets = Counter()
    handler_keys = Counter()
    handler_key_arg_shapes = defaultdict(Counter)
    tf_payloads = []
    beacon_targets = Counter()
    candidate_lineage_events = []

    for row in rows:
        kind = str(row.get("kind"))
        data = row.get("data") if isinstance(row.get("data"), dict) else {}
        if kind in ROUTE_B_HOOK_KINDS:
            summary = {
                "line": row["_line"],
                "origin": row.get("origin"),
                "hrefHash": hashlib.sha256(str(row.get("href") or "").encode()).hexdigest(),
                "dataKeys": sorted(data.keys()),
                "dataHash": sha256_text(data),
            }
            if kind == "serviceWorker.snapshot":
                summary["controller"] = data.get("controller")
                summary["readyType"] = data.get("readyType")
            route_b_values[kind].append(summary)

        if kind == "window.message.recv":
            norm = normalize_message_data(data.get("data"))
            message_patterns[json.dumps(norm, sort_keys=True, ensure_ascii=False)] += 1
            candidate_lineage_events.append({"line": row["_line"], "kind": kind, "origin": row.get("origin"), "summary": norm})

        if kind == "document.cookie.set":
            raw = str(data.get("value") or "")
            name = parse_cookie_name(raw)
            cookie_sets[name] += 1
            candidate_lineage_events.append(
                {"line": row["_line"], "kind": kind, "origin": row.get("origin"), "summary": {"cookieName": name, "valueLen": len(raw), "sha256": hashlib.sha256(raw.encode()).hexdigest()}}
            )

        if kind in {"hsprotect.main.jl.item", "hsprotect.main.jl.dispatch"}:
            key = str(data.get("handlerKey") or "")
            handler_keys[key] += 1
            handler_key_arg_shapes[key][json.dumps(normalize_args(data.get("args")), sort_keys=True, ensure_ascii=False)] += 1
            candidate_lineage_events.append(
                {"line": row["_line"], "kind": kind, "origin": row.get("origin"), "summary": {"handlerKey": key, "args": normalize_args(data.get("args"))}}
            )

        if kind == "hsprotect.main.jl.queue":
            queue = data.get("queue")
            keys = [str(item.get("key")) for item in queue if isinstance(item, dict)] if isinstance(queue, list) else []
            candidate_lineage_events.append({"line": row["_line"], "kind": kind, "origin": row.get("origin"), "summary": {"queueLen": len(keys), "keys": keys}})

        if kind == "hsprotect.main.tf.payload":
            summary = summarize_tf_payload(data)
            tf_payloads.append({"line": row["_line"], **summary})
            candidate_lineage_events.append({"line": row["_line"], "kind": kind, "origin": row.get("origin"), "summary": summary})

        if kind == "hsprotect.sendBeacon.internal":
            url = str(data.get("url") or "")
            beacon_targets[url] += 1
            candidate_lineage_events.append(
                {"line": row["_line"], "kind": kind, "origin": row.get("origin"), "summary": {"url": url, "blobSize": data.get("blobSize"), "blobType": data.get("blobType")}}
            )

    return {
        "path": str(path),
        "exists": path.exists(),
        "eventCount": len(rows),
        "kindCounts": dict(kind_counts),
        "originCounts": dict(origin_counts),
        "firstLineByKind": first_line,
        "firstPerfByKind": first_perf,
        "routeBHookValueSummaries": {k: v[:12] for k, v in route_b_values.items()},
        "messagePatterns": {k: v for k, v in message_patterns.items()},
        "cookieSetCounts": dict(cookie_sets),
        "handlerKeyCounts": dict(handler_keys),
        "handlerKeyArgShapes": {k: dict(v) for k, v in handler_key_arg_shapes.items()},
        "tfPayloadSummaries": tf_payloads[:24],
        "beaconTargets": dict(beacon_targets),
        "candidateLineageEventsSample": candidate_lineage_events[:80],
    }


def real_rows(matrix: dict[str, Any]) -> list[dict[str, Any]]:
    return [row for row in matrix.get("executedRows") or [] if row.get("attemptSummary") and row.get("artifacts")]


def first_js_trace(row: dict[str, Any]) -> Path | None:
    traces = ((row.get("artifacts") or {}).get("jsInternalTrace") or [])
    if not traces:
        return None
    return Path(traces[0])


def diff_counter(success: dict[str, int], failure: dict[str, int]) -> dict[str, Any]:
    s = Counter(success)
    f = Counter(failure)
    return {
        "successOnly": sorted(s.keys() - f.keys()),
        "failureOnly": sorted(f.keys() - s.keys()),
        "both": sorted(s.keys() & f.keys()),
        "changedCounts": {k: {"success": s[k], "failure": f[k]} for k in sorted((s.keys() & f.keys())) if s[k] != f[k]},
    }


def build() -> dict[str, Any]:
    matrix = read_json(MATRIX)
    rows = real_rows(matrix)
    success_rows = [row for row in rows if ((row.get("classification") or {}).get("successLike") is True)]
    failure_rows = [row for row in rows if ((row.get("classification") or {}).get("successLike") is not True)]
    success_row = success_rows[0] if success_rows else {}
    failure_row = failure_rows[0] if failure_rows else {}
    success_trace = first_js_trace(success_row) if success_row else None
    failure_trace = first_js_trace(failure_row) if failure_row else None

    success = summarize_trace(success_trace) if success_trace and success_trace.exists() else {}
    failure = summarize_trace(failure_trace) if failure_trace and failure_trace.exists() else {}

    kind_diff = diff_counter(success.get("kindCounts") or {}, failure.get("kindCounts") or {})
    cookie_diff = diff_counter(success.get("cookieSetCounts") or {}, failure.get("cookieSetCounts") or {})
    handler_diff = diff_counter(success.get("handlerKeyCounts") or {}, failure.get("handlerKeyCounts") or {})
    beacon_diff = diff_counter(success.get("beaconTargets") or {}, failure.get("beaconTargets") or {})

    success_only_kinds = set(kind_diff["successOnly"])
    success_only_lineage = sorted(success_only_kinds & LINEAGE_KINDS)
    success_only_hsprotect = sorted(k for k in success_only_kinds if k.startswith(HSPROTECT_PREFIX))
    success_only_environment = sorted(success_only_kinds & ENVIRONMENT_ONLY_KINDS)
    route_b_success_value_keys = set((success.get("routeBHookValueSummaries") or {}).keys())
    route_b_failure_value_keys = set((failure.get("routeBHookValueSummaries") or {}).keys())

    attempt_env = {
        "success": {
            "sessionId": success_row.get("sessionId"),
            "sampleClass": success_row.get("sampleClass"),
            "stage": (success_row.get("classification") or {}).get("stage"),
            "envPatchApply": ((read_json(Path(success_row.get("attemptSummary"))) if success_row.get("attemptSummary") else {}).get("envOverlay") or {}).get("OUTLOOK_HSPROTECT_JS_PATCH_APPLY"),
            "jsTrace": str(success_trace) if success_trace else None,
        },
        "failure": {
            "sessionId": failure_row.get("sessionId"),
            "sampleClass": failure_row.get("sampleClass"),
            "stage": (failure_row.get("classification") or {}).get("stage"),
            "envPatchApply": ((read_json(Path(failure_row.get("attemptSummary"))) if failure_row.get("attemptSummary") else {}).get("envOverlay") or {}).get("OUTLOOK_HSPROTECT_JS_PATCH_APPLY"),
            "jsTrace": str(failure_trace) if failure_trace else None,
        },
    }

    instrumentation_controlled = attempt_env["success"]["envPatchApply"] == attempt_env["failure"]["envPatchApply"]

    promoted = []
    for key in success_only_lineage:
        promoted.append(
            {
                "kind": key,
                "promoteToSingleTransitionCandidate": False,
                "reason": (
                    "Success-only lineage event is observed only in browser JS trace, but this contrast is confounded by OUTLOOK_HSPROTECT_JS_PATCH_APPLY "
                    "differing between success and failure samples; current audit has no evidence that its value is constructible without browser/captcha lifecycle, "
                    "and no negative-control proves replacing a pure-protocol field with this value changes seq5 from oIIoIooo|-1 to success."
                ),
            }
        )

    checks = {
        "planExists": PLAN.exists(),
        "matrixExists": MATRIX.exists(),
        "realAttemptCount": len(rows),
        "successSampleCount": len(success_rows),
        "failureSampleCount": len(failure_rows),
        "successTraceExists": bool(success_trace and success_trace.exists()),
        "failureTraceExists": bool(failure_trace and failure_trace.exists()),
        "successEventCount": success.get("eventCount"),
        "failureEventCount": failure.get("eventCount"),
        "successOnlyKindCount": len(kind_diff["successOnly"]),
        "failureOnlyKindCount": len(kind_diff["failureOnly"]),
        "successOnlyLineageKindCount": len(success_only_lineage),
        "successOnlyHsprotectKindCount": len(success_only_hsprotect),
        "successOnlyEnvironmentKindCount": len(success_only_environment),
        "routeBHookKindsBothObserved": sorted(route_b_success_value_keys & route_b_failure_value_keys),
        "routeBHookValueComparedKindCount": len(route_b_success_value_keys & route_b_failure_value_keys),
        "routeBHookSuccessOnlyValueKindCount": len(route_b_success_value_keys - route_b_failure_value_keys),
        "routeBHookFailureOnlyValueKindCount": len(route_b_failure_value_keys - route_b_success_value_keys),
        "cookieNameSuccessOnlyCount": len(cookie_diff["successOnly"]),
        "handlerKeySuccessOnlyCount": len(handler_diff["successOnly"]),
        "beaconTargetSuccessOnlyCount": len(beacon_diff["successOnly"]),
        "instrumentationPatchApplyDiffersBetweenSamples": not instrumentation_controlled,
        "hsprotectValueContrastControlled": instrumentation_controlled,
        "promotedSingleTransitionCandidateCount": 0,
        "readyForFreshExperiment": False,
        "goalComplete": False,
    }

    return {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "plan": str(PLAN),
        "purpose": "Compare value-level and sequence-level JS trace taxonomy for the new Route B browser success/failure samples.",
        "inputs": {
            "routeBResamplingMatrix": str(MATRIX),
            "successTrace": str(success_trace) if success_trace else None,
            "failureTrace": str(failure_trace) if failure_trace else None,
        },
        "attemptEnvironment": attempt_env,
        "checks": checks,
        "diffs": {
            "kindDiff": kind_diff,
            "cookieNameDiff": cookie_diff,
            "handlerKeyDiff": handler_diff,
            "beaconTargetDiff": beacon_diff,
            "successOnlyLineageKinds": success_only_lineage,
            "successOnlyHsprotectKinds": success_only_hsprotect,
        },
        "traceSummaries": {
            "success": success,
            "failure": failure,
        },
        "promotedCandidates": promoted,
        "decision": {
            "goalComplete": False,
            "readyForFreshExperiment": False,
            "recommendedExperiment": None,
            "nextArtifact": None,
            "nextScript": None,
            "reason": (
                "Value taxonomy finds browser-success-only hsprotect lineage and captcha/WASM events, but that contrast is not instrumentation-controlled because "
                "OUTLOOK_HSPROTECT_JS_PATCH_APPLY differs between samples. The Route B hook values observed on both sides remain lifecycle/environment snapshots; "
                "no pure-protocol constructible single transition is promoted."
            ),
        },
    }


def main() -> int:
    doc = build()
    write_json(OUT, doc)
    print(json.dumps({"json": str(OUT), "checks": doc["checks"], "diffs": doc["diffs"], "decision": doc["decision"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
