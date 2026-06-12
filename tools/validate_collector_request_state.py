#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import urllib.parse
from pathlib import Path
from typing import Any


REPO = Path("/Users/chaopenglv/data/me/Gpt-Agreement-Payment")


def parse_form(body: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for part in str(body or "").split("&"):
        if not part:
            continue
        key, _, value = part.partition("=")
        out[urllib.parse.unquote_plus(key)] = urllib.parse.unquote_plus(value)
    return out


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return rows
    with path.open("r", encoding="utf-8") as fh:
        for line_no, line in enumerate(fh, 1):
            if not line.strip():
                continue
            row = json.loads(line)
            row["_line"] = line_no
            rows.append(row)
    return rows


def split_handler(part: str) -> tuple[str, list[str]]:
    fields = str(part).split("|")
    return fields[0] if fields else "", fields[1:]


def kl(value: str | None) -> str:
    # main.beautified.js:4797-4802 Kl(t): unescape("%uDB40%uDD" + hex(charCode)).
    # The resulting surrogate pair is U+E0100 + charCode, e.g. "%uDB40%uDD31" -> U+E0131.
    if not value:
        return ""
    return "".join(chr(0xE0100 + ord(ch)) for ch in str(value))


def apply_response_parts(state: dict[str, Any], parts: list[str], line_no: int) -> None:
    state.setdefault("memory", {})
    state.setdefault("cookies", {})
    state.setdefault("sources", {})
    for part_index, part in enumerate(parts):
        key, args = split_handler(part)
        source = {"collectorLine": line_no, "partIndex": part_index, "handler": key, "raw": part}
        if key == "IIoIIo" and args:
            state["memory"]["sid"] = args[0]
            state["sources"]["sid"] = source
        elif key == "oIIoIoII" and args:
            state["memory"]["Jo"] = args[0]
            state["sources"]["Jo"] = source
        elif key == "IoIIII" and args:
            state["memory"]["Yo"] = args[0]
            state["sources"]["Yo"] = source
        elif key == "IooIoo" and args:
            state["cookies"]["_pxvid"] = args[0]
            state["sources"]["_pxvid"] = source
        elif key == "oIIooIIo" and args:
            state["memory"]["Fo"] = args[0]
            state["sources"]["Fo"] = source
        elif key == "IooIoI" and len(args) >= 2:
            state["memory"]["ci"] = args[1]
            state["sources"]["ci"] = source


def expected_fields_for_request(state: dict[str, Any], request_index: int) -> dict[str, dict[str, Any]]:
    memory = state.get("memory") or {}
    cookies = state.get("cookies") or {}
    sources = state.get("sources") or {}
    sid_base = memory.get("sid")
    jo = memory.get("Jo")
    expected: dict[str, dict[str, Any]] = {
        "rsc": {
            "value": str(request_index + 1),
            "source": {"static": "main.beautified.js:8423-8425 Fv(t) appends ++wv; observed first collector request rsc=1"},
        }
    }
    if memory.get("Yo"):
        expected["cs"] = {"value": memory["Yo"], "source": sources.get("Yo")}
    if sid_base or jo:
        expected["sid"] = {"value": (sid_base or "") + kl(jo), "source": {"sid": sources.get("sid"), "Jo": sources.get("Jo")}}
    if cookies.get("_pxvid"):
        expected["vid"] = {"value": cookies["_pxvid"], "source": sources.get("_pxvid")}
    if memory.get("Fo"):
        expected["cts"] = {"value": memory["Fo"], "source": sources.get("Fo")}
    if memory.get("ci"):
        expected["ci"] = {"value": memory["ci"], "source": sources.get("ci")}
    return expected


def extract_session_id(value: Any) -> str | None:
    if not isinstance(value, str) or "session_id=" not in value:
        return None
    parsed = urllib.parse.urlparse(value)
    query = urllib.parse.parse_qs(parsed.query)
    sid = (query.get("session_id") or [None])[0]
    return sid or None


def find_activity_session_id(trace_rows: list[dict[str, Any]], tf_line: int | None) -> dict[str, Any] | None:
    if not tf_line:
        return None
    for row in trace_rows:
        if int(row.get("_line") or 0) != int(tf_line):
            continue
        data = row.get("data") or {}
        for activity in data.get("activities") or []:
            d = activity.get("d") or {}
            for key, value in d.items():
                sid = extract_session_id(value)
                if sid:
                    return {
                        "value": sid,
                        "source": {
                            "traceLine": tf_line,
                            "activityKey": key,
                            "static": "main.beautified.js:2640-2648 Gi(e) extracts _pxParam1; tf activity URL shows iframe session_id feeding p1 in current samples",
                        },
                    }
    return None


def runtime_request_body(runtime_rows: list[dict[str, Any]], request_line: int) -> str:
    for row in runtime_rows:
        if int(row.get("_line") or 0) == int(request_line):
            return str(row.get("post_data") or "")
    return ""


def validate(request_build_path: Path, collector_decode_path: Path) -> dict[str, Any]:
    request_build = json.loads(request_build_path.read_text(encoding="utf-8"))
    collector_decode = json.loads(collector_decode_path.read_text(encoding="utf-8"))
    evidence = request_build.get("evidenceFiles") or {}
    trace_path = Path(request_build.get("tracePath") or evidence.get("jsTrace") or "")
    if trace_path and not trace_path.is_absolute():
        trace_path = REPO / trace_path
    trace_rows = read_jsonl(trace_path) if trace_path else []
    runtime_path = Path(evidence.get("runtimeTrace") or "")
    if runtime_path and not runtime_path.is_absolute():
        runtime_path = REPO / runtime_path
    runtime_rows = read_jsonl(runtime_path) if runtime_path else []
    entries = sorted(collector_decode.get("decodedEntries", []), key=lambda e: int(e.get("lineNo") or 0))
    requests = sorted(request_build.get("rows", []), key=lambda r: int(r.get("requestLine") or 0))

    state: dict[str, Any] = {"memory": {}, "cookies": {}, "sources": {}}
    entry_pos = 0
    rows: list[dict[str, Any]] = []
    for request_index, req in enumerate(requests):
        request_line = int(req.get("requestLine") or 0)
        applied_lines: list[int] = []
        while entry_pos < len(entries) and int(entries[entry_pos].get("lineNo") or 0) < request_line:
            entry = entries[entry_pos]
            line_no = int(entry.get("lineNo") or 0)
            apply_response_parts(state, [str(p) for p in entry.get("parts", [])], line_no)
            applied_lines.append(line_no)
            entry_pos += 1

        observed_body = req.get("observedBody") or runtime_request_body(runtime_rows, request_line)
        observed = parse_form(observed_body)
        expected = expected_fields_for_request(state, request_index)
        material_line = req.get("tfLine") or req.get("materialSourceLine")
        p1 = find_activity_session_id(trace_rows, int(material_line or 0) if material_line else None)
        if p1:
            expected["p1"] = p1
        checks: dict[str, Any] = {}
        for field in ["cs", "sid", "vid", "cts", "ci", "rsc", "p1"]:
            if field in expected:
                expected_value = expected[field]["value"]
                observed_value = observed.get(field)
                checks[field] = {
                    "expected": expected_value,
                    "observed": observed_value,
                    "match": expected_value == observed_value,
                    "source": expected[field].get("source"),
                }
            else:
                checks[field] = {
                    "expected": None,
                    "observed": observed.get(field),
                    "match": observed.get(field) is None,
                    "source": None,
                    "gap": "no independent state producer implemented for this field at this request point",
                }
        rows.append(
            {
                "index": req.get("index"),
                "requestLine": request_line,
                "appliedCollectorLines": applied_lines,
                "state": {
                    "sid": state["memory"].get("sid"),
                    "Jo": state["memory"].get("Jo"),
                    "Yo": state["memory"].get("Yo"),
                    "_pxvid": state["cookies"].get("_pxvid"),
                    "Fo": state["memory"].get("Fo"),
                    "ci": state["memory"].get("ci"),
                },
                "checks": checks,
            }
        )

    return {
        "requestBuildPath": str(request_build_path),
        "collectorDecodePath": str(collector_decode_path),
        "tracePath": str(trace_path) if trace_path else None,
        "rows": rows,
        "summary": {
            "requestCount": len(rows),
            "fieldMatches": sum(
                1
                for row in rows
                for field, check in row["checks"].items()
                if field != "p1" and check.get("match") is True
            ),
            "fieldMismatches": sum(
                1
                for row in rows
                for field, check in row["checks"].items()
                if field != "p1" and check.get("match") is False
            ),
            "p1Matches": sum(
                1 for row in rows if (row["checks"].get("p1") or {}).get("match") is True
            ),
            "p1Gaps": sum(
                1
                for row in rows
                if (row["checks"].get("p1") or {}).get("expected") is None
                and (row["checks"].get("p1") or {}).get("observed") is not None
            ),
        },
    }


def base_name(path: Path) -> str:
    name = path.name.removesuffix(".json")
    return name.replace("collector_request_build_", "")


def write_outputs(result: dict[str, Any], out_dir: Path) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    base = base_name(Path(result["requestBuildPath"]))
    json_path = out_dir / f"collector_request_state_validation_{base}.json"
    md_path = out_dir / f"collector_request_state_validation_{base}.md"
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    lines: list[str] = []
    lines.append(f"# collector request state validation: {base}")
    lines.append("")
    lines.append(f"requestBuild={result['requestBuildPath']}")
    lines.append(f"collectorDecode={result['collectorDecodePath']}")
    lines.append(f"trace={result.get('tracePath') or ''}")
    lines.append("")
    lines.append("## summary")
    for key, value in result["summary"].items():
        lines.append(f"- {key}: {value}")
    lines.append("")
    lines.append("| idx | req line | applied collector lines | cs | sid | vid | cts | ci | rsc | p1 |")
    lines.append("|---:|---:|---|---|---|---|---|---|---|---|")
    for row in result["rows"]:
        def mark(field: str) -> str:
            check = row["checks"][field]
            if check.get("expected") is None and check.get("observed") is not None:
                return "gap"
            return "true" if check.get("match") else "false"

        lines.append(
            f"| {row['index']} | {row['requestLine']} | {','.join(map(str, row['appliedCollectorLines']))} | "
            f"{mark('cs')} | {mark('sid')} | {mark('vid')} | {mark('cts')} | {mark('ci')} | {mark('rsc')} | {mark('p1')} |"
        )
    lines.append("")
    lines.append("## evidence boundary")
    lines.append("- `cs` is derived from decoded handler `IoIIII` -> state `Yo`, static evidence `main.beautified.js:2666-2667` and `4482-4484`.")
    lines.append("- `sid` is derived from decoded handler `IIoIIo` plus `Kl(Jo)`, static evidence `main.beautified.js:1917-1921`, `2675-2677`, `4797-4802`, `4840-4842`.")
    lines.append("- `vid` is derived from decoded handler `IooIoo`, static evidence `main.beautified.js:426-428`, `4404-4411`, `4844`.")
    lines.append("- `cts` is derived from decoded handler `oIIooIIo` -> `Fo`, static evidence `main.beautified.js:1901-1903`, `4523-4525`, `4850`.")
    lines.append("- `ci` is derived from decoded handler `IooIoI` argument 2 -> `ci`, static evidence `main.beautified.js:4494-4510` and request append evidence around `main.beautified.js:4846-4848`.")
    lines.append("- `rsc` is derived from send counter `Fv(t)` appending `++wv`, static evidence `main.beautified.js:8423-8425`.")
    lines.append("- `p1` is derived from the iframe `session_id` present in the matched `tf.payload` activity URL; this matches static producer `Gi(e)` reading `_pxParam1` (`main.beautified.js:2640-2648`) and runtime samples where `p1 == session_id`.")
    md_path.write_text("\n".join(lines), encoding="utf-8")
    return json_path, md_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate collector POST optional fields against prior decoded collector response state.")
    parser.add_argument("request_build_json", type=Path)
    parser.add_argument("collector_decode_json", type=Path)
    parser.add_argument("--out-dir", type=Path, default=REPO / "output/protocol_reverse/collector_request_state")
    args = parser.parse_args()

    result = validate(args.request_build_json, args.collector_decode_json)
    json_path, md_path = write_outputs(result, args.out_dir)
    print(json.dumps({"jsonPath": str(json_path), "mdPath": str(md_path), "summary": result["summary"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
