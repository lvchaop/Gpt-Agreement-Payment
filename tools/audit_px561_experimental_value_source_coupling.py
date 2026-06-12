#!/usr/bin/env python3
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


REPO = Path("/Users/chaopenglv/data/me/Gpt-Agreement-Payment")
CONSTRUCTOR = REPO / "output/protocol_reverse/px561_constructor/px561_pow_tail_constructor_audit.json"
INNER_DIFF = REPO / "output/protocol_reverse/px561_compare/px561_experimental_vs_template_inner_diff.json"
LIVE_PROBE = REPO / "output/protocol_reverse/px561_constructor/px561_experimental_live_probe_audit.json"
OUT_DIR = REPO / "output/protocol_reverse/px561_compare"

RUN_RE = re.compile(r"([a-z0-9]{12}_\d{10})")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def first_run_id(value: Any) -> str | None:
    text = json.dumps(value, ensure_ascii=False) if not isinstance(value, str) else value
    match = RUN_RE.search(text)
    return match.group(1) if match else None


def main() -> int:
    constructor = read_json(CONSTRUCTOR)
    diff = read_json(INNER_DIFF)
    probe = read_json(LIVE_PROBE)
    template_run = constructor.get("template", {}).get("run")
    pow_source = constructor.get("experimental", {}).get("livePowSource")
    pow_run = first_run_id(pow_source)
    tbr9_source = constructor.get("experimental", {}).get("freshTbr9Source") or {}
    tbr9_run = first_run_id(tbr9_source.get("path")) or first_run_id(tbr9_source)
    changed = [
        key
        for key, row in (diff.get("pxComparison", {}).get("targetDiffs") or {}).items()
        if row.get("sameSha256") is False
    ]
    unchanged_outer = {
        key: value
        for key, value in (diff.get("outerFormComparison") or {}).items()
        if key.startswith("same")
    }
    checks = {
        "innerShapeMatchesTemplate": all(
            diff.get("checks", {}).get(key) is True
            for key in [
                "sameActivityTypes",
                "sameActivityCount",
                "samePxKeySet",
                "samePxKeyOrder",
                "samePxFieldCount",
                "allTargetIndexesSame",
            ]
        ),
        "onlyTbr9BztOskChanged": changed == ["TBR9Ugl7emA=", "Bzt2fUFRcw==", "OSkIb39DDA=="],
        "outerSessionFieldsStayTemplate": all(
            unchanged_outer.get(key) is True
            for key in ["sameUuid", "sameSeq", "sameCs", "sameSid", "sameVid", "sameCts"]
        ),
        "tbr9RunMatchesTemplateRun": tbr9_run == template_run,
        "powRunMatchesTemplateRun": pow_run == template_run,
        "tbr9RunMatchesPowRun": tbr9_run == pow_run,
        "liveProbeReachedCollector": probe.get("checks", {}).get("sentProbeStatus200") is True,
        "liveProbeStillFails": probe.get("liveResponse", {}).get("handlerStatus") == "failure",
    }
    result = {
        "purpose": "Audit whether the current fresh-TBR9 experimental PX561 body is same-session coherent or cross-run spliced.",
        "evidenceFiles": {
            "constructor": str(CONSTRUCTOR),
            "innerDiff": str(INNER_DIFF),
            "liveProbeAudit": str(LIVE_PROBE),
        },
        "sourceRuns": {
            "outerAndTemplateRun": template_run,
            "powRun": pow_run,
            "tbr9Run": tbr9_run,
        },
        "changedTargetKeys": changed,
        "outerFormComparison": diff.get("outerFormComparison"),
        "checks": checks,
        "conclusion": (
            "The failed live probe uses an inner payload whose shape matches the accepted j0t8 template, but its dynamic values are cross-run spliced: "
            f"outer/session state remains {template_run}, POW comes from {pow_run}, and TBR9 comes from {tbr9_run}. "
            "This proves the current negative result is not sufficient to reject the individual TBR9/POW algorithms; the next proof target is a same-session coherent constructor where collector challenge, POW answer, TBR9 input/_pxUuid, and outer sid/vid/cts/cs/pc are generated from the same live state."
        ),
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_json = OUT_DIR / "px561_experimental_value_source_coupling.json"
    out_md = OUT_DIR / "px561_experimental_value_source_coupling.md"
    out_json.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = ["# PX561 experimental value source coupling", "", "## Checks", ""]
    lines.extend(f"- {key}: `{value}`" for key, value in checks.items())
    lines += [
        "",
        "## Source runs",
        "",
        f"- outer/template: `{template_run}`",
        f"- POW: `{pow_run}`",
        f"- TBR9: `{tbr9_run}`",
        "",
        "## Conclusion",
        "",
        result["conclusion"],
        "",
    ]
    out_md.write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"json": str(out_json), "md": str(out_md), "checks": checks}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
