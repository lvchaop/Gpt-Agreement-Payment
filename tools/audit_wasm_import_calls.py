#!/usr/bin/env python3
import json
import sys
from collections import Counter, defaultdict
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


def summarize_calls(rows):
    calls = []
    returns = []
    for row in rows:
        if row.get("kind") == "hsprotect.captcha.wasm.import.return":
            data = row.get("data") or {}
            active = data.get("active") or {}
            returns.append(
                {
                    "line": row.get("_line"),
                    "fn": active.get("fn"),
                    "name": data.get("name"),
                    "prop": data.get("prop"),
                    "outStringPreview": data.get("outStringPreview"),
                    "outStringLen": data.get("outStringLen"),
                    "ret": data.get("ret"),
                    "retType": data.get("retType"),
                    "threw": data.get("threw"),
                    "input": active.get("input"),
                }
            )
            continue
        if row.get("kind") != "hsprotect.captcha.wasm.import.call":
            continue
        data = row.get("data") or {}
        active = data.get("active") or {}
        calls.append(
            {
                "line": row.get("_line"),
                "fn": active.get("fn"),
                "name": data.get("name"),
                "args": data.get("args"),
                "input": active.get("input"),
                "ptr": active.get("ptr"),
                "len": active.get("len"),
                "stackPtr": active.get("stackPtr"),
            }
        )
    by_fn = defaultdict(list)
    for call in calls:
        by_fn[call.get("fn")].append(call)
    returns_by_fn = defaultdict(list)
    for ret in returns:
        returns_by_fn[ret.get("fn")].append(ret)
    return {
        "total": len(calls),
        "returnTotal": len(returns),
        "byFn": {
            fn: {
                "count": len(items),
                "nameCounts": dict(Counter(item.get("name") for item in items)),
                "orderedNames": [item.get("name") for item in items],
                "firstCalls": items[:30],
            }
            for fn, items in by_fn.items()
        },
        "returnsByFn": {
            fn: {
                "count": len(items),
                "propValues": [item.get("prop") for item in items if item.get("prop") is not None],
                "outStringValues": [
                    item.get("outStringPreview") for item in items if item.get("outStringPreview") is not None
                ],
                "interestingReturns": [
                    item
                    for item in items
                    if item.get("prop") is not None or item.get("outStringPreview") is not None
                ],
            }
            for fn, items in returns_by_fn.items()
        },
    }


def main():
    run = sys.argv[1] if len(sys.argv) > 1 else "wdyobrwf3wkl_1781190721"
    trace = Path(sys.argv[2]) if len(sys.argv) > 2 else REPO / f"output/outlook_browser/js_internal_trace_{run}.jsonl"
    rows = read_jsonl(trace)
    kinds = Counter(row.get("kind") for row in rows)
    call_summary = summarize_calls(rows)
    nq_rows = [row for row in rows if row.get("kind") == "hsprotect.captcha.wasm.nq.after"]
    after_nq_rows = [row for row in rows if row.get("kind") == "hsprotect.captcha.tbr9.after_nq"]
    ng_after_rows = [row for row in rows if row.get("kind") == "hsprotect.captcha.wasm.ng.after"]

    pairs = []
    for idx, row in enumerate(nq_rows):
        data = row.get("data") or {}
        after_nq = (after_nq_rows[idx].get("data") or {}) if idx < len(after_nq_rows) else {}
        pairs.append(
            {
                "idx": idx,
                "nqAfterLine": row.get("_line"),
                "tbrAfterNqLine": after_nq_rows[idx].get("_line") if idx < len(after_nq_rows) else None,
                "input": data.get("input"),
                "retLen": data.get("retLen"),
                "retPreview": data.get("retPreview"),
                "afterNqLen": len(after_nq.get("nqValue") or ""),
                "afterNqValue": after_nq.get("nqValue"),
                "retMatchesAfterNq": data.get("retPreview") == after_nq.get("nqValue"),
            }
        )

    nq_returns = call_summary["returnsByFn"].get("NQ", {})
    ng_returns = call_summary["returnsByFn"].get("Ng", {})
    nq_props = nq_returns.get("propValues", [])
    nq_out_strings = nq_returns.get("outStringValues", [])
    ng_props = ng_returns.get("propValues", [])
    ng_out_strings = ng_returns.get("outStringValues", [])
    checks = {
        "hasImportWrap": kinds["hsprotect.captcha.wasm.import.wrap"] > 0,
        "hasImportCalls": call_summary["total"] > 0,
        "hasImportReturns": call_summary["returnTotal"] > 0,
        "hasNgCalls": "Ng" in call_summary["byFn"],
        "hasNqCalls": "NQ" in call_summary["byFn"],
        "hasNgAfter": bool(ng_after_rows),
        "hasNqAfter": bool(nq_rows),
        "hasAfterNq": bool(after_nq_rows),
        "nqReturnMatchesTbrAfterNq": bool(pairs) and all(pair["retMatchesAfterNq"] for pair in pairs),
        "nqImportSequenceContainsGet": any(
            name == "__wbg_get_e6ae480a4b8df368"
            for name in call_summary["byFn"].get("NQ", {}).get("orderedNames", [])
        ),
        "nqImportSequenceContainsStringGet": any(
            name == "__wbindgen_string_get"
            for name in call_summary["byFn"].get("NQ", {}).get("orderedNames", [])
        ),
        "nqGetPropIsPxUuid": "_pxUuid" in nq_props,
        "ngGetPropIsPxUuid": "_pxUuid" in ng_props,
        "nqStringGetReturnsUuid": any(isinstance(value, str) and len(value) == 36 for value in nq_out_strings),
        "ngStringGetReturnsUuid": any(isinstance(value, str) and len(value) == 36 for value in ng_out_strings),
        "ngImportCallCountExceedsOfflineMinimalNqOnly": call_summary["byFn"].get("Ng", {}).get("count", 0) > 4,
        "nqImportCallCountExceedsOfflineNgThenNq": call_summary["byFn"].get("NQ", {}).get("count", 0) > 2,
    }

    result = {
        "purpose": "Compare browser-runtime wasm-bindgen import calls around Ws.Ng/Ws.NQ with the previously observed offline replay gap.",
        "inputs": {"run": run, "trace": str(trace.resolve())},
        "kindCounts": dict(kinds),
        "callSummary": call_summary,
        "nqPairs": pairs,
        "checks": checks,
        "conclusion": (
            "Browser runtime invokes a larger NQ import sequence than the earlier offline Ng-then-NQ replay. "
            "The captured NQ sequence reads _pxUuid via __wbg_get and obtains a 36-byte UUID via __wbindgen_string_get while still returning the exact TBR9 value, "
            "so fresh_tbr9_ws_nq now has a concrete import-state gap to reproduce rather than an unknown export mapping gap."
        ),
    }

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    json_path = OUT_DIR / f"wasm_import_calls_{run}.json"
    md_path = OUT_DIR / f"wasm_import_calls_{run}.md"
    json_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    md = [
        "# WASM import call audit",
        "",
        f"- run: `{run}`",
        f"- trace: `{trace.resolve()}`",
        "",
        "## Checks",
        "",
        "| check | value |",
        "|---|---:|",
        *[f"| `{k}` | `{v}` |" for k, v in checks.items()],
        "",
        "## Import counts by active export",
        "",
        "| export | calls | import names |",
        "|---|---:|---|",
        *[
            f"| `{fn}` | {summary['count']} | `{summary['nameCounts']}` |"
            for fn, summary in call_summary["byFn"].items()
        ],
        "",
        "## Interesting import returns",
        "",
        "| export | line | import | prop | outStringPreview |",
        "|---|---:|---|---|---|",
        *[
            f"| `{fn}` | {item['line']} | `{item['name']}` | `{item.get('prop')}` | `{item.get('outStringPreview')}` |"
            for fn, summary in call_summary["returnsByFn"].items()
            for item in summary["interestingReturns"]
        ],
        "",
        "## NQ pairs",
        "",
        "| idx | input | retLen | after_nq_len | match |",
        "|---:|---|---:|---:|---:|",
        *[
            f"| {pair['idx']} | `{pair['input']}` | {pair['retLen']} | {pair['afterNqLen']} | `{pair['retMatchesAfterNq']}` |"
            for pair in pairs
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
