#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import urllib.parse
from pathlib import Path
from typing import Any


REPO = Path("/Users/chaopenglv/data/me/Gpt-Agreement-Payment")
OUT_DIR = REPO / "output/protocol_reverse/goal_audit"


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def load_jsonl_line(path: Path, line_no: int) -> dict[str, Any]:
    with path.open(encoding="utf-8", errors="replace") as f:
        for idx, line in enumerate(f, 1):
            if idx == line_no:
                return json.loads(line)
    raise ValueError(f"line {line_no} not found in {path}")


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def redact_headers(headers: dict[str, Any]) -> dict[str, Any]:
    redacted = {}
    for key, value in headers.items():
        lk = key.lower()
        if lk in {"proxy-authorization", "authorization", "cookie"}:
            redacted[key] = {
                "present": True,
                "len": len(str(value)),
                "sha256": sha256_text(str(value)),
                "preview": str(value)[:16] + "...",
            }
        else:
            redacted[key] = value
    return redacted


def normalize_headers(headers: dict[str, Any]) -> dict[str, Any]:
    return {str(k).lower(): v for k, v in headers.items()}


def parse_form(body: str) -> dict[str, Any]:
    pairs = urllib.parse.parse_qsl(body, keep_blank_values=True)
    return {
        "order": [k for k, _ in pairs],
        "values": {k: v for k, v in pairs},
        "length": len(body.encode()),
        "sha256": sha256_text(body),
    }


def form_value_summary(values: dict[str, str]) -> dict[str, Any]:
    return {
        key: {
            "len": len(value),
            "sha256": sha256_text(value),
            "preview": value[:64] + ("..." if len(value) > 64 else ""),
        }
        for key, value in values.items()
    }


def diff_maps(a: dict[str, Any], b: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for key in sorted(set(a) | set(b)):
        av = a.get(key)
        bv = b.get(key)
        if av != bv:
            rows.append({
                "key": key,
                "acceptedPresent": key in a,
                "rejectedPresent": key in b,
                "accepted": av,
                "rejected": bv,
            })
    return rows


def request_summary(source: str, req: dict[str, Any], decoded: dict[str, Any] | None = None) -> dict[str, Any]:
    headers = req.get("headers") or {}
    body = req.get("post_data") if "post_data" in req else req.get("body", "")
    form = parse_form(body or "")
    return {
        "source": source,
        "method": req.get("method", "POST"),
        "url": req.get("url"),
        "headers": redact_headers(headers),
        "headerOrder": list(headers.keys()),
        "contentLengthHeader": normalize_headers(headers).get("content-length"),
        "postLenField": req.get("post_len"),
        "bodyLenBytes": len((body or "").encode()),
        "bodySha256": form["sha256"],
        "formOrder": form["order"],
        "formValueSummary": form_value_summary(form["values"]),
        "decodedHandlers": (decoded or {}).get("handlers"),
        "hasSuccessHandler": (decoded or {}).get("hasSuccessHandler"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare accepted browser collector request context with rejected no-browser request context.")
    parser.add_argument("--accepted-trace", type=Path, default=REPO / "output/outlook_browser/runtime_trace_s00ld1lglrw0_1781191381.jsonl")
    parser.add_argument("--accepted-line", type=int, default=933)
    parser.add_argument("--accepted-decode", type=Path, default=REPO / "output/protocol_reverse/collector_decode/collector_decode_s00ld1lglrw0_1781191381.json")
    parser.add_argument("--rejected-combo", type=Path, default=REPO / "output/protocol_reverse/seq5_seq6_combo_probe/seq5_seq6_combo_probe_4a6cb4f4-65d3-11f1-84a5-62666cc2b93d_1781209372.json")
    parser.add_argument("--rejected-step", default="seq5")
    parser.add_argument("--out", type=Path, default=OUT_DIR / "collector_request_context_diff_s00_line933_vs_direct_seq5.json")
    args = parser.parse_args()

    accepted_req = load_jsonl_line(args.accepted_trace, args.accepted_line)
    accepted_decode_doc = load_json(args.accepted_decode)
    accepted_decode = None
    accepted_decoded_entries = accepted_decode_doc.get("decodedEntries") or accepted_decode_doc.get("rows") or []
    success_after_request = [
        row for row in accepted_decoded_entries
        if (row.get("lineNo") or row.get("requestLine") or 0) > args.accepted_line
        and row.get("hasSuccessHandler") is True
    ]
    if success_after_request:
        accepted_decode = min(success_after_request, key=lambda row: row.get("lineNo") or row.get("requestLine") or 10**9)
    else:
        for row in accepted_decoded_entries:
            if row.get("requestLine") == args.accepted_line or row.get("lineNo") == args.accepted_line:
                accepted_decode = row
                break

    rejected_doc = load_json(args.rejected_combo)
    rejected_step = ((rejected_doc.get("results") or {}).get(args.rejected_step) or {})
    rejected_req = (rejected_step.get("material") or {})
    rejected_decode = rejected_step.get("decoded") or {}

    accepted = request_summary(f"{args.accepted_trace}:{args.accepted_line}", accepted_req, accepted_decode)
    rejected = request_summary(f"{args.rejected_combo}:{args.rejected_step}", rejected_req, rejected_decode)
    accepted_headers_norm = normalize_headers(accepted_req.get("headers") or {})
    rejected_headers_norm = normalize_headers(rejected_req.get("headers") or {})
    accepted_form = parse_form(accepted_req.get("post_data") or "")
    rejected_form = parse_form(rejected_req.get("body") or "")

    result = {
        "purpose": "Compare collector request context after decoded activities/Ng/NQ/IP have been narrowed.",
        "accepted": accepted,
        "rejected": rejected,
        "diffs": {
            "sameMethod": accepted["method"] == rejected["method"],
            "sameUrl": accepted["url"] == rejected["url"],
            "sameHeaderOrder": accepted["headerOrder"] == rejected["headerOrder"],
            "headerDiffs": diff_maps(redact_headers(accepted_headers_norm), redact_headers(rejected_headers_norm)),
            "sameFormOrder": accepted_form["order"] == rejected_form["order"],
            "formValueDiffKeys": [row["key"] for row in diff_maps(accepted_form["values"], rejected_form["values"])],
            "formValueDiffs": diff_maps(form_value_summary(accepted_form["values"]), form_value_summary(rejected_form["values"])),
            "sameBodySha256": accepted_form["sha256"] == rejected_form["sha256"],
            "bodyLenDiff": accepted["bodyLenBytes"] - rejected["bodyLenBytes"],
            "contentLengthHeaderDiff": {
                "accepted": accepted["contentLengthHeader"],
                "rejected": rejected["contentLengthHeader"],
            },
        },
        "checks": {
            "acceptedHasSuccessHandler": accepted["hasSuccessHandler"] is True,
            "rejectedReachedNormalFailureHandler": (
                rejected["hasSuccessHandler"] is False
                and isinstance(rejected.get("decodedHandlers"), list)
                and "oIIoIooo" in rejected["decodedHandlers"]
            ),
            "sameUrl": accepted["url"] == rejected["url"],
            "sameMethod": accepted["method"] == rejected["method"],
            "sameHeaderOrder": accepted["headerOrder"] == rejected["headerOrder"],
            "sameFormOrder": accepted_form["order"] == rejected_form["order"],
            "headersDifferOnlyExpectedLengthsAndProxyAuth": False,
        },
    }
    header_diff_keys = {row["key"] for row in result["diffs"]["headerDiffs"]}
    result["checks"]["headersDifferOnlyExpectedLengthsAndProxyAuth"] = header_diff_keys <= {"content-length", "proxy-authorization"}
    result["conclusion"] = (
        "Request context comparison is evidence only: equal URL/method/form order would narrow the gap to body/session/server-state, "
        "while header/order differences identify concrete protocol variables for live controls."
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"json": str(args.out), "checks": result["checks"], "diffKeys": result["diffs"]["formValueDiffKeys"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
