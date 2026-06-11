#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


REPO = Path("/Users/chaopenglv/data/me/Gpt-Agreement-Payment")
POW_RESPONSE_DIR = REPO / "output/protocol_reverse/pow_response"
POW_TO_OSK = REPO / "output/protocol_reverse/pow/pow_to_px561_osk_audit.json"
OSK_STATIC = REPO / "output/protocol_reverse/source_offsets/osk_static_producer_boundary_audit.json"
OUT_DIR = REPO / "output/protocol_reverse/pow"

ACCEPTED_RUNS = [
    "ni109xdjp5zp_1780948211",
    "j0t8van4qyhm_1781119142",
]

LIVE_PROBES = [
    "bc_collector_request_build_hcxwyrtiudbg_1780949301_idx0_1781023909",
]


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def pow_response_path(name: str) -> Path:
    return POW_RESPONSE_DIR / f"pow_response_{name}.json"


def solved_results(doc: dict[str, Any]) -> list[dict[str, Any]]:
    return [r for r in doc.get("results", []) if r and r.get("matchesTarget") is True]


def accepted_rows(pow_to_osk: dict[str, Any], run: str) -> list[dict[str, Any]]:
    for row in pow_to_osk.get("runs", []):
        if row.get("run") == run:
            return [
                item
                for item in row.get("px561Rows", [])
                if item.get("oskIsValid64Hex") is True
            ]
    return []


def main() -> int:
    pow_to_osk = load_json(POW_TO_OSK)
    osk_static = load_json(OSK_STATIC)

    accepted = []
    for run in ACCEPTED_RUNS:
        response_doc = load_json(pow_response_path(run))
        solutions = solved_results(response_doc)
        rows = accepted_rows(pow_to_osk, run)
        matched = []
        for sol in solutions:
            value = sol.get("value")
            matched_rows = [
                row
                for row in rows
                if row.get("oskValue") == value
                and row.get("matchesPowHit") is True
                and row.get("matchesCollectorChallengeHash") is True
            ]
            matched.append(
                {
                    "raw": sol.get("raw"),
                    "value": value,
                    "sha256": sol.get("sha256"),
                    "i": sol.get("i"),
                    "prefixBase": sol.get("prefixBase"),
                    "difficulty": sol.get("difficulty"),
                    "matchedPx561Rows": [
                        {
                            "line": row.get("line"),
                            "seq": row.get("seq"),
                            "activityIndex": row.get("activityIndex"),
                            "bztValue": row.get("bztValue"),
                            "hasTBR9": row.get("hasTBR9"),
                        }
                        for row in matched_rows
                    ],
                    "matchesObservedOsk": bool(matched_rows),
                }
            )
        accepted.append(
            {
                "run": run,
                "powPartCount": response_doc.get("powPartCount"),
                "solvedCount": len(solutions),
                "px561ValidOskRowCount": len(rows),
                "matched": matched,
            }
        )

    live = []
    for name in LIVE_PROBES:
        response_doc = load_json(pow_response_path(name))
        solutions = solved_results(response_doc)
        live.append(
            {
                "probe": name,
                "input": response_doc.get("input"),
                "powPartCount": response_doc.get("powPartCount"),
                "solvedCount": len(solutions),
                "tailInputsFromSolver": [
                    {
                        "OSkIb39DDA==": sol.get("value"),
                        "sha256": sol.get("sha256"),
                        "target": sol.get("target"),
                        "matchesTarget": sol.get("matchesTarget"),
                        "Bzt2fUFRcw==": "measure solve elapsed ms in the pure-protocol solver; static Us/Ts path maps Es to Bzt",
                        "raw": sol.get("raw"),
                    }
                    for sol in solutions
                ],
            }
        )

    checks = {
        "staticOskPropagationClosed": bool(osk_static.get("checks", {}).get("allStaticNeedlesPresent")),
        "runtimeAcceptedOskMatchesPowHit": bool(osk_static.get("checks", {}).get("runtimeAcceptedOskMatchesPowHit")),
        "acceptedSolverOutputsMatchObservedOsk": all(
            item.get("matchesObservedOsk")
            for run in accepted
            for item in run.get("matched", [])
        )
        and all(run.get("solvedCount") == run.get("px561ValidOskRowCount") for run in accepted),
        "acceptedBztObservedNonNull": all(
            row.get("bztValue") is not None
            for run in accepted
            for item in run.get("matched", [])
            for row in item.get("matchedPx561Rows", [])
        ),
        "liveProbePowSolved": all(item.get("solvedCount", 0) > 0 for item in live),
    }

    result = {
        "purpose": "Bridge collector IooIIo POW solver outputs to PX561 tail input fields without guessing TBR9.",
        "evidenceFiles": {
            "powToOskRuntimeAudit": str(POW_TO_OSK.resolve()),
            "oskStaticProducerBoundaryAudit": str(OSK_STATIC.resolve()),
            "powResponseDir": str(POW_RESPONSE_DIR.resolve()),
        },
        "accepted": accepted,
        "live": live,
        "checks": checks,
        "conclusion": (
            "For accepted samples, every solved collector POW value matches an observed PX561 OSkIb39DDA row. "
            "Static evidence maps the POW candidate through Us/Ts into OSk, while Bzt2fUFRcw is the elapsed-time companion value (Es), not a fixed constant. "
            "The live /b/c POW challenge is solvable and yields an OSk candidate for a future pure-protocol bundle constructor, but TBR9 remains unsolved."
        ),
        "boundary": (
            "This audit only proves the OSk/Bzt tail input boundary. It does not generate TBR9Ugl7emA= and does not prove the next live collector request will be accepted."
        ),
    }

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_json = OUT_DIR / "pow_solver_px561_tail_inputs_audit.json"
    out_md = OUT_DIR / "pow_solver_px561_tail_inputs_audit.md"
    out_json.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = ["# POW solver to PX561 tail inputs audit", "", "## Checks", ""]
    for key, value in checks.items():
        lines.append(f"- {key}: `{value}`")
    lines += ["", "## Accepted solver matches"]
    for run in accepted:
        lines.append(f"- {run['run']}: solved={run['solvedCount']} px561ValidOskRows={run['px561ValidOskRowCount']}")
        for item in run["matched"]:
            rows = ", ".join(
                f"line {row['line']} seq {row['seq']} bzt={row['bztValue']} tbr9={row['hasTBR9']}"
                for row in item["matchedPx561Rows"]
            )
            lines.append(f"  - value={item['value']} i={item['i']} matchesObservedOsk={item['matchesObservedOsk']} rows=[{rows}]")
    lines += ["", "## Live solver tail candidates"]
    for probe in live:
        lines.append(f"- {probe['probe']}: solved={probe['solvedCount']}")
        for item in probe["tailInputsFromSolver"]:
            lines.append(f"  - OSkIb39DDA== `{item['OSkIb39DDA==']}`")
            lines.append(f"    Bzt2fUFRcw== `{item['Bzt2fUFRcw==']}`")
    lines += ["", "## Conclusion", "", result["conclusion"], "", "## Boundary", "", result["boundary"], ""]
    out_md.write_text("\n".join(lines), encoding="utf-8")

    print(json.dumps({"json": str(out_json), "md": str(out_md), "checks": checks}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
