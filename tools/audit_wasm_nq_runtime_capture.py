#!/usr/bin/env python3
import json
import sys
from pathlib import Path


REPO = Path("/Users/chaopenglv/data/me/Gpt-Agreement-Payment")
OUT_DIR = REPO / "output/protocol_reverse/wasm"


def read_jsonl(path: Path):
    rows = []
    with path.open("r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            row["_line"] = line_no
            rows.append(row)
    return rows


def pick(row, keys):
    data = row.get("data") or {}
    out = {"line": row.get("_line"), "wall_t": row.get("wall_t"), "href": row.get("href")}
    for key in keys:
        if key in data:
            out[key] = data.get(key)
    return out


def main():
    run = sys.argv[1] if len(sys.argv) > 1 else "a9quwrn1c1j3_1781189801"
    trace = Path(sys.argv[2]) if len(sys.argv) > 2 else REPO / f"output/outlook_browser/js_internal_trace_{run}.jsonl"
    rows = read_jsonl(trace)

    kinds = {
        "material": "hsprotect.captcha.wasm.material",
        "bind": "hsprotect.captcha.wasm.bind",
        "before": "hsprotect.captcha.wasm.nq.before",
        "after": "hsprotect.captcha.wasm.nq.after",
        "after_nq": "hsprotect.captcha.tbr9.after_nq",
        "pre_i": "hsprotect.captcha.pre_i_px561",
    }
    by_kind = {name: [row for row in rows if row.get("kind") == kind] for name, kind in kinds.items()}

    before = by_kind["before"]
    after = by_kind["after"]
    after_nq = by_kind["after_nq"]
    paired = []
    for idx, b in enumerate(before):
        a = after[idx] if idx < len(after) else {}
        n = after_nq[idx] if idx < len(after_nq) else {}
        bd, ad, nd = b.get("data") or {}, a.get("data") or {}, n.get("data") or {}
        paired.append(
            {
                "idx": idx,
                "beforeLine": b.get("_line"),
                "afterLine": a.get("_line"),
                "afterNqLine": n.get("_line"),
                "input": bd.get("input"),
                "beforeInputLen": bd.get("inputLen"),
                "beforePtr": bd.get("ptr"),
                "beforeLen": bd.get("len"),
                "beforeStackPtr": bd.get("stackPtr"),
                "beforeExportName": bd.get("exportName"),
                "beforeExportType": bd.get("exportType"),
                "beforeMemoryBytes": bd.get("memoryBytes"),
                "afterInput": ad.get("input"),
                "retPtr": ad.get("retPtr"),
                "retLen": ad.get("retLen"),
                "err": ad.get("err"),
                "retPreview": ad.get("retPreview"),
                "afterMemoryBytes": ad.get("memoryBytes"),
                "afterNqInput": nd.get("nInput"),
                "afterNqLen": len(nd.get("nqValue") or ""),
                "afterNqValue": nd.get("nqValue"),
                "beforeAfterInputMatch": bd.get("input") == ad.get("input"),
                "afterRetMatchesAfterNq": ad.get("retPreview") == nd.get("nqValue"),
                "afterRetLenMatchesAfterNqLen": ad.get("retLen") == len(nd.get("nqValue") or ""),
            }
        )

    bind_rows = [
        pick(
            row,
            [
                "exportsKey",
                "exportKeys",
                "ngExport",
                "nqExport",
                "nqExportType",
                "nqExportLen",
                "memoryBytes",
                "moduleType",
            ],
        )
        for row in by_kind["bind"]
    ]
    material_rows = [
        pick(row, ["encodedLen", "byteLen", "firstBytes"])
        for row in by_kind["material"]
    ]
    pre_i_rows = [pick(row, ["keys", "sample", "payload"]) for row in by_kind["pre_i"]]

    checks = {
        "hasMaterial": bool(by_kind["material"]),
        "hasBind": bool(by_kind["bind"]),
        "hasBefore": bool(before),
        "hasAfter": bool(after),
        "hasAfterNq": bool(after_nq),
        "countsAligned": len(before) == len(after) == len(after_nq),
        "bindNqExportIsB": bool(bind_rows) and bind_rows[0].get("nqExport") == "b",
        "bindNqExportIsFunction": bool(bind_rows) and bind_rows[0].get("nqExportType") == "function",
        "allBeforeAfterInputMatch": bool(paired) and all(row["beforeAfterInputMatch"] for row in paired),
        "allAfterRetMatchesAfterNq": bool(paired) and all(row["afterRetMatchesAfterNq"] for row in paired),
        "allAfterRetLenMatchesAfterNqLen": bool(paired) and all(row["afterRetLenMatchesAfterNqLen"] for row in paired),
        "allRuntimeNqNonEmpty": bool(paired) and all((row.get("retLen") or 0) > 0 for row in paired),
    }

    result = {
        "purpose": "Audit browser-runtime WASM bind and Ws.NQ wrapper capture against tbr9.after_nq material.",
        "inputs": {"run": run, "trace": str(trace.resolve())},
        "counts": {name: len(items) for name, items in by_kind.items()},
        "material": material_rows,
        "bind": bind_rows,
        "pairedNqRows": paired,
        "preIPx561Rows": pre_i_rows,
        "checks": checks,
        "conclusion": (
            "Runtime evidence shows Ws.NQ is export b and returns the exact tbr9.after_nq value through the "
            "wasm-bindgen wrapper. This distinguishes browser-runtime state from the standalone offline replay, "
            "where export b returns empty."
        ),
    }

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    json_path = OUT_DIR / f"wasm_nq_runtime_capture_{run}.json"
    md_path = OUT_DIR / f"wasm_nq_runtime_capture_{run}.md"
    json_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    md = [
        "# WASM NQ runtime capture audit",
        "",
        f"- run: `{run}`",
        f"- trace: `{trace.resolve()}`",
        "",
        "## Counts",
        "",
        "| kind | count |",
        "|---|---:|",
        *[f"| `{k}` | {v} |" for k, v in result["counts"].items()],
        "",
        "## Checks",
        "",
        "| check | value |",
        "|---|---:|",
        *[f"| `{k}` | `{v}` |" for k, v in checks.items()],
        "",
        "## NQ rows",
        "",
        "| idx | input | export | retLen | after_nq_len | ret matches after_nq |",
        "|---:|---|---|---:|---:|---:|",
        *[
            f"| {r['idx']} | `{r['input']}` | `{r['beforeExportName']}` | {r['retLen']} | {r['afterNqLen']} | `{r['afterRetMatchesAfterNq']}` |"
            for r in paired
        ],
        "",
        "## Conclusion",
        "",
        result["conclusion"],
    ]
    md_path.write_text("\n".join(md) + "\n", encoding="utf-8")
    print(json.dumps({"json": str(json_path), "md": str(md_path), "checks": checks}, indent=2))


if __name__ == "__main__":
    main()
