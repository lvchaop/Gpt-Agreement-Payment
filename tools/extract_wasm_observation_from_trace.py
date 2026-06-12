#!/usr/bin/env python3
import argparse
import base64
import json
from pathlib import Path


def iter_rows(path):
    for line_no, line in enumerate(path.read_text(errors="replace").splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except Exception:
            continue
        yield line_no, row


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("trace", type=Path)
    parser.add_argument("--out-dir", type=Path, default=Path("output/protocol_reverse/wasm"))
    parser.add_argument("--label", default="")
    args = parser.parse_args()

    label = args.label or args.trace.stem.replace("js_internal_trace_", "")
    material = None
    random_rows = []
    ng_after = None
    after_ng = None
    nq_before = None
    nq_after = None
    after_nq = None
    bind = None
    for line_no, row in iter_rows(args.trace):
        kind = row.get("kind")
        data = row.get("data") or {}
        if kind == "hsprotect.captcha.wasm.material" and material is None:
            material = {"line": line_no, **data}
        elif kind == "hsprotect.captcha.wasm.bind" and bind is None:
            bind = {"line": line_no, **data}
        elif kind == "hsprotect.captcha.wasm.import.return":
            active = data.get("active") or {}
            if (
                active.get("fn") == "Ng"
                and data.get("name") in {
                    "__wbg_getRandomValues_37fa2ca9e4e07fab",
                    "__wbg_randomFillSync_dc1e9a60c158336d",
                }
            ):
                random_rows.append({"line": line_no, **data})
        elif kind == "hsprotect.captcha.wasm.ng.after":
            ng_after = {"line": line_no, **data}
        elif kind == "hsprotect.captcha.tbr9.after_ng":
            after_ng = {"line": line_no, **data}
        elif kind == "hsprotect.captcha.wasm.nq.before":
            nq_before = {"line": line_no, **data}
        elif kind == "hsprotect.captcha.wasm.nq.after":
            nq_after = {"line": line_no, **data}
        elif kind == "hsprotect.captcha.tbr9.after_nq":
            after_nq = {"line": line_no, **data}

    if not material:
        raise SystemExit("missing hsprotect.captcha.wasm.material")
    encoded = material.get("encoded") or ""
    wasm_bytes = base64.b64decode(encoded + "=" * ((4 - len(encoded) % 4) % 4))
    args.out_dir.mkdir(parents=True, exist_ok=True)
    wasm_path = args.out_dir / f"captcha_{label}.wasm"
    audit_path = args.out_dir / f"captcha_{label}_observation.json"
    wasm_path.write_bytes(wasm_bytes)

    audit = {
        "trace": str(args.trace),
        "wasmPath": str(wasm_path),
        "label": label,
        "material": {**material, "encoded": encoded[:120] + "...", "encodedLen": len(encoded)},
        "bind": bind,
        "randomRows": random_rows,
        "randomHexSeq": [row.get("randomHex") for row in random_rows],
        "ngAfter": ng_after,
        "afterNg": after_ng,
        "nqBefore": nq_before,
        "nqAfter": nq_after,
        "afterNq": after_nq,
        "checks": {
            "hasWasm": len(wasm_bytes) > 0,
            "hasNineRandomHex": len(random_rows) == 9 and all(isinstance(row.get("randomHex"), str) for row in random_rows),
            "ngAfterMatchesAfterNg": (ng_after or {}).get("retPreview") == (after_ng or {}).get("aeaxValue"),
            "nqAfterMatchesAfterNq": (nq_after or {}).get("retPreview") == (after_nq or {}).get("nqValue"),
        },
    }
    audit_path.write_text(json.dumps(audit, indent=2, ensure_ascii=False))
    print(json.dumps({"wasm": str(wasm_path), "audit": str(audit_path), "checks": audit["checks"]}, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
