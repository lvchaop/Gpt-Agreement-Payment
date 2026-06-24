#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.util
import json
import time
from pathlib import Path
from typing import Any


REPO = Path("/Users/chaopenglv/data/me/Gpt-Agreement-Payment")
PX_TOOL = REPO / "tools/probe_human_fresh_px561.py"
PROGRESSION_TOOL = REPO / "tools/probe_human_fresh_bundle_progression.py"
COMBO_TOOL = REPO / "tools/probe_human_seq5_seq6_combo.py"
OUT_DIR = REPO / "output/protocol_reverse/first_failure_overlap_probe"


def load_module(path: Path, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def update_state_from_parts(state: dict[str, Any], parts: list[str]) -> dict[str, Any]:
    prog = load_module(PROGRESSION_TOOL, "probe_human_fresh_bundle_progression")
    return prog.update_state_from_parts(state, parts)


def result_state(initial: dict[str, Any], results: dict[str, Any]) -> dict[str, Any]:
    state = json.loads(json.dumps(initial))
    ordered = sorted(
        results.items(),
        key=lambda item: ((item[1] or {}).get("endedAt") or 0),
    )
    for _name, row in ordered:
        parts = [str(part) for part in ((row.get("decoded") or {}).get("parts") or [])]
        update_state_from_parts(state, parts)
    return state


def main() -> int:
    parser = argparse.ArgumentParser(description="Send first-failure seq2 PX561 and seq3 in the observed overlapping h2 shape.")
    parser.add_argument("--fresh-bundle", type=Path, required=True)
    parser.add_argument("--pow-json", type=Path, required=True)
    parser.add_argument("--nq-json", type=Path, required=True)
    parser.add_argument("--ng-nq-json", type=Path, required=True)
    parser.add_argument("--gap-seconds", type=float, default=0.5344)
    parser.add_argument(
        "--h2-body-order",
        choices=["normal", "seq3-body-first", "seq3-response-before-seq2-body"],
        default="normal",
    )
    parser.add_argument("--timeout", type=float, default=35.0)
    parser.add_argument("--include-proxy-authorization", action="store_true")
    parser.add_argument("--header-mode", choices=["safe", "runtime-exact"], default="runtime-exact")
    parser.add_argument("--aeax-source", choices=["template", "offline-ng"], default="template")
    parser.add_argument("--bzt-source", choices=["solve", "template", "value"], default="solve")
    parser.add_argument("--out-dir", type=Path, default=OUT_DIR)
    args = parser.parse_args()

    px = load_module(PX_TOOL, "probe_human_fresh_px561")
    prog = load_module(PROGRESSION_TOOL, "probe_human_fresh_bundle_progression")
    combo = load_module(COMBO_TOOL, "probe_human_seq5_seq6_combo")
    started = time.time()
    bundle = read_json(args.fresh_bundle)
    initial_state = prog.state_from_bundle(bundle)

    seq2 = px.build_material(
        send=True,
        include_proxy_authorization=args.include_proxy_authorization,
        header_mode=args.header_mode,
        aeax_source=args.aeax_source,
        bzt_source=args.bzt_source,
        bzt_value=None,
        template_line=566,
        runtime_line=574,
        seq="2",
        rsc="3",
        state_probe=None,
        fresh_bundle=args.fresh_bundle,
        pow_json=args.pow_json,
        nq_json=args.nq_json,
        ng_nq_json=args.ng_nq_json,
        stack_source="fresh",
        tail_source="fresh",
        inner_uuid_source="fresh",
        non_px_activity_source="fresh",
        payload_uuid_source="fresh",
        pc_uuid_source="payload",
        marker_source="fresh",
        form_outer_source="fresh",
        payload_source="built",
        pc_source="computed",
        body_source="built",
        stack_probe=None,
    )
    seq3 = prog.build_request(
        {"name": "bundle_seq3", "jsLine": 569, "runtimeLine": 578, "seq": "3", "rsc": "4", "activityCount": 1},
        initial_state,
        include_proxy_authorization=args.include_proxy_authorization,
        header_mode=args.header_mode,
        activity_source="fresh",
    )
    raw_results = combo.send_h2_pair(
        combo.load_module(COMBO_TOOL.parent / "probe_human_collector_live.py", "probe_human_collector_live"),
        seq2,
        seq3,
        args.timeout,
        args.gap_seconds,
        {
            "normal": "normal",
            "seq3-body-first": "seq6-body-first",
            "seq3-response-before-seq2-body": "seq6-response-before-seq5-body",
        }[args.h2_body_order],
    )
    results = {"seq2": raw_results.get("seq5"), "seq3": raw_results.get("seq6")}
    final_state = result_state(initial_state, results)
    timing = {
        "seq3StartMinusSeq2Start": ((results["seq3"] or {}).get("startedAt") or 0) - ((results["seq2"] or {}).get("startedAt") or 0),
        "seq3EndMinusSeq2End": ((results["seq3"] or {}).get("endedAt") or 0) - ((results["seq2"] or {}).get("endedAt") or 0),
        "firstResponse": "seq3" if ((results["seq3"] or {}).get("endedAt") or 0) < ((results["seq2"] or {}).get("endedAt") or 0) else "seq2",
    }
    output = {
        "startedAt": started,
        "sent": True,
        "freshBundle": str(args.fresh_bundle),
        "powJson": str(args.pow_json),
        "nqJson": str(args.nq_json),
        "ngNqJson": str(args.ng_nq_json),
        "initialState": initial_state,
        "finalState": final_state,
        "gapSeconds": args.gap_seconds,
        "h2BodyOrder": args.h2_body_order,
        "timing": timing,
        "results": results,
        "checks": {
            "seq2Http200": ((results["seq2"] or {}).get("response") or {}).get("status") == 200,
            "seq3Http200": ((results["seq3"] or {}).get("response") or {}).get("status") == 200,
            "seq3ResponseFirst": timing["firstResponse"] == "seq3",
            "seq2Rejected": "oIIoIooo|-1" in (((results["seq2"] or {}).get("decoded") or {}).get("parts") or []),
            "seq3HasNoSuccessHandler": ((results["seq3"] or {}).get("decoded") or {}).get("hasSuccessHandler") is False,
            "finalStateHasPow": bool(final_state.get("powChallenge")),
        },
    }
    args.out_dir.mkdir(parents=True, exist_ok=True)
    out = args.out_dir / f"first_failure_overlap_probe_{initial_state.get('uuid', 'unknown')}_{int(started)}.json"
    out.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"json": str(out), "checks": output["checks"], "timing": timing}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
