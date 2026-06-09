#!/usr/bin/env python3
import argparse
import json
from pathlib import Path


def line_col_for_offset(source: str, offset: int) -> tuple[int, int]:
    if offset < 0:
        offset = 0
    if offset > len(source):
        offset = len(source)
    line = source.count("\n", 0, offset) + 1
    last_nl = source.rfind("\n", 0, offset)
    col = offset + 1 if last_nl < 0 else offset - last_nl
    return line, col


def offset_for_line_col(source: str, line: int, col: int) -> int:
    if line < 1:
        line = 1
    if col < 1:
        col = 1
    pos = 0
    current = 1
    while current < line:
        nxt = source.find("\n", pos)
        if nxt < 0:
            return len(source)
        pos = nxt + 1
        current += 1
    return min(len(source), pos + col - 1)


def compact(s: str, limit: int = 400) -> str:
    s = s.replace("\n", "\\n")
    return s[:limit] + ("..." if len(s) > limit else "")


def main() -> int:
    ap = argparse.ArgumentParser(description="Extract local snippets around stack offsets from HSProtect source files.")
    ap.add_argument("--source", required=True, help="Path to raw JS source")
    ap.add_argument("--label", required=True, help="Artifact label")
    ap.add_argument("--offset", action="append", type=int, required=True, help="Character offset; repeatable")
    ap.add_argument("--line", type=int, help="Line number for column offsets")
    ap.add_argument("--radius", type=int, default=1200, help="Characters before/after offset")
    ap.add_argument("--out-dir", default="output/protocol_reverse/source_offsets")
    args = ap.parse_args()

    source_path = Path(args.source)
    source = source_path.read_text(encoding="utf-8", errors="replace")
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    records = []
    for input_off in args.offset:
        off = offset_for_line_col(source, args.line, input_off) if args.line else input_off
        start = max(0, off - args.radius)
        end = min(len(source), off + args.radius)
        line, col = line_col_for_offset(source, off)
        snippet = source[start:end]
        records.append(
            {
                "source": str(source_path),
                "sourceSize": len(source),
                "inputOffset": input_off,
                "inputLine": args.line,
                "offset": off,
                "line": line,
                "column": col,
                "radius": args.radius,
                "start": start,
                "end": end,
                "beforePreview": compact(source[start:off]),
                "afterPreview": compact(source[off:end]),
                "snippet": snippet,
            }
        )

    json_path = out_dir / f"source_offsets_{args.label}.json"
    md_path = out_dir / f"source_offsets_{args.label}.md"
    json_path.write_text(json.dumps({"records": records}, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        f"# HSProtect source offsets: {args.label}",
        "",
        f"- source: `{source_path}`",
        f"- source size: `{len(source)}` bytes/chars",
        f"- input line: `{args.line}`",
        f"- radius: `{args.radius}`",
        f"- json: `{json_path}`",
        "",
    ]
    for rec in records:
        lines.extend(
            [
                f"## input `{rec['inputLine']}:{rec['inputOffset']}` -> offset {rec['offset']}",
                "",
                f"- line: `{rec['line']}`",
                f"- column: `{rec['column']}`",
                f"- range: `{rec['start']}..{rec['end']}`",
                "",
                "### before preview",
                "",
                "```js",
                rec["beforePreview"],
                "```",
                "",
                "### after preview",
                "",
                "```js",
                rec["afterPreview"],
                "```",
                "",
            ]
        )
    md_path.write_text("\n".join(lines), encoding="utf-8")
    print(md_path)
    print(json_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
