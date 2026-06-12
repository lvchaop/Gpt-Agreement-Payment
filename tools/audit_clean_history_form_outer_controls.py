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
OUT = PROTO / "goal_audit/clean_history_form_outer_controls_audit.json"

FRESH_PAYLOAD_TEMPLATE_OUTER = PROTO / "fresh_px561_probe/fresh_px561_probe_c257e05c-65c3-11f1-a79e-62666cc2b93d_1781204089.json"
EXACT_BODY_TEMPLATE_OUTER = PROTO / "fresh_px561_probe/fresh_px561_probe_c257e05c-65c3-11f1-a79e-62666cc2b93d_1781204109.json"


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
            return {"body": body, "params": parse_form(body), "bodySha256": sha(body)}
    raise RuntimeError("s00 line 933 request not found")


def summarize(path: Path, s00: dict[str, Any]) -> dict[str, Any]:
    doc = read_json(path)
    material = doc.get("material") or {}
    meta = material.get("meta") or {}
    body = material.get("body") or ""
    params = parse_form(body)
    diff_keys = [key for key in list(dict.fromkeys([*s00["params"], *params])) if s00["params"].get(key) != params.get(key)]
    return {
        "path": str(path.resolve()),
        "status": (doc.get("response") or {}).get("status"),
        "bodyText": (doc.get("response") or {}).get("bodyText"),
        "handlers": (doc.get("decoded") or {}).get("handlers"),
        "hasSuccessHandler": (doc.get("decoded") or {}).get("hasSuccessHandler"),
        "decodedMode": (doc.get("decoded") or {}).get("mode"),
        "checks": material.get("checks"),
        "meta": {
            key: meta.get(key)
            for key in [
                "payloadUuid",
                "pcUuid",
                "pc",
                "markerJo",
                "payloadUuidSource",
                "pcUuidSource",
                "markerSource",
                "formOuterSource",
            ]
        },
        "outer": {
            "bodyEqualS00": body == s00["body"],
            "bodySha256": sha(body),
            "bodyLen": len(body.encode()),
            "diffKeysVsS00": diff_keys,
            "sameKeysVsS00": [key for key in s00["params"] if s00["params"].get(key) == params.get(key)],
        },
    }


def main() -> int:
    s00 = s00_request()
    fresh_payload_template_outer = summarize(FRESH_PAYLOAD_TEMPLATE_OUTER, s00)
    exact_body_template_outer = summarize(EXACT_BODY_TEMPLATE_OUTER, s00)
    checks = {
        "freshPayloadTemplateOuterReturnedDoEmpty": fresh_payload_template_outer["bodyText"] == '{"do":[]}\n',
        "freshPayloadTemplateOuterDiffOnlyPayloadPc": fresh_payload_template_outer["outer"]["diffKeysVsS00"] == ["payload", "pc"],
        "exactBodyTemplateOuterBodyEqualS00": exact_body_template_outer["outer"]["bodyEqualS00"] is True,
        "exactBodyTemplateOuterRejected": exact_body_template_outer["hasSuccessHandler"] is False,
        "exactBodyTemplateOuterNormalHandlers": "oIIoIooo" in (exact_body_template_outer.get("handlers") or []),
    }
    result = {
        "purpose": "Test form outer/session binding by crossing fresh/template payload with template outer params.",
        "s00": {"runtimeTrace": str(RUNTIME_TRACE.resolve()), "requestLine": 933, "bodySha256": s00["bodySha256"], "bodyLen": len(s00["body"].encode())},
        "freshPayloadTemplateOuter": fresh_payload_template_outer,
        "exactBodyTemplateOuter": exact_body_template_outer,
        "checks": checks,
        "conclusion": (
            "Fresh payload/pc with template outer params returns {do:[]}, even though only payload and pc differ from s00 line933. "
            "Exact s00 body with template outer params is byte-identical to s00 line933 but now returns oIIoIooo|-1. "
            "Therefore live success is not recoverable from static exact body alone; collector server-side state/time/history is part of the remaining boundary."
        ),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"json": str(OUT), "checks": checks}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
