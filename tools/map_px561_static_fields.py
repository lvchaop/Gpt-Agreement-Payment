#!/usr/bin/env python3
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


REPO = Path("/Users/chaopenglv/data/me/Gpt-Agreement-Payment")
MAIN_MIN = REPO / "output/outlook_browser/js_probe/main.min.js"
MAIN_BEAUTIFIED = REPO / "output/outlook_browser/js_static_analysis/main.beautified.js"
PX561_INPUTS = REPO / "output/protocol_reverse/px561_protocol_inputs/px561_protocol_inputs_ni109_vs_tf.json"
OUT_DIR = REPO / "output/protocol_reverse/px561_static_field_map"


Yc_VAR_VALUES = {
    "i": 268,
    "c": 261,
    "u": 278,
    "s": 261,
    "l": 231,
    "f": 278,
    "d": 231,
    "v": 269,
    "p": 240,
    "m": 282,
    "g": 226,
    "y": 264,
    "b": 284,
    "I": 251,
    "E": 283,
    "S": 280,
    "T": 252,
    "R": 248,
    "A": 279,
    "M": 239,
    "w": 233,
    "x": 270,
}


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def line_for_offset(source: str, offset: int) -> int:
    return source.count("\n", 0, offset) + 1


def snippet(source: str, offset: int, radius: int = 260) -> str:
    start = max(0, offset - radius)
    end = min(len(source), offset + radius)
    return source[start:end]


def extract_dc_array(source: str) -> list[str]:
    match = re.search(r"function Dc\(\)\{var t=\[(.*?)\];return\(Dc=function", source)
    if not match:
        raise RuntimeError("cannot locate main Dc() array")
    return re.findall(r'"((?:[^"\\]|\\.)*)"', match.group(1))


def js_parse_int(text: str) -> float:
    match = re.match(r"[+-]?\d+", text)
    return float(int(match.group(0))) if match else float("nan")


def rotate_dc(values: list[str]) -> tuple[list[str], int]:
    vals = list(values)
    for rot in range(1000):
        p = lambda idx: js_parse_int(vals[idx - 219])
        expr = (
            p(265) / 1 * (p(238) / 2)
            + p(260) / 3 * (p(257) / 4)
            + -p(253) / 5
            + p(229) / 6 * (-p(281) / 7)
            + p(223) / 8 * (p(274) / 9)
            + p(227) / 10 * (-p(234) / 11)
            + p(271) / 12 * (p(232) / 13)
        )
        if expr == 135321:
            return vals, rot
        vals.append(vals.pop(0))
    raise RuntimeError("cannot rotate main Dc() array")


def decode_yc_vars(rotated: list[str]) -> dict[str, str]:
    return {name: rotated[index - 219] for name, index in Yc_VAR_VALUES.items()}


def source_occurrences(source: str, key: str) -> list[dict[str, Any]]:
    out = []
    start = 0
    while True:
        offset = source.find(key, start)
        if offset < 0:
            break
        out.append({"offset": offset, "line": line_for_offset(source, offset), "snippet": snippet(source, offset)})
        start = offset + 1
    return out


def build_yc_mapping(decoded: dict[str, str]) -> dict[str, dict[str, str]]:
    return {
        decoded["p"]: {
            "producer": "Yc PX561 branch",
            "expression": "C[F(p)] = Boolean(true)",
            "meaning": "branch marker when _r() && n === PX561",
        },
        decoded["m"]: {
            "producer": "Yc PX561 branch",
            "expression": "C[F(m)] = navigator[F(g)] && navigator[F(g)][F(y)]",
            "meaning": "navigator.languages.length",
        },
        decoded["b"]: {
            "producer": "Yc PX561 branch",
            "expression": "C[F(b)] = ki()",
            "meaning": "ki() returns localStorage _pxhvd-derived value",
        },
        decoded["I"]: {
            "producer": "Yc PX561 branch",
            "expression": "C[F(I)] = zi()",
            "meaning": "Element.prototype.attachShadow capability boolean",
        },
        decoded["E"]: {
            "producer": "Yc PX561 branch / Xt()",
            "expression": "C[F(E)] = X[F(S)]",
            "meaning": "Xt().cssFromResourceApi",
        },
        decoded["T"]: {
            "producer": "Yc PX561 branch / Xt()",
            "expression": "C[F(T)] = X[F(R)]",
            "meaning": "Xt().imgFromResourceApi",
        },
        decoded["A"]: {
            "producer": "Yc PX561 branch / Xt()",
            "expression": "C[F(A)] = X[F(M)]",
            "meaning": "Xt().fontFromResourceApi",
        },
        decoded["w"]: {
            "producer": "Yc PX561 branch / Xt()",
            "expression": "C[F(w)] = X[F(x)]",
            "meaning": "Xt().cssFromStyleSheets",
        },
    }


def main() -> None:
    main_min = read(MAIN_MIN)
    main_beautified = read(MAIN_BEAUTIFIED)
    px561 = json.loads(PX561_INPUTS.read_text(encoding="utf-8"))
    success_only = [row["key"] for row in px561["fields"] if row["bucket"] == "success_only_unmapped"]
    success_values = {row["key"]: row["successValuePreview"] for row in px561["fields"]}

    dc_raw = extract_dc_array(main_min)
    dc_rotated, rotations = rotate_dc(dc_raw)
    decoded_yc = decode_yc_vars(dc_rotated)
    yc_mapping = build_yc_mapping(decoded_yc)

    records = []
    for key in success_only:
        occurrences = {
            "main.min.js": source_occurrences(main_min, key),
            "main.beautified.js": source_occurrences(main_beautified, key),
        }
        mapping = yc_mapping.get(key)
        status = "static_producer_identified" if mapping else "literal_seen_only" if any(occurrences.values()) else "not_found_literal"
        records.append(
            {
                "key": key,
                "successValuePreview": success_values.get(key),
                "status": status,
                "ycProducer": mapping,
                "occurrences": occurrences,
            }
        )

    result = {
        "inputs": {
            "mainMin": str(MAIN_MIN.relative_to(REPO)),
            "mainBeautified": str(MAIN_BEAUTIFIED.relative_to(REPO)),
            "px561Inputs": str(PX561_INPUTS.relative_to(REPO)),
        },
        "dcDecoder": {
            "rotations": rotations,
            "indexBase": 219,
            "decodedYcVars": decoded_yc,
        },
        "records": records,
        "summary": {
            "total": len(records),
            "staticProducerIdentified": sum(1 for r in records if r["status"] == "static_producer_identified"),
            "literalSeenOnly": sum(1 for r in records if r["status"] == "literal_seen_only"),
            "notFoundLiteral": sum(1 for r in records if r["status"] == "not_found_literal"),
        },
    }

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    json_path = OUT_DIR / "px561_static_field_map_success_only.json"
    md_path = OUT_DIR / "px561_static_field_map_success_only.md"
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "# PX561 static field map for success_only_unmapped keys",
        "",
        "## inputs",
        "",
    ]
    for name, value in result["inputs"].items():
        lines.append(f"- {name}: `{value}`")
    lines.extend(
        [
            "",
            "## Dc/Yc decoder",
            "",
            f"- rotations: `{rotations}`",
            "- indexBase: `219`",
            "",
            "| Yc var | decoded key/value |",
            "|---|---|",
        ]
    )
    for name, value in decoded_yc.items():
        lines.append(f"| `{name}` | `{value}` |")
    lines.extend(
        [
            "",
            "## summary",
            "",
            f"- total: `{result['summary']['total']}`",
            f"- staticProducerIdentified: `{result['summary']['staticProducerIdentified']}`",
            f"- literalSeenOnly: `{result['summary']['literalSeenOnly']}`",
            f"- notFoundLiteral: `{result['summary']['notFoundLiteral']}`",
            "",
            "## records",
            "",
            "| key | status | success value | producer/evidence | literal occurrences |",
            "|---|---|---|---|---:|",
        ]
    )
    for rec in records:
        producer = ""
        if rec["ycProducer"]:
            p = rec["ycProducer"]
            producer = f"{p['producer']}: `{p['expression']}`; {p['meaning']}"
        else:
            producer = "no producer identified in this pass"
        occ_count = sum(len(v) for v in rec["occurrences"].values())
        lines.append(
            f"| `{rec['key']}` | `{rec['status']}` | `{rec['successValuePreview']}` | {producer} | {occ_count} |"
        )
    lines.extend(
        [
            "",
            "## evidence boundary",
            "",
            "- `static_producer_identified` here means a key is decoded from the rotated `Dc()` table and assigned in the `Yc()` PX561 branch.",
            "- `literal_seen_only` means the key appears in static source, but this pass has not mapped the assignment path.",
            "- `not_found_literal` means the key did not appear as a plaintext string in checked main sources; it may be produced by another decoder/table or captcha-side code.",
        ]
    )
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"json": str(json_path), "md": str(md_path), "summary": result["summary"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
