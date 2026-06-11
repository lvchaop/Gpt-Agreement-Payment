#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import importlib.util
import json
import urllib.parse
from pathlib import Path
from typing import Any


REPO = Path("/Users/chaopenglv/data/me/Gpt-Agreement-Payment")
DECODE_TOOL = REPO / "tools/decode_bundle_payload_with_marker.py"
OUT_DIR = REPO / "output/protocol_reverse/pow"
RUNS = [
    {"run": "ni109xdjp5zp_1780948211", "role": "accepted_success"},
    {"run": "j0t8van4qyhm_1781119142", "role": "accepted_success"},
    {"run": "fk8zn2nqhex1_1781115338", "role": "aeax_only_negative_control"},
    {"run": "b0hnt0zycbpx_1781116322", "role": "aeax_only_negative_control"},
]


def load_module(path: Path, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    with path.open("r", encoding="utf-8") as fh:
        for line_no, line in enumerate(fh, 1):
            if not line.strip():
                continue
            row = json.loads(line)
            row["_line"] = line_no
            rows.append(row)
    return rows


def parse_form(body: str) -> dict[str, str]:
    out = {}
    for part in str(body or "").split("&"):
        if not part:
            continue
        key, _, raw = part.partition("=")
        out[urllib.parse.unquote_plus(key)] = urllib.parse.unquote(raw)
    return out


def collector_pow_challenges(run: str) -> list[dict[str, Any]]:
    path = REPO / f"output/protocol_reverse/collector_decode/collector_decode_{run}.json"
    doc = json.loads(path.read_text(encoding="utf-8"))
    out = []
    for entry in doc.get("decodedEntries") or []:
        for part in entry.get("parts") or []:
            fields = str(part).split("|")
            if fields[0] != "IooIIo" or len(fields) < 5:
                continue
            prefix = fields[2]
            target_hash = fields[3]
            out.append(
                {
                    "collectorLine": entry.get("lineNo"),
                    "raw": part,
                    "prefix": prefix,
                    "targetHash": target_hash,
                    "difficulty": fields[4],
                }
            )
    return out


def pow_hits(js_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for row in js_rows:
        if row.get("kind") != "hsprotect.captcha.pow.hit":
            continue
        data = row.get("data") or {}
        value = str(data.get("value") or "")
        out.append(
            {
                "line": row["_line"],
                "wall_t": row.get("wall_t"),
                "i": data.get("i"),
                "value": value,
                "sha256": hashlib.sha256(value.encode("utf-8")).hexdigest() if value else None,
            }
        )
    return out


def px561_from_tf(run: str, js_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for row in js_rows:
        if row.get("kind") != "hsprotect.main.tf.payload":
            continue
        data = row.get("data") or {}
        for idx, activity in enumerate(data.get("activities") or []):
            if not isinstance(activity, dict) or activity.get("t") != "PX561":
                continue
            d = activity.get("d") or {}
            out.append(
                {
                    "source": "tf.payload",
                    "line": row["_line"],
                    "pc": data.get("pc") or (data.get("meta") or {}).get("pc"),
                    "activityIndex": idx,
                    "oskValue": d.get("OSkIb39DDA=="),
                    "bztValue": d.get("Bzt2fUFRcw=="),
                    "hasTBR9": "TBR9Ugl7emA=" in d,
                    "hasAEAx": "AEAxBkUsPjQ=" in d,
                }
            )
    return out


def px561_from_ni_bundle() -> list[dict[str, Any]]:
    dec = load_module(DECODE_TOOL, "decode_bundle_payload_with_marker")
    runtime_trace = REPO / "output/outlook_browser/runtime_trace_ni109xdjp5zp_1780948211.jsonl"
    collector_decode = REPO / "output/protocol_reverse/collector_decode/collector_decode_ni109xdjp5zp_1780948211.json"
    rows = dec.read_jsonl(runtime_trace)
    timeline = dec.build_marker_timeline(collector_decode)
    out = []
    for row in rows:
        if row.get("kind") != "request" or not str(row.get("url") or "").endswith("/assets/js/bundle"):
            continue
        params = parse_form(row.get("post_data") or "")
        marker = dec.marker_for_request(timeline, int(row["_line"]))
        decoded = dec.decode_payload(params.get("payload", ""), marker["marker"], params.get("uuid", ""))
        activities = decoded.get("json") if isinstance(decoded.get("json"), list) else []
        for idx, activity in enumerate(activities):
            if not isinstance(activity, dict) or activity.get("t") != "PX561":
                continue
            d = activity.get("d") or {}
            out.append(
                {
                    "source": "bundle.payload",
                    "line": row["_line"],
                    "seq": params.get("seq"),
                    "activityIndex": idx,
                    "oskValue": d.get("OSkIb39DDA=="),
                    "bztValue": d.get("Bzt2fUFRcw=="),
                    "hasTBR9": "TBR9Ugl7emA=" in d,
                    "hasAEAx": "AEAxBkUsPjQ=" in d,
                }
            )
    return out


def match_osks(px_rows: list[dict[str, Any]], hits: list[dict[str, Any]], challenges: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for px in px_rows:
        osk = px.get("oskValue")
        hit = next((h for h in hits if h["value"] == osk), None)
        challenge = next(
            (
                c
                for c in challenges
                if isinstance(osk, str)
                and hashlib.sha256(osk.encode("utf-8")).hexdigest() == c["targetHash"]
            ),
            None,
        )
        out.append(
            {
                **px,
                "oskIsValid64Hex": isinstance(osk, str) and len(osk) == 64 and all(ch in "0123456789abcdefABCDEF" for ch in osk),
                "matchesPowHit": hit is not None,
                "powHit": hit,
                "matchesCollectorChallengeHash": challenge is not None,
                "startsWithCollectorPrefix": bool(challenge and isinstance(osk, str) and osk.startswith(challenge["prefix"])),
                "collectorChallenge": challenge,
            }
        )
    return out


def summarize_run(item: dict[str, str]) -> dict[str, Any]:
    run = item["run"]
    js_rows = read_jsonl(REPO / f"output/outlook_browser/js_internal_trace_{run}.jsonl")
    hits = pow_hits(js_rows)
    challenges = collector_pow_challenges(run)
    px_rows = px561_from_ni_bundle() if run == "ni109xdjp5zp_1780948211" else px561_from_tf(run, js_rows)
    matches = match_osks(px_rows, hits, challenges)
    return {
        "run": run,
        "role": item["role"],
        "powHits": hits,
        "collectorPowChallenges": challenges,
        "px561Rows": matches,
    }


def main() -> int:
    runs = [summarize_run(item) for item in RUNS]
    accepted_px = [px for r in runs if r["role"] == "accepted_success" for px in r["px561Rows"] if px["hasTBR9"]]
    controls = [r for r in runs if r["role"] != "accepted_success"]
    result = {
        "purpose": "Correlate collector IooIIo POW challenges, runtime pow.hit values, and PX561 OSkIb39DDA values.",
        "runs": runs,
        "checks": {
            "acceptedRowsHaveValidOsk": all(px["oskIsValid64Hex"] for px in accepted_px),
            "acceptedRowsMatchPowHit": all(px["matchesPowHit"] for px in accepted_px),
            "acceptedRowsMatchCollectorChallengeHash": all(px["matchesCollectorChallengeHash"] for px in accepted_px),
            "controlsHaveNoPowHit": all(not r["powHits"] for r in controls),
            "controlsHaveNoValidOsk": all(not px["oskIsValid64Hex"] for r in controls for px in r["px561Rows"]),
            "controlsStillHaveCollectorChallenges": all(bool(r["collectorPowChallenges"]) for r in controls),
        },
        "conclusion": (
            "In accepted rows, PX561 OSkIb39DDA equals a runtime hsprotect.captcha.pow.hit value and its SHA-256 satisfies a collector IooIIo target hash. "
            "AEAx-only controls still receive collector POW challenges but have no runtime pow.hit and no valid OSk value, so the OSk transition is specifically worker-hit-to-PX561 rather than mere challenge receipt."
        ),
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_json = OUT_DIR / "pow_to_px561_osk_audit.json"
    out_md = OUT_DIR / "pow_to_px561_osk_audit.md"
    out_json.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = ["# POW to PX561 OSk audit", "", "## Checks", ""]
    for key, value in result["checks"].items():
        lines.append(f"- {key}: `{value}`")
    lines += ["", "## PX561 rows", "", "| run | role | source | line | OSk valid | hit | challenge | Bzt | TBR9 |", "|---|---|---|---:|---:|---:|---:|---|---:|"]
    for run in runs:
        for px in run["px561Rows"]:
            lines.append(
                f"| {run['run']} | {run['role']} | {px['source']} | {px['line']} | {px['oskIsValid64Hex']} | "
                f"{px['matchesPowHit']} | {px['matchesCollectorChallengeHash']} | `{px.get('bztValue')}` | {px['hasTBR9']} |"
            )
    lines += ["", "## Conclusion", "", result["conclusion"], ""]
    out_md.write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"json": str(out_json), "md": str(out_md), "checks": result["checks"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
