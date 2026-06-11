#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import urllib.parse
from pathlib import Path
from typing import Any


REPO = Path("/Users/chaopenglv/data/me/Gpt-Agreement-Payment")


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def parse_form_ordered(body: str) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for part in str(body or "").split("&"):
        if not part:
            continue
        key, _, value = part.partition("=")
        # HUMAN payload/pc material can contain literal '+'. Treating '+' as a
        # form-space corrupts base64-like payload bytes before marker replay.
        out.append((urllib.parse.unquote(key), urllib.parse.unquote(value)))
    return out


def encode_form(pairs: list[tuple[str, str]]) -> str:
    return "&".join(f"{urllib.parse.quote(k, safe='')}={urllib.parse.quote(str(v), safe='')}" for k, v in pairs)


def xor_string(value: str, key: int) -> str:
    return "".join(chr(ord(ch) ^ key) for ch in value)


def marker_from_qi(qi: str | None) -> str:
    value = str(qi or "1604064986000")
    return xor_string(base64.b64encode(value.encode()).decode(), 10)


def insertion_positions(chars: str, base_len: int, cu: str) -> list[int]:
    h = xor_string(base64.b64encode(str(cu).encode()).decode(), 10)
    positions: list[int] = []
    max_value = -1
    for p in range(len(chars)):
        m = p // len(h) + 1
        g = p % len(h) if p >= len(h) else p
        max_value = max(max_value, ord(h[g]) * ord(h[m]))
    for idx in range(len(chars)):
        i = idx // len(h) + 1
        e = idx % len(h)
        pos = ord(h[e]) * ord(h[i])
        if pos >= base_len:
            pos = int((pos / max_value) * (base_len - 1))
        while pos in positions:
            pos += 1
        positions.append(pos)
    return sorted(positions)


def remove_inserted(final_text: str, positions: list[int]) -> tuple[str, str]:
    remove = {p - 1 for p in positions}
    marker = []
    base = []
    for idx, ch in enumerate(final_text):
        if idx in remove:
            marker.append(ch)
        else:
            base.append(ch)
    return "".join(marker), "".join(base)


def insert_chars(chars: str, base: str, positions: list[int]) -> str:
    out = []
    start = 0
    for idx, ch in enumerate(chars):
        pos = positions[idx] - idx - 1
        out.append(base[start:pos])
        out.append(ch)
        start = pos
    out.append(base[start:])
    return "".join(out)


def extract_payload_base(payload: str, cu: str, marker_len: int = 24) -> dict[str, str]:
    base_len = len(payload) - marker_len
    if base_len <= 0:
        raise ValueError(f"payload too short for marker_len={marker_len}: len={len(payload)}")
    positions = insertion_positions("X" * marker_len, base_len, cu)
    marker, base = remove_inserted(payload, positions)
    return {"marker": marker, "base": base}


def kl(value: str | None) -> str:
    if not value:
        return ""
    return "".join(chr(0xE0100 + ord(ch)) for ch in str(value))


def live_state_from_probe(path: Path) -> dict[str, Any]:
    probe = read_json(path)
    decoded = probe.get("decoded") or {}
    state: dict[str, Any] = {"sourceProbe": str(path), "handlers": decoded.get("handlers") or []}
    for part in decoded.get("parts") or []:
        fields = str(part).split("|")
        key, args = fields[0], fields[1:]
        if key == "IIoIIo" and args:
            state["sidBase"] = args[0]
        elif key == "oIIoIoII" and args:
            state["Jo"] = args[0]
        elif key == "IooIoo" and args:
            state["vid"] = args[0]
        elif key == "oIIooIIo" and args:
            state["cts"] = args[0]
        elif key == "IoIIII" and args:
            state["cs"] = args[0]
    if state.get("sidBase") or state.get("Jo"):
        state["sid"] = str(state.get("sidBase") or "") + kl(state.get("Jo"))
    state["marker"] = marker_from_qi(state.get("Jo"))
    return state


def build(request_build_path: Path, live_probe_path: Path, index: int) -> dict[str, Any]:
    request_build = read_json(request_build_path)
    rows = request_build.get("rows") or []
    if index < 0 or index >= len(rows):
        raise IndexError(f"index out of range: {index}")
    row = rows[index]
    live = live_state_from_probe(live_probe_path)
    pairs = parse_form_ordered(row.get("rebuiltBody") or row.get("observedBody") or "")
    current = dict(pairs)
    cu = current.get("uuid") or ""
    payload_info = extract_payload_base(current.get("payload") or "", cu, len(row.get("marker") or live["marker"]))
    new_payload = insert_chars(live["marker"], payload_info["base"], insertion_positions(live["marker"], len(payload_info["base"]), cu))

    replacements = {
        "payload": new_payload,
        "cs": live.get("cs"),
        "sid": live.get("sid"),
        "vid": live.get("vid"),
        "cts": live.get("cts"),
    }
    rebuilt_pairs: list[tuple[str, str]] = []
    for key, value in pairs:
        rebuilt_pairs.append((key, str(replacements.get(key) if replacements.get(key) is not None else value)))
    body = encode_form(rebuilt_pairs)
    return {
        "requestBuildPath": str(request_build_path),
        "liveProbePath": str(live_probe_path),
        "index": index,
        "url": row.get("url"),
        "liveState": live,
        "oldMarker": row.get("marker"),
        "newMarker": live["marker"],
        "payloadBaseSha256": hashlib.sha256(payload_info["base"].encode()).hexdigest(),
        "body": body,
        "bodySha256": hashlib.sha256(body.encode()).hexdigest(),
        "bodyLenBytes": len(body.encode()),
        "fieldValues": {k: v for k, v in rebuilt_pairs if k in {"cs", "sid", "vid", "cts", "rsc", "seq", "p1"}},
    }


def write_outputs(result: dict[str, Any], out_dir: Path) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    base = Path(result["requestBuildPath"]).name.removeprefix("collector_request_build_").removesuffix(".json")
    stem = f"collector_live_state_body_{base}_idx{result['index']}"
    json_path = out_dir / f"{stem}.json"
    md_path = out_dir / f"{stem}.md"
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = [
        f"# collector body from live state: {base} idx={result['index']}",
        "",
        f"requestBuild={result['requestBuildPath']}",
        f"liveProbe={result['liveProbePath']}",
        f"url={result['url']}",
        "",
        "## state",
        f"- Jo: {result['liveState'].get('Jo')}",
        f"- sidBase: {result['liveState'].get('sidBase')}",
        f"- sid: {result['liveState'].get('sid')}",
        f"- cs: {result['liveState'].get('cs')}",
        f"- vid: {result['liveState'].get('vid')}",
        f"- cts: {result['liveState'].get('cts')}",
        f"- oldMarker: {result['oldMarker']}",
        f"- newMarker: {result['newMarker']}",
        "",
        "## body",
        f"- bodyLenBytes: {result['bodyLenBytes']}",
        f"- bodySha256: {result['bodySha256']}",
        f"- payloadBaseSha256: {result['payloadBaseSha256']}",
        "",
        "## replaced fields",
    ]
    for key, value in result["fieldValues"].items():
        lines.append(f"- `{key}`: {value}")
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return json_path, md_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a collector POST body using live collector response state from a previous probe.")
    parser.add_argument("request_build", type=Path)
    parser.add_argument("live_probe", type=Path)
    parser.add_argument("--index", type=int, default=1)
    parser.add_argument("--out-dir", type=Path, default=REPO / "output/protocol_reverse/collector_live_state_body")
    args = parser.parse_args()
    result = build(args.request_build, args.live_probe, args.index)
    json_path, md_path = write_outputs(result, args.out_dir)
    print(json.dumps({"json": str(json_path), "md": str(md_path), "bodyLenBytes": result["bodyLenBytes"], "newMarker": result["newMarker"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
