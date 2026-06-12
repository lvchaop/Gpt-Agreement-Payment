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
FRESH_PROBE = PROTO / "fresh_px561_probe/fresh_px561_probe_d2eae322-65b6-11f1-8553-62666cc2b93d_1781201361.json"
ACTIVITY_DIFF = PROTO / "px561_compare/fresh_px561_probe_d2eae322-65b6-11f1-8553-62666cc2b93d_1781201361_full_activity_diff.json"
OUT = PROTO / "goal_audit/exact_activities_outer_request_diff_audit.json"


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


def s00_request(line_no: int = 933) -> dict[str, Any]:
    for row in read_jsonl(RUNTIME_TRACE):
        if row["_line"] == line_no and row.get("kind") == "request":
            body = row.get("post_data") or ""
            return {
                "line": line_no,
                "url": row.get("url"),
                "headers": row.get("headers") or {},
                "body": body,
                "params": parse_form(body),
            }
    raise RuntimeError(f"runtime request line {line_no} not found")


def fresh_request(path: Path) -> dict[str, Any]:
    doc = read_json(path)
    material = doc["material"]
    return {
        "path": str(path.resolve()),
        "url": material.get("url"),
        "headers": material.get("headers") or {},
        "body": material.get("body") or "",
        "params": parse_form(material.get("body") or ""),
        "response": doc.get("response") or {},
        "decoded": doc.get("decoded") or {},
        "meta": material.get("meta") or {},
        "checks": material.get("checks") or {},
    }


def value_summary(value: str) -> dict[str, Any]:
    return {
        "len": len(value),
        "sha256": hashlib.sha256(value.encode("utf-8")).hexdigest(),
        "preview": value[:160] + (f"...<len={len(value)}>" if len(value) > 160 else ""),
    }


def diff_params(a: dict[str, str], b: dict[str, str]) -> list[dict[str, Any]]:
    rows = []
    for key in list(dict.fromkeys([*a.keys(), *b.keys()])):
        av = a.get(key)
        bv = b.get(key)
        if av == bv:
            continue
        rows.append({
            "key": key,
            "same": False,
            "s00": value_summary(av) if av is not None else None,
            "fresh": value_summary(bv) if bv is not None else None,
        })
    return rows


def interesting_headers(headers: dict[str, Any]) -> dict[str, str]:
    out = {}
    for key, value in headers.items():
        lk = key.lower()
        if lk in {
            "origin",
            "referer",
            "user-agent",
            "content-type",
            "accept",
            "cookie",
            "x-px-authorization",
            "px-authorization",
        } or "sec-" in lk or "px" in lk:
            out[key] = str(value)
    return out


def main() -> int:
    s00 = s00_request()
    fresh = fresh_request(FRESH_PROBE)
    activity = read_json(ACTIVITY_DIFF)
    param_diffs = diff_params(s00["params"], fresh["params"])
    result = {
        "purpose": "After proving decoded activity-array equality, enumerate remaining outer request/session differences between s00 accepted line933 and the fresh rejected control.",
        "inputs": {
            "s00RuntimeTrace": str(RUNTIME_TRACE.resolve()),
            "s00RequestLine": 933,
            "freshProbe": str(FRESH_PROBE.resolve()),
            "activityDiff": str(ACTIVITY_DIFF.resolve()),
        },
        "activityEqualityChecks": activity.get("checks"),
        "responses": {
            "s00Accepted": "runtime line 933 is the browser request immediately followed by decoded oIIoIooo|0 in existing s00 audits",
            "fresh": {
                "status": fresh["response"].get("status"),
                "handlers": fresh["decoded"].get("handlers"),
                "hasSuccessHandler": fresh["decoded"].get("hasSuccessHandler"),
            },
        },
        "outer": {
            "urlEqual": s00["url"] == fresh["url"],
            "bodySha256": {
                "s00": hashlib.sha256(s00["body"].encode()).hexdigest(),
                "fresh": hashlib.sha256(fresh["body"].encode()).hexdigest(),
            },
            "bodyLen": {"s00": len(s00["body"].encode()), "fresh": len(fresh["body"].encode())},
            "paramDiffCount": len(param_diffs),
            "paramDiffs": param_diffs,
            "sameParams": [key for key in s00["params"] if s00["params"].get(key) == fresh["params"].get(key)],
            "interestingHeaders": {
                "s00": interesting_headers(s00["headers"]),
                "fresh": interesting_headers(fresh["headers"]),
            },
            "freshMeta": fresh["meta"],
            "freshChecks": fresh["checks"],
        },
        "checks": {
            "decodedActivitiesWholeEqual": (activity.get("checks") or {}).get("wholeActivitiesEqual") is True,
            "freshRejected": fresh["decoded"].get("hasSuccessHandler") is False,
            "urlEqual": s00["url"] == fresh["url"],
            "seqEqual": s00["params"].get("seq") == fresh["params"].get("seq"),
            "rscEqual": s00["params"].get("rsc") == fresh["params"].get("rsc"),
            "payloadDiffersDespiteDecodedActivitiesEqual": s00["params"].get("payload") != fresh["params"].get("payload"),
            "outerSessionParamsDiffer": any(row["key"] in {"uuid", "cs", "pc", "sid", "p1", "vid", "ci", "cts"} for row in param_diffs),
        },
        "conclusion": (
            "The fresh rejected control has decoded activities equal to s00 accepted line922, but the encoded payload/body and outer session parameters differ. "
            "The next variable boundary is no longer decoded activity content; it is the encoding marker/pc/body binding, collector outer params, headers/cookies, or server-side state accumulated before the request."
        ),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"json": str(OUT), "checks": result["checks"], "paramDiffCount": len(param_diffs)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
