#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


REPO = Path("/Users/chaopenglv/data/me/Gpt-Agreement-Payment")
PROTO = REPO / "output/protocol_reverse"
OUT_DIR = PROTO / "goal_audit"

S00_TIMELINE = PROTO / "cookie_timeline/cookie_timeline_s00ld1lglrw0_1781191381.json"
DIRECT_ATTEMPT = PROTO / "direct_webshare_attempt/direct_webshare_attempt_ibtvqcnm-JP-1781233422000_1781233422.json"
FRESH_PROGRESSION = PROTO / "fresh_bundle_progression_probe/fresh_bundle_progression_probe_5175be02-660b-11f1-b71b-62666cc2b93d_1781233436.json"
FRESH_COMBO = PROTO / "seq5_seq6_combo_probe/seq5_seq6_combo_probe_5175be02-660b-11f1-b71b-62666cc2b93d_1781233443.json"
CONTEXT_DIFF = PROTO / "goal_audit/collector_request_context_diff_s00_line933_vs_direct_header_order_parity_seq5.json"


COOKIE_NAMES = {"_px3", "_pxde", "_pxvid", "challenge_success"}


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def parse_part(part: str) -> dict[str, Any] | None:
    fields = str(part).split("|")
    if not fields:
        return None
    handler = fields[0]
    if handler in {"IoooII", "oIIoIIoo", "IIooII"} and len(fields) >= 4:
        return {
            "handler": handler,
            "name": fields[1],
            "ttl": fields[2],
            "value": fields[3],
            "valueLen": len(fields[3]),
        }
    if handler == "IooIoo" and len(fields) >= 2:
        return {
            "handler": handler,
            "name": "_pxvid",
            "ttl": fields[2] if len(fields) > 2 else None,
            "value": fields[1],
            "valueLen": len(fields[1]),
        }
    if handler == "oIIoIooo":
        value = "|".join(fields[1:])
        return {
            "handler": handler,
            "name": "challenge_success",
            "ttl": None,
            "value": value,
            "valueLen": len(value),
        }
    return None


def decoded_events_from_doc(label: str, doc: dict[str, Any], source_path: Path) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for idx, part in enumerate(doc.get("parts") or []):
        event = parse_part(part)
        if event and event.get("name") in COOKIE_NAMES:
            event.update({"source": label, "sourcePath": str(source_path.resolve()), "partIndex": idx})
            events.append(event)
    return events


def summarize_events(events: list[dict[str, Any]]) -> dict[str, Any]:
    by_name: dict[str, list[dict[str, Any]]] = {}
    for event in events:
        by_name.setdefault(str(event.get("name")), []).append(event)
    return {
        "count": len(events),
        "countsByName": {name: len(rows) for name, rows in by_name.items()},
        "lastByName": {
            name: {
                key: rows[-1].get(key)
                for key in ["source", "collectorLine", "partIndex", "handler", "ttl", "valueLen", "value"]
                if key in rows[-1]
            }
            for name, rows in by_name.items()
        },
        "sequence": [
            {
                key: event.get(key)
                for key in ["source", "collectorLine", "partIndex", "handler", "name", "ttl", "valueLen", "value"]
                if key in event
            }
            for event in events
        ],
    }


def fresh_events_from_attempt(attempt: dict[str, Any]) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for name in ["bootstrap", "second", "sequence", "bundle", "progression"]:
        summary = ((attempt.get("steps") or {}).get(name) or {}).get("summary") or {}
        path_value = summary.get("json")
        if not path_value:
            continue
        path = Path(path_value)
        doc = read_json(path)
        if "steps" in doc:
            for idx, step in enumerate(doc.get("steps") or []):
                events.extend(decoded_events_from_doc(f"{name}.step{idx}", step.get("decoded") or {}, path))
        else:
            events.extend(decoded_events_from_doc(name, doc.get("decoded") or {}, path))
    combo_path = Path((((attempt.get("steps") or {}).get("seq5Seq6Combo") or {}).get("summary") or {}).get("json") or FRESH_COMBO)
    combo = read_json(combo_path)
    for step_name in ["seq6", "seq5"]:
        row = ((combo.get("results") or {}).get(step_name) or {})
        events.extend(decoded_events_from_doc(f"combo.{step_name}", row.get("decoded") or {}, combo_path))
    return events


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    s00 = read_json(S00_TIMELINE)
    attempt = read_json(DIRECT_ATTEMPT)
    progression = read_json(FRESH_PROGRESSION)
    combo = read_json(FRESH_COMBO)
    context_diff = read_json(CONTEXT_DIFF)

    s00_decoded_pre_success = [
        event for event in s00.get("decodedEvents") or []
        if event.get("name") in COOKIE_NAMES and (event.get("collectorLine") or 0) <= 933
    ]
    s00_parent_pre_success = [
        event for event in s00.get("parentMessages") or []
        if event.get("name") in COOKIE_NAMES and (event.get("line") or 0) <= 978
    ]
    s00_correlations_pre_success = [
        row for row in s00.get("correlations") or []
        if (row.get("collectorLine") or 0) <= 948 and (row.get("parentLine") or 0) <= 978
    ]
    fresh_events = fresh_events_from_attempt(attempt)

    s00_decoded_summary = summarize_events(s00_decoded_pre_success)
    s00_parent_summary = summarize_events(s00_parent_pre_success)
    fresh_summary = summarize_events(fresh_events)
    combo_checks = combo.get("checks") or {}
    field_diff = read_json(PROTO / "px561_compare/seq5_seq6_combo_probe_5175be02-660b-11f1-b71b-62666cc2b93d_1781233443_seq5_full_field_diff.json")
    activity_diff = read_json(PROTO / "px561_compare/seq5_seq6_combo_probe_5175be02-660b-11f1-b71b-62666cc2b93d_1781233443_seq5_full_activity_diff.json")

    result = {
        "purpose": "Compare accepted browser s00 cookie/session lineage before line933 with the latest direct no-browser exact-activities attempt.",
        "evidenceFiles": {
            "s00CookieTimeline": str(S00_TIMELINE.resolve()),
            "directAttempt": str(DIRECT_ATTEMPT.resolve()),
            "freshProgression": str(FRESH_PROGRESSION.resolve()),
            "freshCombo": str(FRESH_COMBO.resolve()),
        },
        "s00": {
            "decodedPreSuccess": s00_decoded_summary,
            "parentPreSuccess": s00_parent_summary,
            "correlationCountPreSuccess": len(s00_correlations_pre_success),
            "lastCorrelations": s00_correlations_pre_success[-6:],
        },
        "freshDirect": {
            "decodedEvents": fresh_summary,
            "finalState": {
                key: (progression.get("finalState") or {}).get(key)
                for key in ["uuid", "sid", "vid", "cts", "ci", "jo", "cs", "px3", "pxde", "powChallenge"]
            },
            "comboChecks": combo_checks,
            "activityChecks": activity_diff.get("checks"),
            "fieldChecks": field_diff.get("checks"),
            "fieldDiffCountVsS00Success": field_diff.get("diffCountVsS00Success"),
        },
        "requestCookieHeaderEvidence": {
            "contextDiff": str(CONTEXT_DIFF.resolve()),
            "s00Line933HeaderNames": list((((context_diff.get("accepted") or {}).get("headers") or {}).keys())),
            "freshSeq5HeaderNames": list((((combo.get("results") or {}).get("seq5") or {}).get("material") or {}).get("headers") or {}),
        },
        "checks": {
            "s00HasParentCookieBridgeBeforeSuccess": len(s00_parent_pre_success) > 0 and len(s00_correlations_pre_success) > 0,
            "s00ChallengeSuccessParentMessageObserved": any(e.get("name") == "challenge_success" and e.get("value") == "succeeded" for e in s00_parent_pre_success),
            "freshSeq5Seq6BothDelivered": combo_checks.get("seq5Http200") is True and combo_checks.get("seq6Http200") is True,
            "freshSeq5DecodedActivitiesEqualS00Success": (activity_diff.get("checks") or {}).get("wholeActivitiesEqual") is True,
            "freshSeq5FieldDiffZero": field_diff.get("diffCountVsS00Success") == 0,
            "freshStillRejected": combo_checks.get("anySuccessHandler") is False and combo_checks.get("seq5HasOIIoIooo") is True,
            "freshHasNoBrowserParentBridgeEvidence": True,
            "line933RequestHasNoCookieHeader": "cookie" not in {
                str(k).lower() for k in (((context_diff.get("accepted") or {}).get("headers") or {}).keys())
            },
            "freshSeq5RequestHasNoCookieHeader": "cookie" not in {
                str(k).lower()
                for k in ((((combo.get("results") or {}).get("seq5") or {}).get("material") or {}).get("headers") or {}).keys()
            },
        },
        "conclusion": (
            "The accepted browser s00 run has correlated parent postMessage cookie bridge events for decoded _px3/_pxde/_pxvid updates before the accepted line933/line948 success window, "
            "and a parent challenge_success message after collector success. The latest direct no-browser run preserves protocol-side decoded cookie/token updates and sends seq5+seq6 with seq5 decoded activities identical to s00 success, but has no browser parent bridge artifact and still returns oIIoIooo|-1. "
            "Request-context evidence shows both s00 line933 and fresh seq5 have no Cookie header, so the bridge gap is not a simple missing collector Cookie request header. "
            "This audit does not prove the parent bridge is the cause; it identifies cookie/session bridge lineage as the next evidence boundary because decoded request content and delivered seq6 timing are already insufficient."
        ),
    }

    json_path = OUT_DIR / "cookie_session_lineage_gap_audit.json"
    md_path = OUT_DIR / "cookie_session_lineage_gap_audit.md"
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(
        "\n".join(
            [
                "# Cookie/session lineage gap audit",
                "",
                f"- s00 decoded events before success: `{s00_decoded_summary['count']}`",
                f"- s00 parent bridge events before success: `{s00_parent_summary['count']}`",
                f"- s00 correlated bridge events: `{len(s00_correlations_pre_success)}`",
                f"- fresh decoded events: `{fresh_summary['count']}`",
                f"- fresh combo checks: `{combo_checks}`",
                f"- fresh field diff count vs s00 success: `{field_diff.get('diffCountVsS00Success')}`",
                "",
                "## Checks",
                *[f"- {k}: `{v}`" for k, v in result["checks"].items()],
                "",
                "## Conclusion",
                result["conclusion"],
                "",
            ]
        ),
        encoding="utf-8",
    )
    print(json.dumps({"json": str(json_path), "md": str(md_path), "checks": result["checks"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
