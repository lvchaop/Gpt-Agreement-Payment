#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import urllib.parse
from pathlib import Path
from typing import Any


REPO = Path("/Users/chaopenglv/data/me/Gpt-Agreement-Payment")
PROTO = REPO / "output/protocol_reverse"
OUT = PROTO / "goal_audit/clean_history_pc_uuid_controls_audit.json"

EXACT_PAYLOAD_FRESH_PC = PROTO / "fresh_px561_probe/fresh_px561_probe_c257e05c-65c3-11f1-a79e-62666cc2b93d_1781203939.json"
FRESH_PAYLOAD_TEMPLATE_PC = PROTO / "fresh_px561_probe/fresh_px561_probe_c257e05c-65c3-11f1-a79e-62666cc2b93d_1781203971.json"


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def parse_form(body: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for part in str(body or "").split("&"):
        if not part:
            continue
        key, _, raw = part.partition("=")
        out[urllib.parse.unquote_plus(key)] = urllib.parse.unquote(raw)
    return out


def summarize(path: Path) -> dict[str, Any]:
    doc = read_json(path)
    material = doc.get("material") or {}
    meta = material.get("meta") or {}
    body = material.get("body") or ""
    params = parse_form(body)
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
            "payloadSha256": hashlib.sha256((params.get("payload") or "").encode()).hexdigest(),
            "pc": params.get("pc"),
            "uuid": params.get("uuid"),
            "cs": params.get("cs"),
        },
    }


def main() -> int:
    exact_payload_fresh_pc = summarize(EXACT_PAYLOAD_FRESH_PC)
    fresh_payload_template_pc = summarize(FRESH_PAYLOAD_TEMPLATE_PC)
    checks = {
        "exactPayloadFreshPcReturnedDoEmpty": exact_payload_fresh_pc["bodyText"] == '{"do":[]}\n',
        "exactPayloadFreshPcNoHandlers": exact_payload_fresh_pc["handlers"] == [],
        "freshPayloadTemplatePcRejected": fresh_payload_template_pc["hasSuccessHandler"] is False,
        "freshPayloadTemplatePcHasNormalHandlers": "oIIoIooo" in (fresh_payload_template_pc.get("handlers") or []),
        "pcUuidControlImplemented": exact_payload_fresh_pc["meta"].get("pcUuidSource") == "fresh"
        and fresh_payload_template_pc["meta"].get("pcUuidSource") == "template",
    }
    result = {
        "purpose": "Split payload encoding uuid from pc HMAC uuid to test collector binding behavior.",
        "exactPayloadFreshPc": exact_payload_fresh_pc,
        "freshPayloadTemplatePc": fresh_payload_template_pc,
        "checks": checks,
        "conclusion": (
            "Exact s00 payload with a fresh-uuid pc still returns {do:[]}, so changing pc alone cannot make a stale/template payload valid for the fresh session. "
            "Fresh-uuid payload with template-uuid pc still reaches the normal oIIoIooo|-1 path, so pc mismatch alone is not enough to explain empty-do behavior. "
            "The boundary remains coupled payload encoding uuid/marker with outer session state, not pc in isolation."
        ),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"json": str(OUT), "checks": checks}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
