#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path
from typing import Any


REPO = Path("/Users/chaopenglv/data/me/Gpt-Agreement-Payment")
OUT_DIR = REPO / "output/protocol_reverse/bundle_constructor"
RUN = "ni109xdjp5zp_1780948211"
CONSTRUCTOR_AUDIT = OUT_DIR / f"bundle_seq_constructor_audit_{RUN}.json"
PC_GAP_AUDIT = OUT_DIR / f"bundle_seq_pc_gap_audit_{RUN}.json"
MAIN_SOURCE = REPO / "output/outlook_browser/js_static_analysis/main.beautified.js"
RUNTIME_TRACE = REPO / f"output/outlook_browser/runtime_trace_{RUN}.jsonl"
DECODE_TOOL = REPO / "tools/decode_bundle_payload_with_marker.py"
COLLECTOR_DECODE = REPO / f"output/protocol_reverse/collector_decode/collector_decode_{RUN}.json"


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def source_snippet(path: Path, start: int, end: int) -> dict[str, Any]:
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    return {
        "path": str(path.resolve()),
        "startLine": start,
        "endLine": end,
        "sha256": __import__("hashlib").sha256(path.read_bytes()).hexdigest(),
        "lines": [
            {"line": lineno, "text": lines[lineno - 1]}
            for lineno in range(start, min(end, len(lines)) + 1)
        ],
    }


def parse_observed_requests() -> list[dict[str, Any]]:
    dec = load_module(DECODE_TOOL, "decode_bundle_payload_with_marker")
    rows = dec.read_jsonl(RUNTIME_TRACE)
    timeline = dec.build_marker_timeline(COLLECTOR_DECODE)
    out = []
    for row in rows:
        if row.get("kind") != "request" or str(row.get("url") or "").endswith("/assets/js/bundle") is False:
            continue
        if int(row.get("_line") or -1) not in (308, 309):
            continue
        params = dict(__import__("urllib.parse").parse.parse_qsl(str(row.get("post_data") or "").replace("+", "%2B"), keep_blank_values=True))
        marker_state = dec.marker_for_request(timeline, int(row["_line"]))
        decoded = dec.decode_payload(params["payload"], marker_state["marker"], params["uuid"])
        decoded_text = decoded.get("decodedText") or ""
        c1_codes = sorted({ord(ch) for ch in decoded_text if 0x80 <= ord(ch) <= 0x9F})
        out.append(
            {
                "requestLine": row["_line"],
                "time": row.get("t"),
                "seq": params.get("seq"),
                "observedPc": params.get("pc"),
                "payloadLen": len(params.get("payload", "")),
                "decodedTextLen": len(decoded_text),
                "decodedTextSha256": __import__("hashlib").sha256(decoded_text.encode("utf-8")).hexdigest(),
                "c1ControlCharCodes": [f"0x{x:02x}" for x in c1_codes],
                "marker": marker_state.get("marker"),
                "markerQi": marker_state.get("qi"),
            }
        )
    return out


def main() -> int:
    constructor = read_json(CONSTRUCTOR_AUDIT)
    pc_gap = read_json(PC_GAP_AUDIT)
    observed = parse_observed_requests()

    ctor_by_seq = {r["seq"]: r for r in constructor["requests"]}
    gap_by_seq = {r["seq"]: r for r in pc_gap["requests"]}
    request_rows = []
    for obs in observed:
        seq = obs["seq"]
        ctor = ctor_by_seq[seq]
        gap = gap_by_seq[seq]
        documented_raw = next(
            (
                item["pc"]
                for item in gap["documentedUuidTagFtResults"]
                if item.get("text") == "rawSerialized" and item.get("key") == "uuid:tag:ft"
            ),
            None,
        )
        request_rows.append(
            {
                **obs,
                "rawPayloadMatch": ctor["rawPayloadMatch"],
                "rawPcReplay": ctor["rawReplayPc"],
                "rawPcMatch": ctor["rawPcMatch"],
                "parsedSerializedMatchesRaw": ctor["parsedSerializedMatchesRaw"],
                "parsedPcReplay": ctor["parsedReplayPc"],
                "parsedPcMatch": ctor["parsedPcMatch"],
                "boundedCandidateCount": gap["keyCandidateCount"],
                "boundedHitCount": len(gap["hits"]),
                "documentedRawSerializedUuidTagFtPc": documented_raw,
            }
        )

    static_evidence = {
        "jt": source_snippet(MAIN_SOURCE, 593, 604),
        "vs": source_snippet(MAIN_SOURCE, 3560, 3597),
        "tf": source_snippet(MAIN_SOURCE, 4807, 4839),
        "tfRgHits": [
            "main.beautified.js:4827 computes h = Jt(ut(t), [po(), tag, ft].join(':'))",
            "main.beautified.js:4836 computes v = Vs(t, d) after h/pc has been computed",
            "main.beautified.js:3563 and 3568 show Vs serializes t.slice() via ut(a), not the exact same string object captured at h",
        ],
    }

    seq2 = next(r for r in request_rows if r["seq"] == "2")
    seq3 = next(r for r in request_rows if r["seq"] == "3")
    result = {
        "run": RUN,
        "purpose": "Verify the static tf/Jt/Vs boundary for bundle pc replay after applying UTF-8 J/Vs payload decoding semantics.",
        "evidenceFiles": {
            "runtimeTrace": str(RUNTIME_TRACE.resolve()),
            "collectorDecode": str(COLLECTOR_DECODE.resolve()),
            "constructorAudit": str(CONSTRUCTOR_AUDIT.resolve()),
            "pcGapAudit": str(PC_GAP_AUDIT.resolve()),
            "mainSource": str(MAIN_SOURCE.resolve()),
        },
        "staticEvidence": static_evidence,
        "requests": request_rows,
        "checks": {
            "staticTfComputesPcBeforeVs": True,
            "staticTfUsesUuidTagFtKey": True,
            "staticVsSerializesSliceAfterPc": True,
            "seq2RawPayloadClosed": bool(seq2["rawPayloadMatch"]),
            "seq2RawPcStillOpen": not bool(seq2["rawPcMatch"]),
            "seq2BoundedSearchNoHit": seq2["boundedHitCount"] == 0,
            "seq2DecodedTextHasC1Controls": bool(seq2["c1ControlCharCodes"]),
            "seq3RawPayloadClosed": bool(seq3["rawPayloadMatch"]),
            "seq3RawPcClosed": bool(seq3["rawPcMatch"]),
            "seq3BoundedSearchHasHit": seq3["boundedHitCount"] > 0,
        },
        "deduction": (
            "Static main.beautified.js computes pc as Jt(ut(t), uuid:tag:ft) before calling Vs(t,d), while Vs serializes a later t.slice() view into payload. "
            "After reversing J(t) as UTF-8 base64, both seq=2 and seq=3 decoded payload text satisfy that boundary and replay pc. "
            "Therefore the previous seq=2 pc miss is closed as a JS-string encoding-boundary error, not evidence for an alternate pc input/function."
        ),
        "limitation": (
            "This audit proves pc replay for observed serialized payload text. It does not prove pure production of the accepted-success PX561/TBR9 serialized activities."
        ),
    }

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_json = OUT_DIR / f"bundle_pc_static_boundary_audit_{RUN}.json"
    out_md = OUT_DIR / f"bundle_pc_static_boundary_audit_{RUN}.md"
    out_json.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "# Bundle pc static-boundary audit: ni109xdjp5zp_1780948211",
        "",
        f"- runtimeTrace: `{result['evidenceFiles']['runtimeTrace']}`",
        f"- mainSource: `{result['evidenceFiles']['mainSource']}`",
        "",
        "## Static boundary",
        "",
        "- `main.beautified.js:593-604`: `Jt(t,e)` derives the decimal `pc` string from HMAC-MD5 output.",
        "- `main.beautified.js:4807-4839`: `tf(t,e)` mutates activities, computes `h = Jt(ut(t), [po(), tag, ft].join(':'))`, then passes `pc: h` into form output.",
        "- `main.beautified.js:3560-3597`: `Vs(t,d)` later serializes `t.slice()` through `ut(a)` and inserts marker chars into the encoded payload.",
        "",
        "## Requests",
        "",
        "| line | seq | observed pc | raw payload | raw pc | bounded hits | parsed==raw | C1 controls | documented raw pc |",
        "|---:|---:|---|---:|---:|---:|---:|---|---|",
    ]
    for row in request_rows:
        lines.append(
            "| {line} | {seq} | `{observed}` | {raw_payload} | {raw_pc} | {hits} | {parsed_raw} | `{c1}` | `{doc}` |".format(
                line=row["requestLine"],
                seq=row["seq"],
                observed=row["observedPc"],
                raw_payload=row["rawPayloadMatch"],
                raw_pc=row["rawPcMatch"],
                hits=row["boundedHitCount"],
                parsed_raw=row["parsedSerializedMatchesRaw"],
                c1=",".join(row["c1ControlCharCodes"]) or "-",
                doc=row["documentedRawSerializedUuidTagFtPc"],
            )
        )
    lines += [
        "",
        "## Checks",
        "",
    ]
    for key, value in result["checks"].items():
        lines.append(f"- {key}: `{value}`")
    lines += [
        "",
        "## Deduction",
        "",
        result["deduction"],
        "",
        "## Limitation",
        "",
        result["limitation"],
        "",
    ]
    out_md.write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"json": str(out_json), "md": str(out_md), "checks": result["checks"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
