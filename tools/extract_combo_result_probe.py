#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


REPO = Path("/Users/chaopenglv/data/me/Gpt-Agreement-Payment")
OUT_DIR = REPO / "output/protocol_reverse/seq5_seq6_combo_probe/extracted"


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description="Extract a seq5/seq6 combo result into the standard probe JSON shape.")
    parser.add_argument("combo_json", type=Path)
    parser.add_argument("--name", choices=["seq5", "seq6"], default="seq5")
    parser.add_argument("--out-dir", type=Path, default=OUT_DIR)
    args = parser.parse_args()

    combo = read_json(args.combo_json)
    row = (combo.get("results") or {}).get(args.name) or {}
    if not row:
        raise RuntimeError(f"missing result {args.name}: {args.combo_json}")
    doc = {
        "startedAt": row.get("startedAt"),
        "sent": True,
        "material": row.get("material"),
        "response": row.get("response"),
        "decoded": row.get("decoded"),
        "error": row.get("error"),
        "sourceCombo": str(args.combo_json),
        "sourceResultName": args.name,
    }
    uuid_value = ((doc.get("material") or {}).get("freshState") or {}).get("uuid")
    if not uuid_value:
        uuid_value = Path(args.combo_json).stem.replace("seq5_seq6_combo_probe_", "")
    args.out_dir.mkdir(parents=True, exist_ok=True)
    out = args.out_dir / f"{Path(args.combo_json).stem}_{args.name}.json"
    out.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "json": str(out),
        "name": args.name,
        "status": (doc.get("response") or {}).get("status"),
        "handlers": (doc.get("decoded") or {}).get("handlers"),
        "successParts": [
            part for part in ((doc.get("decoded") or {}).get("parts") or [])
            if str(part).startswith("oIIoIooo")
        ],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
