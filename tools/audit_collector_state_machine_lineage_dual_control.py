#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


REPO = Path("/Users/chaopenglv/data/me/Gpt-Agreement-Payment")
PROTO = REPO / "output/protocol_reverse"
OUT = PROTO / "goal_audit/collector_state_machine_lineage_dual_control_audit.json"

S00_DECODE = PROTO / "collector_decode/collector_decode_s00ld1lglrw0_1781191381.json"
DIRECT = PROTO / "direct_webshare_attempt/direct_webshare_attempt_ibtvqcnm-JP-1781237267000_1781237267.json"
COMBO = PROTO / "seq5_seq6_combo_probe/seq5_seq6_combo_probe_453388c8-6614-11f1-a43c-62666cc2b93d_1781237289.json"
H2_AUDIT = PROTO / "goal_audit/h2_dual_activity_equal_control_audit.json"
FIRST_FAILURE_AUDIT = PROTO / "goal_audit/fresh_first_failure_history_audit.json"
WHOLE_ACTIVITIES_AUDIT = PROTO / "goal_audit/clean_history_exact_whole_activities_audit.json"


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def s00_rows(doc: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for entry in doc.get("decodedEntries") or []:
        rows.append(
            {
                "label": f"s00.line{entry.get('lineNo')}",
                "lineNo": entry.get("lineNo"),
                "handlers": entry.get("handlers") or [],
                "hasPowResult": entry.get("hasPowResult") is True,
                "hasSuccessHandler": entry.get("hasSuccessHandler") is True,
                "successParts": [
                    part for part in entry.get("parts") or []
                    if str(part).startswith("oIIoIooo")
                ],
            }
        )
    return rows


def direct_rows(direct: dict[str, Any], combo: dict[str, Any]) -> list[dict[str, Any]]:
    steps = direct.get("steps") or {}
    rows: list[dict[str, Any]] = []

    def add(label: str, handlers: list[str] | None, has_pow: bool | None = None, success_parts: list[str] | None = None) -> None:
        rows.append(
            {
                "label": label,
                "handlers": handlers or [],
                "hasPowResult": bool(has_pow),
                "hasSuccessHandler": any(str(part).startswith("oIIoIooo|0") for part in success_parts or []),
                "successParts": success_parts or [],
            }
        )

    add(
        "direct.bootstrap",
        ((steps.get("bootstrap") or {}).get("summary") or {}).get("handlers"),
    )
    add(
        "direct.second",
        ((steps.get("second") or {}).get("summary") or {}).get("handlers"),
    )
    for idx, handlers in enumerate(((steps.get("sequence") or {}).get("summary") or {}).get("handlers") or []):
        add(f"direct.sequence[{idx}]", handlers)
    add(
        "direct.bundle",
        ((steps.get("bundle") or {}).get("summary") or {}).get("handlers"),
        ((steps.get("bundle") or {}).get("summary") or {}).get("hasPowResult"),
    )
    for idx, handlers in enumerate(((steps.get("progression") or {}).get("summary") or {}).get("handlers") or []):
        has_pow_list = ((steps.get("progression") or {}).get("summary") or {}).get("hasPow") or []
        add(f"direct.progression[{idx}]", handlers, has_pow_list[idx] if idx < len(has_pow_list) else None)

    for name in ["seq6", "seq5"]:
        decoded = (((combo.get("results") or {}).get(name) or {}).get("decoded") or {})
        add(
            f"combo.{name}",
            decoded.get("handlers"),
            decoded.get("hasPowResult"),
            [
                part for part in decoded.get("parts") or []
                if str(part).startswith("oIIoIooo")
            ],
        )

    return rows


def compare_by_position(expected: list[dict[str, Any]], actual: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for idx in range(max(len(expected), len(actual))):
        exp = expected[idx] if idx < len(expected) else None
        got = actual[idx] if idx < len(actual) else None
        out.append(
            {
                "index": idx,
                "expectedLabel": exp.get("label") if exp else None,
                "actualLabel": got.get("label") if got else None,
                "expectedHandlers": exp.get("handlers") if exp else None,
                "actualHandlers": got.get("handlers") if got else None,
                "handlersEqual": (exp or {}).get("handlers") == (got or {}).get("handlers"),
                "expectedSuccessParts": exp.get("successParts") if exp else None,
                "actualSuccessParts": got.get("successParts") if got else None,
            }
        )
    return out


def main() -> int:
    s00 = read_json(S00_DECODE)
    direct = read_json(DIRECT)
    combo = read_json(COMBO)
    h2 = read_json(H2_AUDIT)
    first_failure = read_json(FIRST_FAILURE_AUDIT)
    whole_activities = read_json(WHOLE_ACTIVITIES_AUDIT)

    expected = s00_rows(s00)
    actual = direct_rows(direct, combo)
    expected_labels = [row["label"] for row in expected]
    actual_labels = [row["label"] for row in actual]
    comparison = compare_by_position(expected, actual)

    line592 = next((row for row in expected if row.get("lineNo") == 592), None)
    direct_has_failure_before_second_pow = any(
        row["successParts"] == ["oIIoIooo|-1"]
        for row in actual[:8]
    )

    audit = {
        "purpose": "Compare s00 accepted collector response state-machine lineage with the latest h2 dual-activity no-browser control before drawing a next boundary.",
        "inputs": {
            "s00Decode": str(S00_DECODE),
            "direct": str(DIRECT),
            "combo": str(COMBO),
            "h2DualActivityAudit": str(H2_AUDIT),
            "firstFailureHistoryAudit": str(FIRST_FAILURE_AUDIT),
            "cleanHistoryExactWholeActivitiesAudit": str(WHOLE_ACTIVITIES_AUDIT),
        },
        "expectedS00": expected,
        "latestDirect": actual,
        "positionComparison": comparison,
        "checks": {
            "h2DualControlStillRejected": (h2.get("checks") or {}).get("stillRejected") is True,
            "h2DualSeq5ActivitiesEqual": (h2.get("checks") or {}).get("seq5WholeActivitiesEqualS00Line922") is True,
            "h2DualSeq6ActivityEqual": (h2.get("checks") or {}).get("seq6WholeActivityEqualS00Line925") is True,
            "s00HasLine592FirstFailureResponse": line592 is not None and line592.get("successParts") == ["oIIoIooo|-1"],
            "latestDualSkippedLine592EquivalentBeforeSecondPow": direct_has_failure_before_second_pow is False,
            "priorCleanHistoryFirstFailureTested": all((first_failure.get("checks") or {}).values()),
            "priorCleanHistoryWholeActivitiesEqualStillRejected": all((whole_activities.get("checks") or {}).values()),
            "latestDirectResponseHandlerSequenceExactlyMatchesS00": all(row["handlersEqual"] for row in comparison),
        },
        "boundary": {
            "latestH2DualControl": "Full asset-lineage + same Webshare session + h2 stream 1/3 + seq6 first + seq5/seq6 decoded activity equality, but no line592-equivalent rejected PX561 before the second POW lineage.",
            "priorCleanHistoryControl": "Line566/line592-equivalent first failure and exact line922 decoded activities were tested in a clean no-browser history, but not in the latest full asset-lineage h2 dual-activity control.",
        },
        "conclusion": (
            "The latest strongest h2 dual-activity control does not reproduce the s00 line592 first rejected PX561 response before the line623 second POW path. "
            "Separate clean-history audits prove that adding that first-failure history and exact line922 decoded activities is still insufficient by itself. "
            "The untested combined boundary is therefore first-failure history + full asset-lineage + h2 seq5/seq6 dual-activity equality in one fresh Webshare session."
        ),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"json": str(OUT), "checks": audit["checks"], "conclusion": audit["conclusion"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
