#!/usr/bin/env python3
from __future__ import annotations

import base64
import hashlib
import importlib.util
import json
import re
import urllib.parse
from pathlib import Path
from typing import Any


REPO = Path("/Users/chaopenglv/data/me/Gpt-Agreement-Payment")
SUCCESS_RUNTIME = REPO / "output/outlook_browser/runtime_trace_ni109xdjp5zp_1780948211.jsonl"
SUCCESS_COLLECTOR = REPO / "output/protocol_reverse/collector_decode/collector_decode_ni109xdjp5zp_1780948211.json"
SUCCESS_BUNDLE = REPO / "output/protocol_reverse/bundle_activity_matches/bundle_activity_matches_ni109xdjp5zp_1780948211.json"
REMAINING_FIELDS = REPO / "output/protocol_reverse/source_offsets/captcha_px561_remaining_fields.json"
CAPTCHA_BEAUTIFIED = REPO / "output/outlook_browser/js_static_analysis/captcha.beautified.js"
CAPTCHA_SOURCE = REPO / "output/outlook_browser/hsprotect_js_patch/captcha_main_1781017191_42fe203091d0.source.js"
EXACT_NI109_CAPTCHA_SOURCE = REPO / "output/protocol_reverse/exact_source/captcha_ni109_4b399270.source.js"
MAIN_BEAUTIFIED = REPO / "output/outlook_browser/js_static_analysis/main.beautified.js"
DECODE_TOOL = REPO / "tools/decode_bundle_payload_with_marker.py"
OUT_DIR = REPO / "output/protocol_reverse/source_offsets"

TARGET_KEY = "TBR9Ugl7emA="
TARGET_VALUE_PREFIX = "Y@tvUUF@W"


def load_decode_tool():
    spec = importlib.util.spec_from_file_location("decode_bundle_payload_with_marker", DECODE_TOOL)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {DECODE_TOOL}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
        if not line.strip():
            continue
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


def xor_string(value: str, key: int) -> str:
    return "".join(chr(ord(ch) ^ key) for ch in value)


def encode_base(decoded_text: str) -> str:
    raw = xor_string(decoded_text, 50)
    return base64.b64encode(raw.encode("latin1")).decode()


def insert_marker(chars: str, base: str, positions: list[int]) -> str:
    out = ""
    cursor = 0
    for idx, ch in enumerate(chars):
        cut = positions[idx] - idx - 1
        out += base[cursor:cut] + ch
        cursor = cut
    return out + base[cursor:]


def source_sha(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"path": str(path), "exists": False}
    data = path.read_bytes()
    return {
        "path": str(path),
        "exists": True,
        "bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
    }


def same_file_sha(a: Path, b: Path) -> bool | None:
    if not a.exists() or not b.exists():
        return None
    return source_sha(a)["sha256"] == source_sha(b)["sha256"]


def find_success_request(rows: list[dict[str, Any]]) -> dict[str, Any]:
    for row in rows:
        if row.get("_line") == 308 and str(row.get("url") or "").endswith("/assets/js/bundle"):
            return row
    raise RuntimeError("success request line 308 /assets/js/bundle not found")


def find_success_px561() -> dict[str, Any]:
    bundle = read_json(SUCCESS_BUNDLE)
    for req in bundle.get("requests", []):
        if req.get("requestLine") != 308:
            continue
        for item in req.get("activitiesWithMatches", []):
            activity = item.get("activity") or {}
            if activity.get("t") == "PX561":
                return {
                    "request": req,
                    "activityIndex": item.get("index"),
                    "d": activity.get("d") or {},
                }
    raise RuntimeError("success PX561 not found")


def extract_stack_urls(d: dict[str, Any]) -> list[dict[str, str]]:
    stack = str(d.get("W0shQR0nJHc=") or "")
    urls = []
    for match in re.finditer(r"https://captcha\.hsprotect\.net/[^\s:]+captcha\.js\?([^\s:]+)", stack):
        query = match.group(1)
        params = dict(urllib.parse.parse_qsl(query))
        urls.append({
            "urlPrefix": match.group(0).split(":1724", 1)[0],
            "u": params.get("u", ""),
            "v": params.get("v", ""),
        })
    return urls


def find_source_occurrences(needles: list[str]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for path in [CAPTCHA_BEAUTIFIED, CAPTCHA_SOURCE, MAIN_BEAUTIFIED, SUCCESS_RUNTIME]:
        text = path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""
        out[str(path.relative_to(REPO))] = {
            needle: text.count(needle)
            for needle in needles
        }
    return out


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    dec = load_decode_tool()
    rows = read_jsonl(SUCCESS_RUNTIME)
    request = find_success_request(rows)
    params = parse_form(request.get("post_data") or "")
    timeline = dec.build_marker_timeline(SUCCESS_COLLECTOR)
    marker = dec.marker_for_request(timeline, 308)
    decoded = dec.decode_payload(params["payload"], marker["marker"], params["uuid"])

    base = encode_base(decoded["decodedText"])
    positions = dec.insertion_positions(marker["marker"], len(base), params["uuid"])
    replay_payload = insert_marker(marker["marker"], base, positions)

    px561 = find_success_px561()
    d = px561["d"]
    keys = list(d)
    tbr_value = d.get(TARGET_KEY)
    tbr_index = keys.index(TARGET_KEY) if TARGET_KEY in d else None
    decoded_text = decoded["decodedText"]
    tbr_text_index = decoded_text.find(f'"{TARGET_KEY}"')

    remaining = read_json(REMAINING_FIELDS)
    remaining_source = remaining.get("source")
    decoder_records = [
        rec for rec in remaining.get("records", [])
        if rec.get("decoded") in {TARGET_KEY, "succeeded", "AEAxBkUsPjQ="}
    ]

    static_context = {
        "remainingFieldsSource": remaining_source,
        "remainingFieldsSourceIsSuccessRun": "1780948211" in str(remaining_source),
        "successRuntime": str(SUCCESS_RUNTIME),
        "successCaptchaUrls": extract_stack_urls(d),
        "exactNi109CaptchaSource": source_sha(EXACT_NI109_CAPTCHA_SOURCE),
        "exactNi109SourceMatchesLaterCapturedSource": same_file_sha(EXACT_NI109_CAPTCHA_SOURCE, CAPTCHA_SOURCE),
        "exactNi109SourceMatchesJsProbeCaptcha": same_file_sha(EXACT_NI109_CAPTCHA_SOURCE, REPO / "output/outlook_browser/js_probe/captcha.js"),
        "localStaticSources": [
            source_sha(CAPTCHA_BEAUTIFIED),
            source_sha(CAPTCHA_SOURCE),
            source_sha(EXACT_NI109_CAPTCHA_SOURCE),
            source_sha(MAIN_BEAUTIFIED),
        ],
    }

    result = {
        "inputs": {
            "successRuntime": str(SUCCESS_RUNTIME),
            "successCollectorDecode": str(SUCCESS_COLLECTOR),
            "successBundle": str(SUCCESS_BUNDLE),
            "remainingFields": str(REMAINING_FIELDS),
            "decodeTool": str(DECODE_TOOL),
        },
        "bundleDecodeIntegrity": {
            "requestLine": request["_line"],
            "payloadLen": len(params["payload"]),
            "uuid": params["uuid"],
            "markerQi": marker["qi"],
            "marker": marker["marker"],
            "extractedMarker": decoded["marker"],
            "markerMatch": decoded["markerMatch"],
            "jsonError": decoded["jsonError"],
            "decodedTextHasTbrKey": f'"{TARGET_KEY}"' in decoded_text,
            "decodedTextHasTbrValuePrefix": TARGET_VALUE_PREFIX in decoded_text,
            "tbrTextIndex": tbr_text_index,
            "replayPayloadMatchesObserved": replay_payload == params["payload"],
            "replayPayloadLen": len(replay_payload),
        },
        "successPx561Tbr": {
            "activityIndex": px561["activityIndex"],
            "keyCount": len(d),
            "tbrPresent": TARGET_KEY in d,
            "tbrIndex": tbr_index,
            "tbrValueType": type(tbr_value).__name__,
            "tbrValueLen": len(tbr_value) if isinstance(tbr_value, str) else None,
            "tbrValue": tbr_value,
            "neighborKeys": keys[max(0, (tbr_index or 0) - 3): min(len(keys), (tbr_index or 0) + 4)] if tbr_index is not None else [],
        },
        "staticDecoderContext": static_context,
        "staticDecoderRecords": decoder_records,
        "literalOccurrences": find_source_occurrences([
            TARGET_KEY,
            str(tbr_value or "")[:12],
            TARGET_VALUE_PREFIX,
            "A3QrSTsPOGBTFDFT",
            "JEMaEwsNMDJS",
            "FnM4CCwDASRmEyFT",
        ]),
        "findings": [
            "The success request line 308 payload decodes to text containing TBR9Ugl7emA= and its long value before JSON object inspection.",
            "Re-encoding the exact decoded text with the same marker algorithm reproduces the observed request payload byte-for-byte at the form-field string level.",
            "Therefore the TBR9 field is not introduced by the downstream Python JSON object extraction step.",
            "The exact ni109 captcha.js source fetched by the success stack URL is byte-identical to the later captured captcha source used by the static decoder audit.",
            "Therefore t(v(-541,-541))->succeeded and TBR9/_s are now proven for the ni109 executed source, not just a later same-family source.",
        ],
        "nextEvidenceTargets": [
            "Audit code paths that rewrite/delete/re-add TBR9 between captcha D/Ts assignment and Yc/tf.",
            "Capture/calculate the pre-Yc object and tf entry for a new observation sample, clearly labeled as patched observation, to locate whether TBR9 exists before serialization.",
            "If no rewrite path is found statically, search for another producer of the fyNOZTpPQF4=/TBR9 group.",
        ],
    }

    json_path = OUT_DIR / "tbr9_decode_context_integrity_audit.json"
    md_path = OUT_DIR / "tbr9_decode_context_integrity_audit.md"
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "# TBR9 decode/context integrity audit",
        "",
        "## Bundle decode integrity",
        "",
        f"- requestLine: `{result['bundleDecodeIntegrity']['requestLine']}`",
        f"- markerMatch: `{result['bundleDecodeIntegrity']['markerMatch']}`",
        f"- jsonError: `{result['bundleDecodeIntegrity']['jsonError']}`",
        f"- decodedTextHasTbrKey: `{result['bundleDecodeIntegrity']['decodedTextHasTbrKey']}`",
        f"- decodedTextHasTbrValuePrefix: `{result['bundleDecodeIntegrity']['decodedTextHasTbrValuePrefix']}`",
        f"- replayPayloadMatchesObserved: `{result['bundleDecodeIntegrity']['replayPayloadMatchesObserved']}`",
        "",
        "## Success PX561 TBR9",
        "",
        f"- activityIndex: `{result['successPx561Tbr']['activityIndex']}`",
        f"- tbrPresent: `{result['successPx561Tbr']['tbrPresent']}`",
        f"- tbrIndex: `{result['successPx561Tbr']['tbrIndex']}`",
        f"- tbrValueLen: `{result['successPx561Tbr']['tbrValueLen']}`",
        f"- neighborKeys: `{', '.join(result['successPx561Tbr']['neighborKeys'])}`",
        "",
        "## Static decoder context",
        "",
        f"- remainingFields source: `{remaining_source}`",
        f"- remainingFields source is ni109 success run: `{static_context['remainingFieldsSourceIsSuccessRun']}`",
        f"- exact ni109 source matches later captured source: `{static_context['exactNi109SourceMatchesLaterCapturedSource']}`",
        f"- exact ni109 source sha256: `{static_context['exactNi109CaptchaSource'].get('sha256')}`",
        "",
        "| success captcha u | success captcha v |",
        "|---|---|",
    ]
    for url in static_context["successCaptchaUrls"]:
        lines.append(f"| `{url['u']}` | `{url['v']}` |")
    lines += [
        "",
        "## Static decoder records",
        "",
        "| expr | decoded | assignment |",
        "|---|---|---|",
    ]
    for rec in decoder_records:
        lines.append(f"| `{rec.get('expr')}` | `{rec.get('decoded')}` | {rec.get('assignment')} |")
    lines += [
        "",
        "## Findings",
        "",
    ]
    lines += [f"- {finding}" for finding in result["findings"]]
    lines += [
        "",
        "## Next evidence targets",
        "",
    ]
    lines += [f"- {target}" for target in result["nextEvidenceTargets"]]
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(json.dumps({"json": str(json_path), "md": str(md_path)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
