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
OUT = PROTO / "goal_audit/clean_history_outer_binding_audit.json"

EXACT_WHOLE = PROTO / "fresh_px561_probe/fresh_px561_probe_c257e05c-65c3-11f1-a79e-62666cc2b93d_1781203460.json"
EXACT_WHOLE_DIFF = PROTO / "px561_compare/fresh_px561_probe_c257e05c-65c3-11f1-a79e-62666cc2b93d_1781203460_full_activity_diff.json"
PROXY_AUTH = PROTO / "fresh_px561_probe/fresh_px561_probe_c257e05c-65c3-11f1-a79e-62666cc2b93d_1781203592.json"
PROXY_AUTH_DIFF = PROTO / "px561_compare/fresh_px561_probe_c257e05c-65c3-11f1-a79e-62666cc2b93d_1781203592_full_activity_diff.json"


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
    raise RuntimeError(f"s00 runtime request line {line_no} not found")


def fresh_request(path: Path) -> dict[str, Any]:
    doc = read_json(path)
    material = doc.get("material") or {}
    body = material.get("body") or ""
    return {
        "path": str(path.resolve()),
        "url": material.get("url"),
        "headers": material.get("headers") or {},
        "body": body,
        "params": parse_form(body),
        "status": (doc.get("response") or {}).get("status"),
        "handlers": (doc.get("decoded") or {}).get("handlers"),
        "hasSuccessHandler": (doc.get("decoded") or {}).get("hasSuccessHandler"),
        "checks": material.get("checks"),
        "meta": material.get("meta"),
    }


def sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def value_summary(value: str | None) -> dict[str, Any] | None:
    if value is None:
        return None
    return {
        "len": len(value),
        "sha256": sha(value),
        "preview": value[:120] + (f"...<len={len(value)}>" if len(value) > 120 else ""),
    }


def param_diffs(a: dict[str, str], b: dict[str, str]) -> list[dict[str, Any]]:
    rows = []
    for key in list(dict.fromkeys([*a.keys(), *b.keys()])):
        if a.get(key) == b.get(key):
            continue
        rows.append({"key": key, "s00": value_summary(a.get(key)), "fresh": value_summary(b.get(key))})
    return rows


def lower_headers(headers: dict[str, Any]) -> dict[str, str]:
    return {str(k).lower(): str(v) for k, v in headers.items()}


def header_diffs(a: dict[str, Any], b: dict[str, Any]) -> list[dict[str, Any]]:
    la = lower_headers(a)
    lb = lower_headers(b)
    rows = []
    for key in sorted(set(la) | set(lb)):
        if la.get(key) != lb.get(key):
            rows.append({"key": key, "s00": la.get(key), "fresh": lb.get(key)})
    return rows


def summarize_fresh(path: Path, diff_path: Path, s00: dict[str, Any]) -> dict[str, Any]:
    fresh = fresh_request(path)
    diff = read_json(diff_path)
    return {
        "probe": fresh,
        "activityChecks": diff.get("checks"),
        "outer": {
            "urlEqual": s00["url"] == fresh["url"],
            "bodyLen": {"s00": len(s00["body"].encode()), "fresh": len(fresh["body"].encode())},
            "bodySha256": {"s00": sha(s00["body"]), "fresh": sha(fresh["body"])},
            "sameParams": [key for key in s00["params"] if s00["params"].get(key) == fresh["params"].get(key)],
            "paramDiffs": param_diffs(s00["params"], fresh["params"]),
            "headerDiffs": header_diffs(s00["headers"], fresh["headers"]),
        },
    }


def main() -> int:
    s00 = s00_request()
    exact = summarize_fresh(EXACT_WHOLE, EXACT_WHOLE_DIFF, s00)
    proxy = summarize_fresh(PROXY_AUTH, PROXY_AUTH_DIFF, s00)
    checks = {
        "exactWholeActivitiesRejected": exact["probe"]["hasSuccessHandler"] is False,
        "exactWholeActivitiesEqual": (exact.get("activityChecks") or {}).get("wholeActivitiesEqual") is True,
        "proxyAuthControlRejected": proxy["probe"]["hasSuccessHandler"] is False,
        "proxyAuthControlWholeActivitiesEqual": (proxy.get("activityChecks") or {}).get("wholeActivitiesEqual") is True,
        "proxyAuthorizationNotSufficient": proxy["probe"]["hasSuccessHandler"] is False,
        "bodyLengthMatchesS00": exact["outer"]["bodyLen"]["s00"] == exact["outer"]["bodyLen"]["fresh"],
        "bodyShaDiffersFromS00": exact["outer"]["bodySha256"]["s00"] != exact["outer"]["bodySha256"]["fresh"],
        "remainingParamDiffKeys": [row["key"] for row in exact["outer"]["paramDiffs"]],
    }
    result = {
        "purpose": "After decoded activity equality, enumerate outer/body/header differences and test proxy-authorization as a header control.",
        "s00": {
            "runtimeTrace": str(RUNTIME_TRACE.resolve()),
            "requestLine": 933,
            "url": s00["url"],
            "bodySha256": sha(s00["body"]),
            "bodyLenBytes": len(s00["body"].encode()),
        },
        "exactWholeActivitiesControl": exact,
        "proxyAuthorizationControl": proxy,
        "checks": checks,
        "conclusion": (
            "The clean exact-whole-activities request has the same URL and body length as s00 accepted line933, but payload/body sha and outer session params differ. "
            "Adding proxy-authorization still returns oIIoIooo|-1 while decoded activities remain equal, so proxy-authorization/header parity is not sufficient. "
            "The remaining observable boundary is payload/pc binding plus outer session params/cookies or server-side state."
        ),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"json": str(OUT), "checks": checks}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
