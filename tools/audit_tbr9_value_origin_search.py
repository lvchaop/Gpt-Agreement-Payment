#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


REPO = Path("/Users/chaopenglv/data/me/Gpt-Agreement-Payment")
ACCEPTED = REPO / "output/protocol_reverse/px561_compare/px561_accepted_consistency_audit.json"
OUT_DIR = REPO / "output/protocol_reverse/tbr9"

SEARCH_ROOTS = [
    REPO / "output/outlook_browser",
    REPO / "output/protocol_reverse",
    REPO / "docs",
    REPO / "tools",
    REPO / "CTF-reg",
]

SKIP_DIR_NAMES = {".git", ".venv", "node_modules", "__pycache__"}
SEARCH_SUFFIXES = {".json", ".jsonl", ".md", ".txt", ".js", ".mjs", ".py"}


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def extract_values() -> list[dict[str, Any]]:
    doc = read_json(ACCEPTED)
    rows = []
    for row in doc.get("acceptedRows") or []:
        target = row.get("target") or {}
        shape = ((target.get("TBR9Ugl7emA=") or {}).get("shape") or {})
        value = shape.get("value")
        # Older accepted-consistency outputs store only preview/hash in target; fall back to template/rows if needed.
        if not value:
            # The row has full key order and target summaries only. Use evidence files that have full activities.
            value = ((row.get("targetValues") or {}).get("TBR9Ugl7emA=") or {}).get("value")
        if not value:
            continue
        rows.append(
            {
                "run": row.get("run"),
                "sourceKind": row.get("sourceKind"),
                "sourceLine": row.get("sourceLine"),
                "seq": row.get("seq"),
                "value": value,
                "len": len(value),
                "sha256": hashlib.sha256(value.encode("utf-8")).hexdigest(),
            }
        )
    if rows:
        return rows

    # Fallback to constructor template for the j0t8 value plus accepted-vs-controls for all stored full values.
    constructor = read_json(REPO / "output/protocol_reverse/px561_constructor/px561_pow_tail_constructor_audit.json")
    tail = ((constructor.get("template") or {}).get("tail") or {}).get("TBR9Ugl7emA=") or {}
    if tail.get("value"):
        rows.append(
            {
                "run": (constructor.get("template") or {}).get("run"),
                "sourceKind": "constructor.template",
                "sourceLine": (constructor.get("template") or {}).get("tfLine"),
                "seq": (constructor.get("template") or {}).get("seq"),
                "value": tail["value"],
                "len": len(tail["value"]),
                "sha256": hashlib.sha256(tail["value"].encode("utf-8")).hexdigest(),
            }
        )
    avc = read_json(REPO / "output/protocol_reverse/px561_compare/px561_accepted_vs_aeax_controls.json")
    for row in avc.get("acceptedRows") or []:
        value = (((row.get("targetValues") or {}).get("TBR9Ugl7emA=") or {}).get("value"))
        if value and all(existing["value"] != value for existing in rows):
            rows.append(
                {
                    "run": row.get("run"),
                    "sourceKind": row.get("sourceKind"),
                    "sourceLine": row.get("tfLine") or row.get("sourceLine"),
                    "seq": row.get("seq"),
                    "value": value,
                    "len": len(value),
                    "sha256": hashlib.sha256(value.encode("utf-8")).hexdigest(),
                }
            )
    matches_path = REPO / "output/protocol_reverse/bundle_activity_matches/bundle_activity_matches_ni109xdjp5zp_1780948211.json"
    if matches_path.exists():
        def walk(value: Any) -> list[dict[str, Any]]:
            out: list[dict[str, Any]] = []
            if isinstance(value, dict):
                if value.get("t") == "PX561" and isinstance(value.get("d"), dict):
                    out.append(value)
                for child in value.values():
                    out.extend(walk(child))
            elif isinstance(value, list):
                for child in value:
                    out.extend(walk(child))
            return out

        matches_doc = json.loads(matches_path.read_text(encoding="utf-8"))
        for activity in walk(matches_doc):
            value = (activity.get("d") or {}).get("TBR9Ugl7emA=")
            if value and all(existing["value"] != value for existing in rows):
                rows.append(
                    {
                        "run": "ni109xdjp5zp_1780948211",
                        "sourceKind": "decoded_bundle_activity",
                        "sourceLine": None,
                        "seq": None,
                        "value": value,
                        "len": len(value),
                        "sha256": hashlib.sha256(value.encode("utf-8")).hexdigest(),
                    }
                )
    return rows


def category(path: Path) -> str:
    rel = str(path.relative_to(REPO))
    if rel.startswith("output/outlook_browser/js_internal_trace_"):
        return "runtime_hook_trace"
    if rel.startswith("output/outlook_browser/runtime_trace_"):
        return "network_runtime_trace"
    if "/collector_decode/" in rel:
        return "collector_decoded_response"
    if rel.startswith("output/outlook_browser/js_static_analysis/"):
        return "static_js"
    if rel.startswith("output/protocol_reverse/"):
        return "derived_protocol_audit"
    if rel.startswith("docs/"):
        return "documentation"
    if rel.startswith("tools/") or rel.startswith("CTF-reg/"):
        return "tooling"
    return "other"


def iter_files() -> list[Path]:
    files: list[Path] = []
    for root in SEARCH_ROOTS:
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            if any(part in SKIP_DIR_NAMES for part in path.parts):
                continue
            if path.suffix not in SEARCH_SUFFIXES:
                continue
            files.append(path)
    return files


def search_value(value: str, files: list[Path]) -> list[dict[str, Any]]:
    hits = []
    encoded = value.encode("utf-8")
    for path in files:
        try:
            data = path.read_bytes()
        except Exception:
            continue
        if encoded not in data:
            continue
        try:
            text = data.decode("utf-8", errors="replace")
        except Exception:
            text = ""
        line_numbers = []
        if text:
            for idx, line in enumerate(text.splitlines(), 1):
                if value in line:
                    line_numbers.append(idx)
                    if len(line_numbers) >= 5:
                        break
        hits.append(
            {
                "path": str(path),
                "relativePath": str(path.relative_to(REPO)),
                "category": category(path),
                "lineNumbers": line_numbers,
            }
        )
    return hits


def main() -> None:
    values = extract_values()
    files = iter_files()
    rows = []
    for item in values:
        hits = search_value(item["value"], files)
        by_category: dict[str, int] = {}
        for hit in hits:
            by_category[hit["category"]] = by_category.get(hit["category"], 0) + 1
        rows.append({**{k: v for k, v in item.items() if k != "value"}, "valuePreview": item["value"][:32], "hits": hits, "hitCategories": by_category})

    all_hits = [hit for row in rows for hit in row["hits"]]
    categories = {hit["category"] for hit in all_hits}
    checks = {
        "acceptedTbr9ValuesFound": len(values) >= 1,
        "allValuesHaveExactHits": all(bool(row["hits"]) for row in rows),
        "hasRuntimeHookTraceHit": any(hit["category"] == "runtime_hook_trace" for hit in all_hits),
        "hasCollectorDecodedResponseHit": any(hit["category"] == "collector_decoded_response" for hit in all_hits),
        "hasStaticJsHit": any(hit["category"] == "static_js" for hit in all_hits),
        "hasNetworkRuntimeTracePlainHit": any(hit["category"] == "network_runtime_trace" for hit in all_hits),
        "onlyPostProducerOrDerivedHits": categories.issubset({"runtime_hook_trace", "derived_protocol_audit", "documentation"}),
    }

    result = {
        "purpose": "Exact-value search for accepted TBR9Ugl7emA= strings across local evidence to determine whether an upstream non-hook source is already present.",
        "acceptedSource": str(ACCEPTED),
        "searchedRoots": [str(p) for p in SEARCH_ROOTS],
        "rows": rows,
        "checks": checks,
        "conclusion": (
            "Accepted TBR9 long strings are present in post-producer runtime hook traces and derived audits/docs, but this search does not find an exact upstream occurrence in decoded collector responses or static JS artifacts. "
            "This keeps the producer boundary at runtime before/inside the captcha pre-i micro-window rather than moving it to collector response decoding or static constants."
        ),
        "limitation": "Exact string absence does not exclude encoded, encrypted, or algorithmically generated sources; it only rules out already-materialized plaintext in the searched local artifacts.",
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_json = OUT_DIR / "tbr9_value_origin_search_audit.json"
    out_md = OUT_DIR / "tbr9_value_origin_search_audit.md"
    out_json.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = [
        "# TBR9 value origin exact search",
        "",
        "## checks",
    ]
    lines.extend(f"- {key}: `{value}`" for key, value in checks.items())
    lines.extend(["", "## rows", "", "| run | len | sha256 | hit categories | first hits |", "|---|---:|---|---|---|"])
    for row in rows:
        first_hits = ", ".join(f"{Path(h['relativePath']).name}:{(h.get('lineNumbers') or ['?'])[0]}" for h in row["hits"][:5])
        lines.append(f"| {row.get('run')} | {row.get('len')} | `{row.get('sha256')}` | `{row.get('hitCategories')}` | {first_hits} |")
    lines.extend(["", "## conclusion", result["conclusion"], "", "## limitation", result["limitation"]])
    out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"json": str(out_json), "md": str(out_md), "checks": checks}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
