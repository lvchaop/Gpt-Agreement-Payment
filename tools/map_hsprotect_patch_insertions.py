#!/usr/bin/env python3
import argparse
import json
from pathlib import Path


MARKERS = [
    "__outlookPatchEmit(kind,data)",
    "__outlookPatchEmit('hsprotect.captcha.zt.enter'",
    "__outlookPatchEmit('hsprotect.captcha.Ot.enter'",
    "__outlookPatchEmit('hsprotect.captcha.worker.new'",
    "__outlookPatchEmit('hsprotect.captcha.worker.message'",
    "__outlookPatchEmit('hsprotect.captcha.worker.error'",
    "__outlookPatchEmit('hsprotect.captcha.pow.hit'",
]


def line_text(path: Path, line: int) -> str:
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    if line < 1 or line > len(lines):
        raise SystemExit(f"{path}: line {line} outside 1..{len(lines)}")
    return lines[line - 1]


def common_prefix(a: str, b: str, start_a: int, start_b: int) -> int:
    n = 0
    while start_a + n < len(a) and start_b + n < len(b) and a[start_a + n] == b[start_b + n]:
        n += 1
    return n


def discover_insertions(source: str, patched: str):
    inserts = []
    si = pi = 0
    while si < len(source) and pi < len(patched):
        if source[si] == patched[pi]:
            si += 1
            pi += 1
            continue
        # find the shortest patched insertion that realigns with the current source suffix.
        found = None
        for end in range(pi + 1, min(len(patched), pi + 20000) + 1):
            if patched[end:end + 40] == source[si:si + 40]:
                found = end
                break
        if found is None:
            raise RuntimeError(f"cannot realign source@{si} patched@{pi}")
        text = patched[pi:found]
        inserts.append({"sourceIndex": si, "patchedIndex": pi, "length": found - pi, "text": text})
        pi = found
    if pi < len(patched):
        inserts.append({"sourceIndex": si, "patchedIndex": pi, "length": len(patched) - pi, "text": patched[pi:]})
    return inserts


def patched_to_source_col(inserts, patched_col: int) -> int:
    # Input/output columns are 1-based.
    pidx = patched_col - 1
    delta = 0
    for ins in inserts:
        p = ins["patchedIndex"]
        l = ins["length"]
        if pidx < p:
            break
        if p <= pidx < p + l:
            return ins["sourceIndex"] + 1
        delta += l
    return pidx - delta + 1


def snip(s: str, col: int, radius: int) -> str:
    idx = max(0, col - 1)
    return s[max(0, idx - radius):min(len(s), idx + radius)]


def main() -> int:
    ap = argparse.ArgumentParser(description="Map HSProtect patched JS columns back to source using insertion discovery.")
    ap.add_argument("--source", required=True)
    ap.add_argument("--patched", required=True)
    ap.add_argument("--line", type=int, required=True)
    ap.add_argument("--col", type=int, action="append", required=True)
    ap.add_argument("--label", required=True)
    ap.add_argument("--radius", type=int, default=1200)
    ap.add_argument("--out-dir", default="output/protocol_reverse/source_offsets")
    args = ap.parse_args()

    source_path = Path(args.source)
    patched_path = Path(args.patched)
    source = line_text(source_path, args.line)
    patched = line_text(patched_path, args.line)
    inserts = discover_insertions(source, patched)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    records = []
    for col in args.col:
        src_col = patched_to_source_col(inserts, col)
        records.append(
            {
                "line": args.line,
                "patchedCol": col,
                "sourceCol": src_col,
                "patchedSnippet": snip(patched, col, args.radius),
                "sourceSnippet": snip(source, src_col, args.radius),
            }
        )

    payload = {
        "source": str(source_path),
        "patched": str(patched_path),
        "line": args.line,
        "sourceLineLength": len(source),
        "patchedLineLength": len(patched),
        "insertions": [
            {
                "sourceIndex": ins["sourceIndex"],
                "patchedIndex": ins["patchedIndex"],
                "length": ins["length"],
                "markerHits": [m for m in MARKERS if m in ins["text"]],
                "preview": ins["text"][:500],
            }
            for ins in inserts
        ],
        "records": records,
    }
    json_path = out_dir / f"patch_insertion_map_{args.label}.json"
    md_path = out_dir / f"patch_insertion_map_{args.label}.md"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        f"# HSProtect patch insertion map: {args.label}",
        "",
        f"- source: `{source_path}`",
        f"- patched: `{patched_path}`",
        f"- line: `{args.line}`",
        f"- source line length: `{len(source)}`",
        f"- patched line length: `{len(patched)}`",
        f"- insertion count: `{len(inserts)}`",
        f"- inserted chars: `{sum(i['length'] for i in inserts)}`",
        f"- json: `{json_path}`",
        "",
        "## Insertions",
        "",
    ]
    for i, ins in enumerate(payload["insertions"]):
        lines.extend(
            [
                f"### insertion {i}",
                f"- sourceIndex: `{ins['sourceIndex']}`",
                f"- patchedIndex: `{ins['patchedIndex']}`",
                f"- length: `{ins['length']}`",
                f"- markerHits: `{ins['markerHits']}`",
                "",
            ]
        )
    for rec in records:
        lines.extend(
            [
                f"## patched `{args.line}:{rec['patchedCol']}` -> source `{args.line}:{rec['sourceCol']}`",
                "",
                "### source snippet",
                "```js",
                rec["sourceSnippet"],
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
