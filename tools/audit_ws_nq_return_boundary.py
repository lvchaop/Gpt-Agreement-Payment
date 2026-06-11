#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


REPO = Path("/Users/chaopenglv/data/me/Gpt-Agreement-Payment")
CAPTCHA = REPO / "output/outlook_browser/js_static_analysis/captcha.beautified.js"
WASM_AUDIT = REPO / "output/protocol_reverse/source_offsets/captcha_wasm_pow_boundaries_audit.json"
PREYC = REPO / "output/protocol_reverse/source_offsets/px561_preyc_static_reconstruction.json"
OUT_DIR = REPO / "output/protocol_reverse/source_offsets"


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def snippet(path: Path, start: int, end: int) -> list[dict[str, Any]]:
    lines = path.read_text(encoding="utf-8").splitlines()
    return [{"line": n, "text": lines[n - 1]} for n in range(start, end + 1)]


def main() -> None:
    wasm = load_json(WASM_AUDIT)
    preyc = load_json(PREYC)
    ws_snippet = snippet(CAPTCHA, 9428, 9468)
    y_snippet = snippet(CAPTCHA, 9180, 9190)

    preyc_rows = {row["decoded"]: row for row in preyc["preYcDirectRows"]}
    succeeded = preyc_rows["succeeded"]
    tbr = preyc_rows["TBR9Ugl7emA="]

    result = {
        "inputs": {
            "captcha": str(CAPTCHA),
            "wasmAudit": str(WASM_AUDIT),
            "preYc": str(PREYC),
        },
        "staticEvidence": {
            "textDecoderY": y_snippet,
            "wsNgNqWrappers": ws_snippet,
        },
        "preYcRows": {
            "succeeded": succeeded,
            "TBR9Ugl7emA=": tbr,
        },
        "wasmCorrections": wasm["corrections"],
        "findings": [
            "Ws.Ng() and Ws.NQ(n) wrappers both return y(ptr,len), where y is TextDecoder.decode over WASM memory.",
            "Therefore current static glue evidence does not support treating Ws.NQ(n) as an object returned for Yc flattening.",
            "The pre-Yc direct key decoded as succeeded is assigned Ws.NQ(n), but final success PX561.d does not contain key succeeded.",
            "Because Ws.NQ(n) is string-returning at the JS glue boundary, Yc would copy succeeded as a primitive string if the key reached Yc unchanged.",
            "TBR9Ugl7emA= remains unexplained by both direct _s() and Ws.NQ object-flatten hypotheses.",
        ],
        "eliminatedHypotheses": [
            "TBR9 final long string is direct _s() output.",
            "TBR9 is produced by Yc flattening an object directly returned by Ws.NQ(n), based on current JS glue evidence.",
        ],
        "remainingHypothesesNeedingEvidence": [
            "The local decoder for key t(v(-541,-541)) -> succeeded is context/version-sensitive or wrong for the actually executed bundle.",
            "The key succeeded is deleted/rewritten before Yc or before final serialization.",
            "The final fyNOZ/TBR9 group is inserted by a different producer path not yet decoded.",
            "The bundle decode/inverse around Vs marker insertion is mis-attributing final keys or order.",
        ],
        "nextEvidenceTargets": [
            "Capture or statically recover the exact return strings of Ws.Ng() and Ws.NQ(n) for the success source version.",
            "Audit the decoder context for t(v(-541,-541)) and neighboring keys against the actually executed captcha source.",
            "Search for a producer of fyNOZTpPQF4= and the 127-byte TBR9 value outside the direct D/Ts assignment block.",
        ],
    }

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    json_path = OUT_DIR / "ws_nq_return_boundary_audit.json"
    md_path = OUT_DIR / "ws_nq_return_boundary_audit.md"
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    md: list[str] = [
        "# Ws.NQ return boundary audit",
        "",
        "## Inputs",
        "",
    ]
    for name, path in result["inputs"].items():
        md.append(f"- {name}: `{path}`")
    md += [
        "",
        "## Pre-Yc rows",
        "",
        "| decoded key | value expr | final present | final index | final value kind |",
        "|---|---|---:|---:|---|",
    ]
    for key in ["succeeded", "TBR9Ugl7emA="]:
        row = result["preYcRows"][key]
        md.append(
            f"| `{key}` | `{row['valueExpr']}` | `{row['finalPresent']}` | "
            f"`{row['finalIndex']}` | `{row['finalValueKind']}` |"
        )
    md += ["", "## Findings", ""]
    for finding in result["findings"]:
        md.append(f"- {finding}")
    md += ["", "## Eliminated hypotheses", ""]
    for item in result["eliminatedHypotheses"]:
        md.append(f"- {item}")
    md += ["", "## Remaining hypotheses needing evidence", ""]
    for item in result["remainingHypothesesNeedingEvidence"]:
        md.append(f"- {item}")
    md += ["", "## Next evidence targets", ""]
    for item in result["nextEvidenceTargets"]:
        md.append(f"- {item}")
    md_path.write_text("\n".join(md) + "\n", encoding="utf-8")

    print(json.dumps({"json": str(json_path), "md": str(md_path)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
