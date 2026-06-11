#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


REPO = Path("/Users/chaopenglv/data/me/Gpt-Agreement-Payment")
PROTO = REPO / "output/protocol_reverse"
OUT_DIR = PROTO / "collector_decode"


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def decode_path(run: str) -> Path:
    return OUT_DIR / f"collector_decode_{run}.json"


def summarize_decode(run: str, role: str, expected_success_handler: bool) -> dict[str, Any]:
    path = decode_path(run)
    if not path.exists():
        return {
            "run": run,
            "role": role,
            "expectedSuccessHandler": expected_success_handler,
            "decodePath": str(path.resolve()),
            "exists": False,
            "ok": False,
            "error": "missing collector_decode file",
        }
    data = load_json(path)
    entries = data.get("decodedEntries") or []
    success_lines = [e.get("lineNo") for e in entries if e.get("hasSuccessHandler")]
    pow_lines = [e.get("lineNo") for e in entries if e.get("hasPowResult")]
    px3_lines = [e.get("lineNo") for e in entries if e.get("hasPx3")]
    pxde_lines = [e.get("lineNo") for e in entries if e.get("hasPxde")]
    handlers = sorted({h for e in entries for h in (e.get("handlers") or [])})
    has_success = bool(success_lines)
    return {
        "run": run,
        "role": role,
        "expectedSuccessHandler": expected_success_handler,
        "decodePath": str(path.resolve()),
        "tracePath": data.get("tracePath"),
        "exists": True,
        "entryCount": data.get("entryCount"),
        "successLines": success_lines,
        "powLines": pow_lines,
        "px3Lines": px3_lines,
        "pxdeLines": pxde_lines,
        "handlers": handlers,
        "hasSuccessHandler": has_success,
        "ok": has_success == expected_success_handler and bool(entries),
    }


def main() -> int:
    classifier = load_json(PROTO / "trace_classification_v2/human_trace_classifier_v2_summary.json")
    success_runs = [r["run"] for r in classifier["runs"] if r.get("stage") == "full_success_decoded"]
    tf_failure_runs = [r["run"] for r in classifier["runs"] if r.get("stage") == "tf_payload_failure_stage"]
    negative_runs = [r["run"] for r in classifier.get("observationControls", []) if r.get("stage") == "aeax_only_negative_control"]

    rows: list[dict[str, Any]] = []
    for run in success_runs:
        rows.append(summarize_decode(run, "full_success_decoded", True))
    for run in tf_failure_runs:
        rows.append(summarize_decode(run, "tf_payload_failure_stage", False))
    for run in negative_runs:
        rows.append(summarize_decode(run, "aeax_only_negative_control", False))

    result = {
        "purpose": "Validate offline collector response decoder coverage against canonical v2 success/failure/negative-control sample selector.",
        "classifierPath": str((PROTO / "trace_classification_v2/human_trace_classifier_v2_summary.json").resolve()),
        "decoderScript": str((REPO / "tools/decode_human_collector_response.mjs").resolve()),
        "checks": {
            "allDecodeFilesExist": all(r.get("exists") for r in rows),
            "allRowsMatchExpectedSuccessHandler": all(r.get("ok") for r in rows),
            "fullSuccessRuns": success_runs,
            "tfFailureRuns": tf_failure_runs,
            "aeaxOnlyNegativeControls": negative_runs,
        },
        "rows": rows,
        "conclusion": (
            "The offline collector response decoder distinguishes the accepted success sample from tf failure and "
            "AEAx-only negative controls by decoded oIIoIooo success handler presence. Cookie and POW handlers are "
            "not sufficient for HUMAN acceptance because they also appear in non-accepted controls."
        ),
        "limitation": (
            "This audits hsprotect.main.fp.enter runtime-hook material captured from local traces. It validates the "
            "offline response decoder and sample classification, not a live pure-protocol collector replay."
        ),
    }

    out_json = OUT_DIR / "collector_decoder_coverage_audit.json"
    out_md = OUT_DIR / "collector_decoder_coverage_audit.md"
    out_json.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "# Collector decoder coverage audit",
        "",
        f"- classifier: `{result['classifierPath']}`",
        f"- decoder: `{result['decoderScript']}`",
        "",
        "## Checks",
        "",
        f"- allDecodeFilesExist: `{result['checks']['allDecodeFilesExist']}`",
        f"- allRowsMatchExpectedSuccessHandler: `{result['checks']['allRowsMatchExpectedSuccessHandler']}`",
        "",
        "## Rows",
        "",
        "| run | role | entries | success lines | POW lines | px3 | pxde | ok |",
        "|---|---|---:|---|---|---:|---:|---:|",
    ]
    for row in rows:
        lines.append(
            "| {run} | {role} | {entries} | {success} | {pow} | {px3} | {pxde} | {ok} |".format(
                run=row["run"],
                role=row["role"],
                entries=row.get("entryCount"),
                success=",".join(str(x) for x in row.get("successLines") or []) or "-",
                pow=",".join(str(x) for x in row.get("powLines") or []) or "-",
                px3=len(row.get("px3Lines") or []),
                pxde=len(row.get("pxdeLines") or []),
                ok=row.get("ok"),
            )
        )
    lines += [
        "",
        "## Conclusion",
        "",
        result["conclusion"],
        "",
        "## Limitation",
        "",
        result["limitation"],
        "",
    ]
    out_md.write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"json": str(out_json), "md": str(out_md), "checks": result["checks"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
