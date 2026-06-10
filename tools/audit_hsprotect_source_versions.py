#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any


REPO = Path("/Users/chaopenglv/data/me/Gpt-Agreement-Payment")
OUT_DIR = REPO / "output/protocol_reverse/source_offsets"

RUNS = [
    "ni109xdjp5zp_1780948211",
    "hcxwyrtiudbg_1780949301",
    "whsnxy8ag5ji_1781017142",
    "i294e72kliud_1781017380",
]

LOCAL_JS = [
    REPO / "output/outlook_browser/js_probe/main.min.js",
    REPO / "output/outlook_browser/js_probe/captcha.js",
    REPO / "output/outlook_browser/js_static_analysis/main.beautified.js",
    REPO / "output/outlook_browser/js_static_analysis/captcha.beautified.js",
    REPO / "output/outlook_browser/js_static_analysis/har_main.beautified.js",
    REPO / "output/outlook_browser/js_static_analysis/har_captcha.beautified.js",
]


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return rows
    with path.open("r", encoding="utf-8", errors="replace") as fh:
        for line_no, line in enumerate(fh, 1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except Exception:
                continue
            row["_line"] = line_no
            rows.append(row)
    return rows


def sha256(path: Path) -> str | None:
    if not path.exists() or not path.is_file():
        return None
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def local_sources() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for path in LOCAL_JS:
        out.append({
            "path": str(path),
            "exists": path.exists(),
            "size": path.stat().st_size if path.exists() else None,
            "sha256": sha256(path),
        })
    patch_dir = REPO / "output/outlook_browser/hsprotect_js_patch"
    for meta_path in sorted(patch_dir.glob("*.json")):
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        source_path = Path(meta.get("source_path") or "")
        out.append({
            "path": str(source_path),
            "meta": str(meta_path),
            "exists": source_path.exists(),
            "url": meta.get("url"),
            "declaredSha256": meta.get("sha256"),
            "size": source_path.stat().st_size if source_path.exists() else None,
            "sha256": sha256(source_path),
        })
    return out


def extract_stack_urls(text: str) -> list[str]:
    urls = []
    for match in re.finditer(r"https://(?:client|captcha)\.hsprotect\.net/[^\s\"\\]+", text):
        urls.append(match.group(0))
    return urls


def summarize_run(run: str) -> dict[str, Any]:
    runtime = REPO / f"output/outlook_browser/runtime_trace_{run}.jsonl"
    js_trace = REPO / f"output/outlook_browser/js_internal_trace_{run}.jsonl"
    rows = read_jsonl(runtime)
    js_rows = read_jsonl(js_trace)

    js_network = []
    for row in rows:
        url = str(row.get("url") or "")
        if "client.hsprotect.net/PXzC5j78di/main.min.js" not in url and "captcha.hsprotect.net/PXzC5j78di/captcha.js" not in url:
            continue
        headers = row.get("headers") or {}
        js_network.append({
            "line": row["_line"],
            "kind": row.get("kind"),
            "status": row.get("status"),
            "method": row.get("method"),
            "url": url,
            "etag": headers.get("etag"),
            "lastModified": headers.get("last-modified"),
            "contentLength": headers.get("content-length") or headers.get("x-goog-stored-content-length"),
            "contentEncoding": headers.get("content-encoding"),
            "cacheControl": headers.get("cache-control"),
        })

    stack_urls: list[dict[str, Any]] = []
    for row in rows + js_rows:
        text = json.dumps(row, ensure_ascii=False)
        for url in extract_stack_urls(text):
            stack_urls.append({"line": row.get("_line"), "kind": row.get("kind"), "url": url})

    unique_stack_urls = []
    seen = set()
    for item in stack_urls:
        key = item["url"]
        if key in seen:
            continue
        seen.add(key)
        unique_stack_urls.append(item)

    return {
        "run": run,
        "runtimeTrace": str(runtime),
        "jsTrace": str(js_trace),
        "runtimeExists": runtime.exists(),
        "jsTraceExists": js_trace.exists(),
        "jsNetwork": js_network,
        "uniqueStackUrls": unique_stack_urls[:80],
        "stackUrlCount": len(unique_stack_urls),
    }


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    result = {
        "runs": [summarize_run(run) for run in RUNS],
        "localSources": local_sources(),
        "findings": [],
    }

    success = result["runs"][0]
    success_etags = {
        item["url"].split("?")[0]: item.get("etag")
        for item in success["jsNetwork"]
        if item.get("kind") == "response"
    }
    patch_sources = [s for s in result["localSources"] if "hsprotect_js_patch" in s["path"] and s.get("exists")]
    if success_etags:
        result["findings"].append(
            "success runtime trace records response etags for hsprotect JS; local saved source files only carry sha256/url metadata, not response etag, so exact byte identity to success is not proven by current artifacts."
        )
    if patch_sources:
        result["findings"].append(
            "patched/source JS artifacts are from later 1781017xxx runs; their URLs do not match success uuid/vid 49cc4a30/4b399270, although app path is the same."
        )

    json_path = OUT_DIR / "hsprotect_source_version_audit.json"
    md_path = OUT_DIR / "hsprotect_source_version_audit.md"
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "# hsprotect source version audit",
        "",
        "## runs",
        "| run | runtime | js trace | JS network responses | unique stack urls |",
        "|---|---|---|---:|---:|",
    ]
    for run in result["runs"]:
        responses = [x for x in run["jsNetwork"] if x.get("kind") == "response"]
        lines.append(
            f"| `{run['run']}` | {run['runtimeExists']} | {run['jsTraceExists']} | {len(responses)} | {run['stackUrlCount']} |"
        )
    lines += ["", "## JS response evidence"]
    for run in result["runs"]:
        lines.append(f"### {run['run']}")
        for item in run["jsNetwork"]:
            if item.get("kind") != "response":
                continue
            lines.append(
                f"- line {item['line']} status={item.get('status')} etag={item.get('etag')} "
                f"len={item.get('contentLength')} enc={item.get('contentEncoding')} url={item.get('url')}"
            )
    lines += ["", "## local source artifacts"]
    lines.append("| path | size | sha256 | url/meta |")
    lines.append("|---|---:|---|---|")
    for src in result["localSources"]:
        lines.append(
            f"| `{src['path']}` | {src.get('size') or ''} | `{src.get('sha256') or ''}` | "
            f"{src.get('url') or src.get('meta') or ''} |"
        )
    lines += ["", "## findings"]
    for finding in result["findings"]:
        lines.append(f"- {finding}")
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"json": str(json_path), "md": str(md_path)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
