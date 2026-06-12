#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


REPO = Path("/Users/chaopenglv/data/me/Gpt-Agreement-Payment")
OUT_DIR = REPO / "output/protocol_reverse/fresh_px561_state"


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def update_state_from_parts(state: dict[str, Any], parts: list[str]) -> dict[str, Any]:
    for part in parts:
        fields = str(part).split("|")
        if fields[:2] == ["IoooII", "_px3"] and len(fields) >= 4:
            state["px3"] = fields[3]
        elif fields[:2] == ["oIIoIIoo", "_pxde"] and len(fields) >= 4:
            state["pxde"] = fields[3]
        elif fields and fields[0] == "IIoIoI" and len(fields) >= 2:
            state["zo"] = fields[1]
        elif fields and fields[0] == "oIIoIoII" and len(fields) >= 2:
            state["jo"] = fields[1]
        elif fields and fields[0] == "ooooII" and len(fields) >= 2:
            state["qo"] = fields[1]
        elif fields and fields[0] == "oIIoIoIo" and len(fields) >= 2:
            state["gl"] = fields[1]
        elif fields and fields[0] == "IoIIII" and len(fields) >= 2:
            state["cs"] = fields[1]
        elif fields and fields[0] == "IooIoI" and len(fields) >= 3:
            state["ci"] = fields[2]
        elif fields and fields[0] == "IooIIo":
            state["powChallenge"] = part
    return state


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a progression-style finalState document from a PX561 probe response.")
    parser.add_argument("probe", type=Path)
    parser.add_argument("--out-dir", type=Path, default=OUT_DIR)
    args = parser.parse_args()
    probe = read_json(args.probe)
    state = dict((probe.get("material") or {}).get("freshState") or {})
    before = {key: state.get(key) for key in ["jo", "ci", "cs", "px3", "pxde", "powChallenge"]}
    parts = [str(p) for p in (probe.get("decoded") or {}).get("parts") or []]
    update_state_from_parts(state, parts)
    after = {key: state.get(key) for key in ["jo", "ci", "cs", "px3", "pxde", "powChallenge"]}
    result = {
        "purpose": "Carry collector response state from a rejected PX561 probe into a later probe.",
        "sourceProbe": str(args.probe.resolve()),
        "sourceResponse": {
            "status": (probe.get("response") or {}).get("status"),
            "handlers": (probe.get("decoded") or {}).get("handlers"),
            "hasSuccessHandler": (probe.get("decoded") or {}).get("hasSuccessHandler"),
        },
        "before": before,
        "after": after,
        "finalState": state,
        "checks": {
            "sourceRejected": (probe.get("decoded") or {}).get("hasSuccessHandler") is False,
            "hasPx3": bool(state.get("px3")),
            "hasPxde": bool(state.get("pxde")),
            "px3Changed": before.get("px3") != after.get("px3"),
            "pxdeChanged": before.get("pxde") != after.get("pxde"),
        },
    }
    args.out_dir.mkdir(parents=True, exist_ok=True)
    out = args.out_dir / f"{args.probe.stem}_state_after_response.json"
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"json": str(out), "checks": result["checks"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
