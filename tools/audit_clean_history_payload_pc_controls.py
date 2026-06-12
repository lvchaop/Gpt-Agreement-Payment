#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import urllib.parse
from pathlib import Path
from typing import Any


REPO = Path("/Users/chaopenglv/data/me/Gpt-Agreement-Payment")
PROTO = REPO / "output/protocol_reverse"
RUNTIME_TRACE = REPO / "output/outlook_browser/runtime_trace_s00ld1lglrw0_1781191381.jsonl"
OUT = PROTO / "goal_audit/clean_history_payload_pc_controls_audit.json"

EXACT_PAYLOAD_PC = PROTO / "fresh_px561_probe/fresh_px561_probe_c257e05c-65c3-11f1-a79e-62666cc2b93d_1781203725.json"
TEMPLATE_MARKER = PROTO / "fresh_px561_probe/fresh_px561_probe_c257e05c-65c3-11f1-a79e-62666cc2b93d_1781203767.json"
TEMPLATE_MARKER_DIFF = PROTO / "px561_compare/fresh_px561_probe_c257e05c-65c3-11f1-a79e-62666cc2b93d_1781203767_full_activity_diff.json"


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    with path.open("r", encoding="utf-8") as fh:
        for line_no, line in enumerate(fh, 1):
            if line.strip():
                row = json.loads(line)
                row["_line"] = line_no
                rows.append(row)
    return rows


def parse_form(body: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for part in str(body or "").split("&"):
        if not part:
            continue
        key, _, raw = part.partition("=")
        out[urllib.parse.unquote_plus(key)] = urllib.parse.unquote(raw)
    return out


def sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def s00_request() -> dict[str, Any]:
    for row in read_jsonl(RUNTIME_TRACE):
        if row["_line"] == 933 and row.get("kind") == "request":
            body = row.get("post_data") or ""
            return {"body": body, "params": parse_form(body)}
    raise RuntimeError("s00 line 933 request not found")


def summarize(path: Path, s00: dict[str, Any], diff_path: Path | None = None) -> dict[str, Any]:
    doc = read_json(path)
    body = (doc.get("material") or {}).get("body") or ""
    params = parse_form(body)
    param_diff_keys = [key for key in list(dict.fromkeys([*s00["params"], *params])) if s00["params"].get(key) != params.get(key)]
    return {
        "path": str(path.resolve()),
        "status": (doc.get("response") or {}).get("status"),
        "bodyText": (doc.get("response") or {}).get("bodyText"),
        "handlers": (doc.get("decoded") or {}).get("handlers"),
        "hasSuccessHandler": (doc.get("decoded") or {}).get("hasSuccessHandler"),
        "decodedMode": (doc.get("decoded") or {}).get("mode"),
        "checks": (doc.get("material") or {}).get("checks"),
        "meta": (doc.get("material") or {}).get("meta"),
        "outer": {
            "bodyLen": len(body.encode()),
            "bodySha256": sha(body),
            "payloadEqualS00": params.get("payload") == s00["params"].get("payload"),
            "pcEqualS00": params.get("pc") == s00["params"].get("pc"),
            "paramDiffKeys": param_diff_keys,
        },
        "activityChecks": (read_json(diff_path).get("checks") if diff_path else None),
    }


def main() -> int:
    s00 = s00_request()
    exact_payload_pc = summarize(EXACT_PAYLOAD_PC, s00)
    template_marker = summarize(TEMPLATE_MARKER, s00, TEMPLATE_MARKER_DIFF)
    checks = {
        "exactPayloadPcHttp200": exact_payload_pc["status"] == 200,
        "exactPayloadPcReturnedDoEmpty": exact_payload_pc["bodyText"] == '{"do":[]}\n',
        "exactPayloadPcMatchesPayloadAndPc": exact_payload_pc["outer"]["payloadEqualS00"] is True and exact_payload_pc["outer"]["pcEqualS00"] is True,
        "exactPayloadPcLeavesOnlySessionParamDiffs": exact_payload_pc["outer"]["paramDiffKeys"] == ["uuid", "cs", "sid", "p1", "vid", "ci", "cts"],
        "templateMarkerRejected": template_marker["hasSuccessHandler"] is False,
        "templateMarkerWholeActivitiesEqual": (template_marker.get("activityChecks") or {}).get("wholeActivitiesEqual") is True,
    }
    result = {
        "purpose": "Test payload/pc binding controls after decoded activity equality was proven insufficient.",
        "s00": {"runtimeTrace": str(RUNTIME_TRACE.resolve()), "requestLine": 933, "bodySha256": sha(s00["body"]), "bodyLen": len(s00["body"].encode())},
        "exactPayloadPcFreshOuter": exact_payload_pc,
        "templateMarkerFreshUuid": template_marker,
        "checks": checks,
        "conclusion": (
            "Using exact s00 payload+pc with fresh outer session params no longer produces the normal rejection handler; collector returns an empty do list. "
            "Using template marker with fresh payload uuid keeps decoded activities equal but still returns oIIoIooo|-1. "
            "This indicates payload/pc/uuid/session binding is checked before or alongside handler generation; the remaining boundary is coherent payload encoding with outer session params and server-side state."
        ),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"json": str(OUT), "checks": checks}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
