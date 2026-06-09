#!/usr/bin/env python3
import argparse
import bisect
import difflib
import json
from pathlib import Path


def line_text(path: Path, line: int) -> str:
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    if line < 1 or line > len(lines):
        raise SystemExit(f"{path}: line {line} outside 1..{len(lines)}")
    return lines[line - 1]


def build_map(source: str, patched: str):
    sm = difflib.SequenceMatcher(None, patched, source, autojunk=False)
    starts = []
    entries = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            starts.append(i1 + 1)
            entries.append((i1 + 1, i2, j1 + 1, j2, 0))
        elif tag == "insert":
            starts.append(i1 + 1)
            entries.append((i1 + 1, i2, j1 + 1, j1, 1))
        elif tag == "delete":
            starts.append(i1 + 1)
            entries.append((i1 + 1, i2, j1 + 1, j2, 2))
        else:
            starts.append(i1 + 1)
            entries.append((i1 + 1, i2, j1 + 1, j2, 3))
    return starts, entries


def map_col(starts, entries, patched_col: int):
    idx = bisect.bisect_right(starts, patched_col) - 1
    if idx < 0:
        return None
    p1, p2, s1, s2, kind = entries[idx]
    if kind == 0 and p1 <= patched_col <= p2:
        return {"sourceCol": s1 + (patched_col - p1), "opcode": "equal", "entry": entries[idx]}
    if p1 <= patched_col <= p2:
        return {"sourceCol": s1, "opcode": ["equal", "insert", "delete", "replace"][kind], "entry": entries[idx]}
    return {"sourceCol": s2, "opcode": "between", "entry": entries[idx]}


def snippet(line: str, col: int, radius: int) -> str:
    start = max(0, col - 1 - radius)
    end = min(len(line), col - 1 + radius)
    return line[start:end]


def main() -> int:
    ap = argparse.ArgumentParser(description="Map line-column offsets from patched JS back to source JS.")
    ap.add_argument("--source", required=True)
    ap.add_argument("--patched", required=True)
    ap.add_argument("--line", type=int, required=True)
    ap.add_argument("--col", type=int, action="append", required=True)
    ap.add_argument("--label", required=True)
    ap.add_argument("--radius", type=int, default=1000)
    ap.add_argument("--out-dir", default="output/protocol_reverse/source_offsets")
    args = ap.parse_args()

    source_path = Path(args.source)
    patched_path = Path(args.patched)
    src_line = line_text(source_path, args.line)
    pat_line = line_text(patched_path, args.line)
    starts, entries = build_map(src_line, pat_line)

    records = []
    for col in args.col:
        mapped = map_col(starts, entries, col)
        src_col = mapped["sourceCol"] if mapped else None
        records.append(
            {
                "line": args.line,
                "patchedCol": col,
                "sourceCol": src_col,
                "opcode": mapped["opcode"] if mapped else None,
                "entry": mapped["entry"] if mapped else None,
                "patchedSnippet": snippet(pat_line, col, args.radius),
                "sourceSnippet": snippet(src_line, src_col, args.radius) if src_col else "",
            }
        )

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / f"patched_offset_map_{args.label}.json"
    md_path = out_dir / f"patched_offset_map_{args.label}.md"
    payload = {
        "source": str(source_path),
        "patched": str(patched_path),
        "line": args.line,
        "sourceLineLength": len(src_line),
        "patchedLineLength": len(pat_line),
        "records": records,
    }
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = [
        f"# Patched offset map: {args.label}",
        "",
        f"- source: `{source_path}`",
        f"- patched: `{patched_path}`",
        f"- line: `{args.line}`",
        f"- source line length: `{len(src_line)}`",
        f"- patched line length: `{len(pat_line)}`",
        f"- json: `{json_path}`",
        "",
    ]
    for rec in records:
        lines.extend(
            [
                f"## patched `{args.line}:{rec['patchedCol']}` -> source `{args.line}:{rec['sourceCol']}`",
                "",
                f"- opcode: `{rec['opcode']}`",
                f"- diff entry: `{rec['entry']}`",
                "",
                "### source snippet",
                "",
                "```js",
                rec["sourceSnippet"].replace("\n", "\\n"),
                "```",
                "",
                "### patched snippet",
                "",
                "```js",
                rec["patchedSnippet"].replace("\n", "\\n"),
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
