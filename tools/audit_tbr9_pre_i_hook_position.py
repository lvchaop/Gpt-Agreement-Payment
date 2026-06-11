#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


REPO = Path("/Users/chaopenglv/data/me/Gpt-Agreement-Payment")
PATCH_SOURCE = REPO / "CTF-reg/outlook_browser_register.py"
CAPTCHA = REPO / "output/outlook_browser/js_static_analysis/captcha.beautified.js"
TBR9_BOUNDARY = REPO / "output/protocol_reverse/source_offsets/tbr9_tf_payload_boundary_j0t8_audit.json"
OUT_DIR = REPO / "output/protocol_reverse/source_offsets"


def source_lines(path: Path, start: int, end: int) -> list[dict[str, Any]]:
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    return [{"line": no, "text": lines[no - 1]} for no in range(start, end + 1)]


def main() -> int:
    patch = PATCH_SOURCE.read_text(encoding="utf-8", errors="replace")
    captcha = CAPTCHA.read_text(encoding="utf-8", errors="replace")
    boundary = json.loads(TBR9_BOUNDARY.read_text(encoding="utf-8"))

    original_needle = "r[f(c(415,422))]=Ks,i(f(c(439,441)),r))"
    hook_emit = "hsprotect.captcha.pre_i_px561"

    facts = {
        "patchReplacesImmediatePreHandoffNeedle": original_needle in patch,
        "patchInsertsHookAfterKsBeforeHandoff": "r[f(c(415,422))]=Ks,function(){try{var __px561=f(c(439,441))" in patch
        and "r&&r[__tbr]" in patch
        and "}catch(_){}}(),i(f(c(439,441)),r))" in patch
        and hook_emit in patch,
        "staticDirectTbrAssignmentBeforeHookPoint": "r[t(v(-540, -543))] = _s()" in captcha,
        "staticHandoffAfterTailAssignments": "r[f(c(415, 422))] = Ks, i(f(c(439, 441)), r)" in captcha,
    }

    result = {
        "purpose": "Determine where the accepted j0t8 captcha.pre_i_px561 hook samples the PX561 object relative to visible D/Ts assignments.",
        "evidenceFiles": {
            "patchSource": str(PATCH_SOURCE.resolve()),
            "captchaSource": str(CAPTCHA.resolve()),
            "tbr9BoundaryAudit": str(TBR9_BOUNDARY.resolve()),
        },
        "patchSourceLines": source_lines(PATCH_SOURCE, 1448, 1458),
        "captchaSourceLines": source_lines(CAPTCHA, 11073, 11099),
        "facts": facts,
        "runtimeChecks": boundary.get("checks"),
        "deducedPosition": [
            "Visible D/Ts assigns TBR9 via _s() at captcha.beautified.js:11083.",
            "Visible D/Ts then assigns AEAx via Ws.Ng(), succeeded-key via Ws.NQ(n), and tail fields Bzt/OSk/time/state globals.",
            "The patch replaces the immediate handoff substring r[f(c(415,422))]=Ks,i(f(c(439,441)),r)) with r[f(c(415,422))]=Ks,<emit snapshot>,i(f(c(439,441)),r)).",
            "Therefore captcha.pre_i_px561 samples r after the visible tail assignments and immediately before i(PX561,r), not immediately after the _s() assignment.",
        ],
        "checks": {
            "allPositionNeedlesPresent": all(facts.values()),
            "preIHookSawTbr9String": bool(boundary.get("checks", {}).get("preIPx561RowsHaveTbr9String")),
            "ycAndTfPreservedTbr9": bool(boundary.get("checks", {}).get("dollarCYcPx561InputOutputHaveTbr9"))
            and bool(boundary.get("checks", {}).get("acceptedRunHasTfPayloadTbr9Serialized")),
        },
        "conclusion": (
            "The pre_i hook is a final pre-handoff snapshot after visible D/Ts tail assignments. "
            "Accepted j0t8 shows TBR9 is a long string at that point, so the remaining producer window is between the visible _s() assignment and the hook point, or in the semantics of that assignment/object access itself."
        ),
        "boundary": (
            "This does not identify the exact producer. It only fixes the runtime observation point and prevents treating pre_i as an immediate post-_s() sample."
        ),
    }

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_json = OUT_DIR / "tbr9_pre_i_hook_position_audit.json"
    out_md = OUT_DIR / "tbr9_pre_i_hook_position_audit.md"
    out_json.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = ["# TBR9 pre_i hook position audit", "", "## Checks", ""]
    for key, value in result["checks"].items():
        lines.append(f"- {key}: `{value}`")
    lines += ["", "## Deduced position", ""]
    for item in result["deducedPosition"]:
        lines.append(f"- {item}")
    lines += ["", "## Conclusion", "", result["conclusion"], "", "## Boundary", "", result["boundary"], ""]
    out_md.write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"json": str(out_json), "md": str(out_md), "checks": result["checks"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
