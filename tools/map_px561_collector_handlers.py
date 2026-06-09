#!/usr/bin/env python3
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


REPO = Path("/Users/chaopenglv/data/me/Gpt-Agreement-Payment")
MAIN_MIN = REPO / "output/outlook_browser/js_probe/main.min.js"
MAIN_BEAUTIFIED = REPO / "output/outlook_browser/js_static_analysis/main.beautified.js"
COLLECTOR_DECODE = REPO / "output/protocol_reverse/collector_decode/collector_decode_ni109xdjp5zp_1780948211.json"
PX561_COMPARE = REPO / "output/protocol_reverse/px561_compare/px561_compare_success_vs_tf_samples.json"
OUT_DIR = REPO / "output/protocol_reverse/px561_collector_handlers"


REMAINING_KEYS = [
    "Czd6cU5Yfko=",
    "EXFgN1QeZAA=",
    "EXFgN1QeZQU=",
    "Em4jaFcBJlg=",
    "Ew9iCVZkZD4=",
    "HCQtIllLKBE=",
    "KVkYX28zG2o=",
    "P2MOJXoMChA=",
    "TBR9Ugl7emA=",
    "ZR1UGyByUC8=",
    "aRlYHyx2XCU=",
]


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def line_for_offset(source: str, offset: int) -> int:
    return source.count("\n", 0, offset) + 1


def js_parse_int(text: str) -> float:
    match = re.match(r"[+-]?\d+", text)
    return float(int(match.group(0))) if match else float("nan")


def extract_array(source: str, function_name: str) -> list[str]:
    pattern = rf"function {re.escape(function_name)}\(\)\{{var t=\[(.*?)\];return\({re.escape(function_name)}=function"
    match = re.search(pattern, source)
    if not match:
        raise RuntimeError(f"cannot locate {function_name}() array")
    return re.findall(r'"((?:[^"\\]|\\.)*)"', match.group(1))


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
    raise RuntimeError("cannot rotate Dc()")


def rotate_ql(values: list[str]) -> tuple[list[str], int]:
    vals = list(values)
    for rot in range(1000):
        p = lambda idx: js_parse_int(vals[idx - 224])
        expr = (
            -p(263) / 1 * (-p(267) / 2)
            + p(250) / 3
            + p(228) / 4
            + p(266) / 5 * (p(265) / 6)
            + p(274) / 7
            + p(259) / 8 * (p(258) / 9)
            + p(234) / 10 * (-p(251) / 11)
        )
        if expr == 580528:
            return vals, rot
        vals.append(vals.pop(0))
    raise RuntimeError("cannot rotate Ql()")


def dc(rotated: list[str], index: int) -> str:
    return rotated[index - 219]


def ql(rotated: list[str], index: int) -> str:
    return rotated[index - 224]


def find_lines(source: str, needles: list[str]) -> dict[str, list[int]]:
    out: dict[str, list[int]] = {}
    for needle in needles:
        lines: list[int] = []
        start = 0
        while True:
            pos = source.find(needle, start)
            if pos < 0:
                break
            lines.append(line_for_offset(source, pos))
            start = pos + 1
        out[needle] = lines
    return out


def decoded_parts_by_handler() -> dict[str, list[str]]:
    data = json.loads(COLLECTOR_DECODE.read_text(encoding="utf-8"))
    out: dict[str, list[str]] = {}
    for entry in data["decodedEntries"]:
        for part in entry.get("parts", []):
            handler = part.split("|", 1)[0]
            out.setdefault(handler, []).append(part)
    return out


def part_fields(part: str) -> list[str]:
    return part.split("|")[1:]


def exact_handler_field_matches(parts: dict[str, list[str]], value: Any) -> list[dict[str, Any]]:
    sval = str(value)
    matches = []
    for handler, handler_parts in parts.items():
        for part in handler_parts:
            fields = part_fields(part)
            for index, field in enumerate(fields, start=1):
                if field == sval:
                    matches.append({"where": "collectorResponseField", "handler": handler, "fieldIndex": index, "part": part})
    return matches


def success_px561_values() -> dict[str, Any]:
    data = json.loads(PX561_COMPARE.read_text(encoding="utf-8"))
    return data["success"]["activity"]["d"]


def main() -> None:
    main_min = read(MAIN_MIN)
    main_beautified = read(MAIN_BEAUTIFIED)
    dc_rotated, dc_rotations = rotate_dc(extract_array(main_min, "Dc"))
    ql_rotated, ql_rotations = rotate_ql(extract_array(main_min, "Ql"))
    parts = decoded_parts_by_handler()
    px = success_px561_values()

    oii_parts = parts.get("oIIooIoo", [])
    ioo_parts = parts.get("IooIoI", [])
    if not oii_parts:
        raise RuntimeError("no oIIooIoo part found")
    if not ioo_parts:
        raise RuntimeError("no IooIoI part found")

    oii_last = oii_parts[-1].split("|")
    ioo_last = ioo_parts[-1].split("|")

    oii_tl_assignment = {
        "arg1": ql(ql_rotated, 262),
        "arg2": ql(ql_rotated, 275),
        "arg3": ql(ql_rotated, 230),
        "arg4": ql(ql_rotated, 225),
        "arg5": ql(ql_rotated, 240),
    }
    oii_yc_read = {
        "h": dc(dc_rotated, 259),
        "d": dc(dc_rotated, 266),
        "v": dc(dc_rotated, 246),
        "p": dc(dc_rotated, 272),
        "m": dc(dc_rotated, 224),
        "callbackSlot": dc(dc_rotated, 254),
    }
    zc_slots = {
        "bootstrapFunction": dc(dc_rotated, 277),
        "jcCallback": dc(dc_rotated, 220),
        "ocCallback": dc(dc_rotated, 249),
        "kcCallback": dc(dc_rotated, 262),
        "nuCallback": dc(dc_rotated, 242),
    }
    ioo_static = {
        "argCountCheck": ql(ql_rotated, 278),
        "splitMethod": ql(ql_rotated, 227),
        "calls": "Hc(e, n = +(n = ne(u[1], Vl)), r = u[0], a = +a, c)",
    }

    oii_decoded_values = {
        oii_tl_assignment["arg1"]: oii_last[1],
        oii_tl_assignment["arg2"]: oii_last[2],
        oii_tl_assignment["arg3"]: oii_last[3],
        oii_tl_assignment["arg4"]: oii_last[4],
        oii_tl_assignment["arg5"]: oii_last[5],
    }
    geometry_object = {
        "startWidth": int(oii_decoded_values["startWidth"]),
        "startHeight": int(oii_decoded_values["startHeight"]),
        "widthJump": int(oii_decoded_values["widthJump"]),
        "heightJump": int(oii_decoded_values["heightJump"]),
        "hash": oii_decoded_values["hash"],
    }

    ioo_r_parts = ioo_last[4].split("_")
    ioo_hc_inputs = {
        "t": ioo_last[1],
        "e": ioo_last[2],
        "nBeforeDecode": ioo_last[3],
        "rRaw": ioo_last[4],
        "rSplit": ioo_r_parts,
        "a": ioo_last[5],
        "c": ioo_last[6] if len(ioo_last) > 6 else "",
        "observedHashPrefix": ioo_r_parts[0],
        "encodedDelaySource": ioo_r_parts[1] if len(ioo_r_parts) > 1 else None,
    }

    value_matches: dict[str, list[dict[str, Any]]] = {}
    relevant_literals = [str(v) for v in list(geometry_object.values()) + list(ioo_hc_inputs.values()) if not isinstance(v, list)]
    for key in REMAINING_KEYS:
        val = px.get(key)
        matches = exact_handler_field_matches(parts, val)
        if val is not None:
            sval = str(val)
            if len(sval) >= 32:
                for handler, handler_parts in parts.items():
                    for part in handler_parts:
                        if sval in part and not any(m.get("part") == part for m in matches):
                            matches.append({"where": "collectorResponseSubstring", "handler": handler, "part": part})
                for name, source in [("main.beautified.js", main_beautified), ("main.min.js", main_min)]:
                    if sval in source:
                        matches.append({"where": name, "lines": find_lines(source, [sval])[sval][:10]})
        value_matches[key] = matches

    source_lines = find_lines(
        main_beautified,
        [
            "IooIoI: function",
            "oIIooIoo: function",
            "function Hc",
            "function Zc",
            "function Yc",
            "function Ql",
            "function Dc",
        ],
    )

    result = {
        "inputs": {
            "mainMin": str(MAIN_MIN.relative_to(REPO)),
            "mainBeautified": str(MAIN_BEAUTIFIED.relative_to(REPO)),
            "collectorDecode": str(COLLECTOR_DECODE.relative_to(REPO)),
            "px561Compare": str(PX561_COMPARE.relative_to(REPO)),
        },
        "decoders": {
            "Dc/yc": {"rotations": dc_rotations, "indexBase": 219},
            "Ql/Tl": {"rotations": ql_rotations, "indexBase": 224},
        },
        "sourceLines": source_lines,
        "oIIooIoo": {
            "collectorPart": oii_parts[-1],
            "tlAssignments": oii_tl_assignment,
            "ycReads": oii_yc_read,
            "decodedValues": oii_decoded_values,
            "geometryObjectPassedToCallback": geometry_object,
            "callbackSlot": oii_yc_read["callbackSlot"],
        },
        "IooIoI": {
            "collectorPart": ioo_parts[-1],
            "static": ioo_static,
            "hcInputsBeforeRuntimeDecode": ioo_hc_inputs,
            "callsHc": True,
        },
        "ZcSlots": zc_slots,
        "remainingSuccessValues": {key: px.get(key) for key in REMAINING_KEYS},
        "remainingValueMatches": value_matches,
        "evidenceBoundary": [
            "oIIooIoo collector arguments are statically mapped to startWidth/startHeight/widthJump/heightJump/hash by Ql/Tl and Dc/yc decoded tables.",
            "IooIoI is statically proven to call Hc after splitting arg4 on '_' and decoding arg3 via ne(u[1], Vl), but this artifact does not yet decode ne/Vl numerically.",
            "Exact mapping from geometry/hash/Hc values into the 11 remaining PX561 obfuscated keys is only proven where a success PX561 value is found in collector response parts.",
        ],
    }

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    json_path = OUT_DIR / "px561_collector_handlers_ni109.json"
    md_path = OUT_DIR / "px561_collector_handlers_ni109.md"
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "# PX561 collector handler mapping: ni109 success sample",
        "",
        "## inputs",
        "",
    ]
    for k, v in result["inputs"].items():
        lines.append(f"- {k}: `{v}`")
    lines.extend(
        [
            "",
            "## decoder evidence",
            "",
            f"- Dc/yc rotations: `{dc_rotations}`, indexBase: `219`",
            f"- Ql/Tl rotations: `{ql_rotations}`, indexBase: `224`",
            "",
            "## source lines",
            "",
        ]
    )
    for needle, line_numbers in source_lines.items():
        lines.append(f"- `{needle}`: `{line_numbers}`")
    lines.extend(
        [
            "",
            "## oIIooIoo mapping",
            "",
            f"- collector part: `{oii_parts[-1]}`",
            "",
            "| collector arg | decoded key | value | callback object field |",
            "|---|---|---|---|",
        ]
    )
    for arg, key in oii_tl_assignment.items():
        field = key
        lines.append(f"| `{arg}` | `{key}` | `{oii_decoded_values[key]}` | `{field}` |")
    lines.extend(
        [
            "",
            f"- callback slot from `yc(254)`: `{oii_yc_read['callbackSlot']}`",
            "",
            "## IooIoI -> Hc mapping",
            "",
            f"- collector part: `{ioo_parts[-1]}`",
            f"- static call: `{ioo_static['calls']}`",
            f"- r split: `{ioo_hc_inputs['rSplit']}`",
            "",
            "## remaining PX561 values matched in decoded collector response",
            "",
            "| PX561 key | success value | collector/source matches |",
            "|---|---|---:|",
        ]
    )
    for key in REMAINING_KEYS:
        value = px.get(key)
        lines.append(f"| `{key}` | `{value}` | `{len(value_matches[key])}` |")
    lines.extend(
        [
            "",
            "## evidence boundary",
            "",
        ]
    )
    for item in result["evidenceBoundary"]:
        lines.append(f"- {item}")
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(json.dumps({"json": str(json_path), "md": str(md_path)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
