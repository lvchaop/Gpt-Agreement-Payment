#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


REPO = Path("/Users/chaopenglv/data/me/Gpt-Agreement-Payment")
CAPTCHA = REPO / "output/outlook_browser/js_static_analysis/captcha.beautified.js"
PRE_I_POSITION = REPO / "output/protocol_reverse/source_offsets/tbr9_pre_i_hook_position_audit.json"
OUT_DIR = REPO / "output/protocol_reverse/source_offsets"


def lines(path: Path) -> list[str]:
    return path.read_text(encoding="utf-8", errors="replace").splitlines()


def source_lines(src: list[str], start: int, end: int) -> list[dict[str, Any]]:
    return [{"line": no, "text": src[no - 1]} for no in range(start, end + 1)]


def joined(src: list[str], start: int, end: int) -> str:
    return "\n".join(src[start - 1 : end])


def main() -> int:
    src = lines(CAPTCHA)
    all_text = "\n".join(src)
    pre_i = json.loads(PRE_I_POSITION.read_text(encoding="utf-8"))

    s_body = joined(src, 9638, 9644)
    pn_body = joined(src, 3648, 3658)
    d_setup = joined(src, 11046, 11068)
    micro = joined(src, 11073, 11098)

    facts = {
        "_sReturnsBooleanExpression": "return !(!window" in s_body and "|| !window" in s_body,
        "_sBodyHasNoObjectPropertyWrite": "] =" not in s_body and ".set" not in s_body and "defineProperty" not in s_body,
        "pnCopiesEnumerableOwnProperties": "for (var e in n)" in pn_body and "(r[e] = n[e])" in pn_body,
        "pnBodyHasNoDefineProperty": "defineProperty" not in pn_body,
        "dSetupMergesRWithPn": "r = pn(r," in d_setup,
        "visibleMicroWindowHasDirectTbrAssignment": "r[t(v(-540, -543))] = _s()" in micro,
        "visibleMicroWindowHasAeaxAssignment": "Ws[t(\"Ng\")]()" in micro,
        "visibleMicroWindowHasWsNqAssignment": "Ws[t(\"NQ\")](n)" in micro,
        "visibleMicroWindowHasTailHandoff": "i(f(c(439, 441)), r)" in micro,
        "visibleMicroWindowHasNoDelete": "delete" not in micro,
        "visibleMicroWindowHasNoDefineProperty": "defineProperty" not in micro,
        "visibleMicroWindowHasNoNewProxy": "new Proxy" not in micro,
        "wholeCaptchaHasNoNewProxyLiteral": "new Proxy" not in all_text,
        "wholeCaptchaHasNoDefineSetterLiteral": "__defineSetter__" not in all_text,
    }

    result = {
        "purpose": "Static audit of the visible window between r[TBR9]=_s() and the accepted pre_i PX561 handoff snapshot.",
        "evidenceFiles": {
            "captchaSource": str(CAPTCHA.resolve()),
            "preIPositionAudit": str(PRE_I_POSITION.resolve()),
        },
        "sourceSlices": {
            "_s": source_lines(src, 9638, 9644),
            "pn": source_lines(src, 3648, 3658),
            "DSetup": source_lines(src, 11046, 11068),
            "microWindow": source_lines(src, 11073, 11098),
        },
        "facts": facts,
        "runtimeChecks": pre_i.get("checks"),
        "checks": {
            "allExpectedStaticFactsPresent": all(facts.values()),
            "preIHookPositionFixed": bool(pre_i.get("checks", {}).get("allPositionNeedlesPresent")),
            "acceptedPreISeesTbr9String": bool(pre_i.get("checks", {}).get("preIHookSawTbr9String")),
        },
        "visibleMicroWindowAssignments": [
            "r[TBR9Ugl7emA=] = _s()",
            "r[instantiating] = Rs",
            "r[AEAxBkUsPjQ=] = Ws.Ng()",
            "r[succeeded-decoded-key] = Ws.NQ(n)",
            "r[Bzt2fUFRcw==] = v",
            "r[OSkIb39DDA==] = e",
            "r[time-field] = parseInt(m() - t)",
            "r[state/global fields] = n/os/ws/Ks",
            "i(PX561, r)",
        ],
        "conclusion": (
            "The visible static micro-window does not contain a delete/defineProperty/Proxy-style rewrite and _s() itself is a boolean-returning read expression. "
            "Accepted j0t8 nevertheless sees a long-string TBR9 at the final pre_i snapshot. The remaining producer is therefore not visible as a simple direct statement in this beautified D/Ts window."
        ),
        "boundary": (
            "This does not exclude non-obvious runtime semantics such as obfuscated decoder side effects, object/accessor behavior inherited before D, or side effects inside Ws.Ng/Ws.NQ/Ou/m()/s()/f(). "
            "A finer runtime hook immediately after each visible statement is still required to identify the exact transition."
        ),
    }

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_json = OUT_DIR / "tbr9_micro_window_static_audit.json"
    out_md = OUT_DIR / "tbr9_micro_window_static_audit.md"
    out_json.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    md = ["# TBR9 micro-window static audit", "", "## Checks", ""]
    for key, value in result["checks"].items():
        md.append(f"- {key}: `{value}`")
    md += ["", "## Visible micro-window assignments", ""]
    for item in result["visibleMicroWindowAssignments"]:
        md.append(f"- {item}")
    md += ["", "## Conclusion", "", result["conclusion"], "", "## Boundary", "", result["boundary"], ""]
    out_md.write_text("\n".join(md), encoding="utf-8")

    print(json.dumps({"json": str(out_json), "md": str(out_md), "checks": result["checks"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
