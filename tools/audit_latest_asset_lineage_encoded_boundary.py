#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import urllib.parse
from pathlib import Path
from typing import Any


REPO = Path("/Users/chaopenglv/data/me/Gpt-Agreement-Payment")
PROTO = REPO / "output/protocol_reverse"
OUT_DIR = PROTO / "goal_audit"
RUNTIME_TRACE = REPO / "output/outlook_browser/runtime_trace_s00ld1lglrw0_1781191381.jsonl"
FRESH_SEQ5 = PROTO / "seq5_seq6_combo_probe/extracted/seq5_seq6_combo_probe_a505e6de-660e-11f1-95e3-62666cc2b93d_1781234877_seq5.json"
ACTIVITY_DIFF = PROTO / "px561_compare/seq5_seq6_combo_probe_a505e6de-660e-11f1-95e3-62666cc2b93d_1781234877_seq5_full_activity_diff.json"
FIELD_DIFF = PROTO / "px561_compare/seq5_seq6_combo_probe_a505e6de-660e-11f1-95e3-62666cc2b93d_1781234877_seq5_full_field_diff.json"
ASSET_AUDIT = PROTO / "goal_audit/asset_lineage_combo_control_audit.json"


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    with path.open("r", encoding="utf-8") as fh:
        for idx, line in enumerate(fh, 1):
            if line.strip():
                row = json.loads(line)
                row["_line"] = idx
                rows.append(row)
    return rows


def parse_form(body: str) -> dict[str, str]:
    return dict(urllib.parse.parse_qsl(body, keep_blank_values=True))


def sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def first_diff(a: str, b: str) -> dict[str, Any] | None:
    for idx, (ca, cb) in enumerate(zip(a, b)):
        if ca != cb:
            return {"index": idx, "a": ca, "b": cb, "aContext": a[max(0, idx - 20):idx + 20], "bContext": b[max(0, idx - 20):idx + 20]}
    if len(a) != len(b):
        idx = min(len(a), len(b))
        return {"index": idx, "aLen": len(a), "bLen": len(b), "aContext": a[max(0, idx - 20):idx + 20], "bContext": b[max(0, idx - 20):idx + 20]}
    return None


def s00_line933() -> dict[str, Any]:
    for row in read_jsonl(RUNTIME_TRACE):
        if row.get("_line") == 933 and row.get("kind") == "request":
            body = row.get("post_data") or ""
            return {"line": 933, "body": body, "params": parse_form(body)}
    raise RuntimeError("s00 line933 request not found")


def summarize(label: str, body: str, params: dict[str, str]) -> dict[str, Any]:
    return {
        "label": label,
        "bodyLenBytes": len(body.encode("utf-8")),
        "bodySha256": sha(body),
        "paramOrder": list(params.keys()),
        "paramLens": {k: len(v) for k, v in params.items()},
        "outer": {k: v for k, v in params.items() if k != "payload"},
        "payloadSha256": sha(params.get("payload", "")),
    }


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    s00 = s00_line933()
    fresh_doc = read_json(FRESH_SEQ5)
    fresh_body = (fresh_doc.get("material") or {}).get("body") or ""
    fresh_params = parse_form(fresh_body)
    s00_params = s00["params"]
    all_keys = list(dict.fromkeys([*s00_params.keys(), *fresh_params.keys()]))
    diff_keys = [k for k in all_keys if s00_params.get(k) != fresh_params.get(k)]
    same_keys = [k for k in all_keys if s00_params.get(k) == fresh_params.get(k)]
    activity = read_json(ACTIVITY_DIFF)
    field = read_json(FIELD_DIFF)
    asset = read_json(ASSET_AUDIT)
    payload_a = s00_params.get("payload", "")
    payload_b = fresh_params.get("payload", "")
    result = {
        "purpose": "For the latest direct Webshare asset-lineage control, compare encoded request/body boundary against s00 accepted line933 after decoded activity equality is proven.",
        "evidenceFiles": {
            "s00RuntimeTrace": str(RUNTIME_TRACE.resolve()),
            "freshSeq5": str(FRESH_SEQ5.resolve()),
            "activityDiff": str(ACTIVITY_DIFF.resolve()),
            "fieldDiff": str(FIELD_DIFF.resolve()),
            "assetLineageAudit": str(ASSET_AUDIT.resolve()),
        },
        "acceptedS00": summarize("s00_line933", s00["body"], s00_params),
        "freshRejected": summarize("fresh_asset_lineage_seq5", fresh_body, fresh_params),
        "diff": {
            "sameKeys": same_keys,
            "diffKeys": diff_keys,
            "bodyFirstDiff": first_diff(s00["body"], fresh_body),
            "payloadFirstDiff": first_diff(payload_a, payload_b),
            "payloadLenEqual": len(payload_a) == len(payload_b),
            "bodyLenEqual": len(s00["body"].encode("utf-8")) == len(fresh_body.encode("utf-8")),
        },
        "decodedEqualityEvidence": {
            "activityChecks": activity.get("checks"),
            "fieldChecks": field.get("checks"),
            "fieldDiffCountVsS00Success": field.get("diffCountVsS00Success"),
        },
        "networkControlEvidence": {
            "assetLineageChecks": asset.get("checks"),
        },
        "freshMeta": ((fresh_doc.get("material") or {}).get("meta") or {}),
        "freshHandlers": ((fresh_doc.get("decoded") or {}).get("handlers")),
        "freshHasSuccessHandler": ((fresh_doc.get("decoded") or {}).get("hasSuccessHandler")),
        "checks": {
            "assetLineageWasTested": all((asset.get("checks") or {}).get(k) is True for k in [
                "preStkNsOk",
                "preCaptchaGetOk",
                "preCaptchaGetFreshCookie",
                "preIframeGetOk",
                "preIframeGetFreshCookieAndSid",
                "preMainGetOk",
                "preMainGetFreshCookie",
                "seq5Seq6BothDelivered",
            ]),
            "decodedActivitiesEqual": (activity.get("checks") or {}).get("wholeActivitiesEqual") is True,
            "decodedFieldsEqual": field.get("diffCountVsS00Success") == 0,
            "freshStillRejected": ((fresh_doc.get("decoded") or {}).get("hasSuccessHandler") is False) and "oIIoIooo" in (((fresh_doc.get("decoded") or {}).get("handlers")) or []),
            "bodyLenEqual": len(s00["body"].encode("utf-8")) == len(fresh_body.encode("utf-8")),
            "payloadLenEqual": len(payload_a) == len(payload_b),
            "encodedPayloadDiffers": payload_a != payload_b,
            "pcDiffers": s00_params.get("pc") != fresh_params.get("pc"),
            "onlyPayloadPcAndSessionParamsDiffer": diff_keys == ["payload", "uuid", "cs", "pc", "sid", "p1", "vid", "ci", "cts"],
        },
        "conclusion": (
            "In the latest direct Webshare asset-lineage control, simple network/browser asset hits were replayed and seq5 decoded activities/fields are equal to s00 success, yet the collector still rejects. "
            "The accepted and fresh rejected form bodies have equal byte length and equal payload length, but encoded payload, pc, and live session params differ. "
            "This pins the remaining boundary to encoded payload/pc/session/server-state binding rather than decoded activity content, request ordering, IP, or simple asset lineage."
        ),
    }
    json_path = OUT_DIR / "latest_asset_lineage_encoded_boundary_audit.json"
    md_path = OUT_DIR / "latest_asset_lineage_encoded_boundary_audit.md"
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(
        "\n".join([
            "# latest asset-lineage encoded boundary audit",
            "",
            f"- s00 body sha: `{result['acceptedS00']['bodySha256']}`",
            f"- fresh body sha: `{result['freshRejected']['bodySha256']}`",
            f"- diff keys: `{diff_keys}`",
            "",
            "## Checks",
            *[f"- {k}: `{v}`" for k, v in result["checks"].items()],
            "",
            "## Conclusion",
            result["conclusion"],
            "",
        ]),
        encoding="utf-8",
    )
    print(json.dumps({"json": str(json_path), "md": str(md_path), "checks": result["checks"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
