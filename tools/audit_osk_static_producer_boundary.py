#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


REPO = Path("/Users/chaopenglv/data/me/Gpt-Agreement-Payment")
CAPTCHA = REPO / "output/outlook_browser/js_static_analysis/captcha.beautified.js"
POW_OSK = REPO / "output/protocol_reverse/pow/pow_to_px561_osk_audit.json"
OUT_DIR = REPO / "output/protocol_reverse/source_offsets"


def source_lines(path: Path, start: int, end: int) -> list[dict[str, Any]]:
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    return [{"line": no, "text": lines[no - 1]} for no in range(start, end + 1)]


def contains(text: str, needle: str) -> bool:
    return needle in text


def main() -> int:
    source = CAPTCHA.read_text(encoding="utf-8", errors="replace")
    pow_osk = json.loads(POW_OSK.read_text(encoding="utf-8"))
    facts = {
        "poiComputesCandidateAndChecksHash": {
            "lines": source_lines(CAPTCHA, 8299, 8303),
            "needle": "if (sha256(z) === s) return z",
            "present": contains(source, "if (sha256(z) === s) return z"),
        },
        "workerQsPostsCandidate": {
            "lines": source_lines(CAPTCHA, 8305, 8307),
            "needle": "postMessage(z)",
            "present": contains(source, "postMessage(z);"),
        },
        "workerMessageCallsUs": {
            "lines": source_lines(CAPTCHA, 8541, 8564),
            "needle": "n && (Us(n, f)",
            "present": contains(source, "n && (Us(n, f)"),
        },
        "fallbackPoiCallsUs": {
            "lines": source_lines(CAPTCHA, 8569, 8582),
            "needle": "u && Us(u, f)",
            "present": contains(source, "u && Us(u, f)"),
        },
        "usStoresPsEsMs": {
            "lines": source_lines(CAPTCHA, 8481, 8492),
            "needle": "Ps = r, Es = m() - n, Ms = !0",
            "present": contains(source, "Ps = r, Es = m() - n, Ms = !0"),
        },
        "tsPassesGsEsPs": {
            "lines": source_lines(CAPTCHA, 8585, 8589),
            "needle": "if (Ms) return r(Gs, Es, Ps)",
            "present": contains(source, "if (Ms) return r(Gs, Es, Ps)"),
        },
        "dTsAssignsVAndEToPx561Tail": {
            "lines": source_lines(CAPTCHA, 11073, 11099),
            "needle": "r[f(c(410, 395))] = v, r[f(c(414, 426))] = e",
            "present": contains(source, "r[f(c(410, 395))] = v, r[f(c(414, 426))] = e"),
            "decodedKeys": {
                "v": "Bzt2fUFRcw==",
                "e": "OSkIb39DDA==",
            },
        },
    }
    result = {
        "purpose": "Static-boundary audit for POW result propagation into PX561 OSkIb39DDA.",
        "evidenceFiles": {
            "captchaSource": str(CAPTCHA.resolve()),
            "powToOskRuntimeAudit": str(POW_OSK.resolve()),
        },
        "facts": facts,
        "runtimeChecks": pow_osk.get("checks"),
        "deducedStaticPath": [
            "poi(...) returns candidate z only when sha256(z) equals the collector target hash.",
            "qs(...) posts candidate z from worker via postMessage(z).",
            "worker onmessage reads event.data as n and calls Us(n, f).",
            "fallback non-worker path calls Us(u, f) with poi(...) result u.",
            "Us(r,n) stores Ps=r, Es=m()-n, Ms=true.",
            "Ts(callback) calls callback(Gs, Es, Ps) once Ms is true.",
            "D's Ts callback receives (n,v,e), then assigns v to Bzt2fUFRcw== and e to OSkIb39DDA== before handing r to PX561.",
        ],
        "checks": {
            "allStaticNeedlesPresent": all(item["present"] for item in facts.values()),
            "runtimeAcceptedOskMatchesPowHit": bool(pow_osk.get("checks", {}).get("acceptedRowsMatchPowHit")),
            "runtimeAcceptedOskMatchesCollectorHash": bool(pow_osk.get("checks", {}).get("acceptedRowsMatchCollectorChallengeHash")),
            "controlsNoPowHitNoValidOsk": bool(pow_osk.get("checks", {}).get("controlsHaveNoPowHit"))
            and bool(pow_osk.get("checks", {}).get("controlsHaveNoValidOsk")),
        },
        "conclusion": (
            "Static source shows a complete value path from POW candidate z to Us(Ps) to Ts(..., e=Ps) to PX561 OSkIb39DDA. "
            "Runtime evidence shows accepted OSk values equal pow.hit and satisfy collector hashes, while controls receive challenges but have no pow.hit/valid OSk."
        ),
        "boundary": (
            "This closes the OSk value propagation boundary at static/value level. It does not close TBR9, and it does not by itself make a fresh pure-protocol collector replay succeed."
        ),
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_json = OUT_DIR / "osk_static_producer_boundary_audit.json"
    out_md = OUT_DIR / "osk_static_producer_boundary_audit.md"
    out_json.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = ["# OSk static producer boundary audit", "", "## Checks", ""]
    for key, value in result["checks"].items():
        lines.append(f"- {key}: `{value}`")
    lines += ["", "## Static path"]
    for item in result["deducedStaticPath"]:
        lines.append(f"- {item}")
    lines += ["", "## Conclusion", "", result["conclusion"], "", "## Boundary", "", result["boundary"], ""]
    out_md.write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"json": str(out_json), "md": str(out_md), "checks": result["checks"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
