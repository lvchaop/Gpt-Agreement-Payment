#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


REPO = Path("/Users/chaopenglv/data/me/Gpt-Agreement-Payment")
OUT_DIR = REPO / "output/protocol_reverse/goal_audit"


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def load_jsonl_events(path: Path, start: int, end: int) -> list[dict[str, Any]]:
    rows = []
    with path.open(encoding="utf-8", errors="replace") as f:
        for line_no, line in enumerate(f, 1):
            if line_no < start or line_no > end:
                continue
            row = json.loads(line)
            if row.get("url") == "https://collector-pxzc5j78di.hsprotect.net/assets/js/bundle":
                row["_line"] = line_no
                rows.append(row)
    return rows


def event_view(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "line": row.get("_line"),
        "kind": row.get("kind"),
        "status": row.get("status"),
        "t": row.get("t"),
        "contentLength": (row.get("headers") or {}).get("content-length"),
        "postLen": row.get("post_len"),
    }


def combo_view(combo: dict[str, Any]) -> dict[str, Any]:
    results = combo.get("results") or {}
    out = {}
    for name in ["seq5", "seq6"]:
        row = results.get(name) or {}
        out[name] = {
            "startedAt": row.get("startedAt"),
            "endedAt": row.get("endedAt"),
            "elapsedSeconds": (row.get("response") or {}).get("elapsedSeconds"),
            "handlers": (row.get("decoded") or {}).get("handlers"),
            "hasSuccessHandler": (row.get("decoded") or {}).get("hasSuccessHandler"),
            "headerMode": ((row.get("material") or {}).get("meta") or {}).get("headerMode"),
        }
    seq5 = out.get("seq5") or {}
    seq6 = out.get("seq6") or {}
    out["derived"] = {
        "seq6StartedAfterSeq5Seconds": (
            seq6.get("startedAt") - seq5.get("startedAt")
            if isinstance(seq5.get("startedAt"), (int, float)) and isinstance(seq6.get("startedAt"), (int, float))
            else None
        ),
        "requestsOverlapped": (
            seq6.get("startedAt") < seq5.get("endedAt")
            if isinstance(seq5.get("endedAt"), (int, float)) and isinstance(seq6.get("startedAt"), (int, float))
            else None
        ),
    }
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit seq5/seq6 timing control against observed s00 successful overlap.")
    parser.add_argument("--s00-runtime", type=Path, default=REPO / "output/outlook_browser/runtime_trace_s00ld1lglrw0_1781191381.jsonl")
    parser.add_argument("--combo", type=Path, default=REPO / "output/protocol_reverse/seq5_seq6_combo_probe/seq5_seq6_combo_probe_f09a7484-6609-11f1-9b9c-62666cc2b93d_1781232843.json")
    parser.add_argument("--out", type=Path, default=OUT_DIR / "seq5_seq6_timing_control_audit.json")
    args = parser.parse_args()

    s00_events = [event_view(row) for row in load_jsonl_events(args.s00_runtime, 920, 965)]
    s00_requests = [row for row in s00_events if row["kind"] == "request"]
    s00_responses = [row for row in s00_events if row["kind"] == "response"]
    combo = load_json(args.combo)
    combo_timing = combo_view(combo)
    s00_gap = None
    s00_overlap = None
    if len(s00_requests) >= 2:
        s00_gap = s00_requests[1]["t"] - s00_requests[0]["t"]
    if len(s00_requests) >= 2 and len(s00_responses) >= 1:
        s00_overlap = s00_requests[1]["t"] < max(row["t"] for row in s00_responses)
    result = {
        "purpose": "Compare observed successful s00 seq5/seq6 request overlap with no-browser parallel timing control.",
        "s00": {
            "runtimeTrace": str(args.s00_runtime),
            "events": s00_events,
            "seq6RequestGapSeconds": s00_gap,
            "requestsOverlappedBeforeFirstResponse": s00_overlap,
        },
        "control": {
            "combo": str(args.combo),
            "mode": combo.get("mode"),
            "gapSeconds": combo.get("gapSeconds"),
            "checks": combo.get("checks"),
            "timing": combo_timing,
        },
        "checks": {
            "s00HasOverlappedSeq5Seq6Requests": s00_overlap is True,
            "controlParallelMode": combo.get("mode") == "parallel",
            "controlRequestsOverlapped": (combo_timing.get("derived") or {}).get("requestsOverlapped") is True,
            "controlGapWithin50msOfS00": (
                abs(((combo_timing.get("derived") or {}).get("seq6StartedAfterSeq5Seconds") or 999) - (s00_gap or 0)) <= 0.05
            ),
            "controlStillRejected": ((combo.get("checks") or {}).get("anySuccessHandler") is False),
        },
        "conclusion": "Observed seq5/seq6 overlap was reproduced as a no-browser parallel timing control; it still rejected if controlStillRejected is true.",
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"json": str(args.out), "checks": result["checks"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
