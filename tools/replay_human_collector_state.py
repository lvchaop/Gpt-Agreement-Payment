#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


REPO = Path("/Users/chaopenglv/data/me/Gpt-Agreement-Payment")


@dataclass
class HumanState:
    cookies: dict[str, dict[str, Any]] = field(default_factory=dict)
    local_storage: dict[str, Any] = field(default_factory=dict)
    memory: dict[str, Any] = field(default_factory=dict)
    scores: list[dict[str, Any]] = field(default_factory=list)
    success_events: list[dict[str, Any]] = field(default_factory=list)
    unknown_events: list[dict[str, Any]] = field(default_factory=list)


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path or not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as fh:
        for line_no, line in enumerate(fh, 1):
            if not line.strip():
                continue
            row = json.loads(line)
            row["_line"] = line_no
            rows.append(row)
    return rows


def base_name(path: Path) -> str:
    name = path.name.removesuffix(".jsonl").removesuffix(".json")
    for prefix in ("collector_decode_", "js_internal_trace_"):
        if name.startswith(prefix):
            return name[len(prefix):]
    return name


def split_part(part: str) -> tuple[str, list[str]]:
    fields = str(part).split("|")
    return fields[0] if fields else "", fields[1:]


def set_cookie(state: HumanState, *, name: str, ttl: str | None, value: str, domain: bool | str | None, source: dict[str, Any]) -> None:
    state.cookies[name] = {
        "value": value,
        "ttl": ttl,
        "domain": domain,
        "source": source,
    }


def apply_handler(state: HumanState, *, line_no: int, part_index: int, part: str) -> dict[str, Any]:
    key, args = split_part(part)
    source = {"collectorLine": line_no, "partIndex": part_index, "raw": part}
    event: dict[str, Any] = {
        **source,
        "handler": key,
        "args": args,
        "effect": "unknown",
        "evidence": [],
    }

    if key == "IoooII" and len(args) >= 3:
        # main.beautified.js: Xl.IoooII -> Zl(t,e,n,a,o).
        # Zl emits di.trigger("bake", n, t, e, o) and writes cookie t=n.
        name, ttl, value = args[0], args[1], args[2]
        domain = args[3] if len(args) > 3 else None
        set_cookie(state, name=name, ttl=ttl, value=value, domain=domain, source=source)
        event.update(
            {
                "effect": "set_cookie",
                "name": name,
                "ttl": ttl,
                "value": value,
                "domain": domain,
                "semantic": "bake",
                "evidence": [
                    "main.beautified.js:4358 Xl.IoooII maps to Zl",
                    "main.beautified.js:4717 function Zl",
                    "main.beautified.js:4721 Zl calls di.trigger(Tl(270)=bake) and Wn(t,e,n,a)",
                ],
            }
        )
    elif key == "oIIoIIoo" and len(args) >= 3:
        # Xl.oIIoIIoo writes enrichment cookie/token and emits enrich.
        name, ttl, value = args[0], args[1], args[2]
        domain = args[3] if len(args) > 3 else None
        set_cookie(state, name=name, ttl=ttl, value=value, domain=domain, source=source)
        event.update(
            {
                "effect": "set_cookie",
                "name": name,
                "ttl": ttl,
                "value": value,
                "domain": domain,
                "semantic": "enrich",
                "evidence": [
                    "main.beautified.js:4487 Xl.oIIoIIoo",
                    "main.beautified.js:4496 oIIoIIoo calls Wn(t,e,n,a)",
                    "main.beautified.js:4496 oIIoIIoo calls di.trigger(Tl(238)=enrich)",
                ],
            }
        )
    elif key == "IooIoo" and args:
        # Xl.IooIoo stores vid, sets mt via Rt, hashed storage via Oi, and localStorage ui.
        value = args[0]
        ttl = args[1] if len(args) > 1 else None
        domain = args[2] if len(args) > 2 else None
        set_cookie(state, name="_pxvid", ttl=ttl, value=value, domain=domain, source=source)
        state.local_storage["_pxvid"] = {"value": value, "ttl": ttl, "source": source}
        event.update(
            {
                "effect": "set_cookie_and_storage",
                "name": "_pxvid",
                "ttl": ttl,
                "value": value,
                "domain": domain,
                "semantic": "vid",
                "evidence": [
                    "main.beautified.js:4399 Xl.IooIoo",
                    "main.beautified.js:4402 IooIoo calls Rt(t), Oi(t), Wn(ui,e,t,n), er(ui,{ttl,val})",
                    "main.beautified.js:426 Rt stores mt",
                    "main.beautified.js:1913 Oi stores hashed vid",
                ],
            }
        )
    elif key == "IIoIIo" and args:
        state.memory["sid"] = {"value": args[0], "source": source}
        event.update(
            {
                "effect": "memory",
                "name": "sid",
                "value": args[0],
                "evidence": [
                    "main.beautified.js:4359 Xl.IIoIIo maps to Ll",
                    "main.beautified.js:4688 function Ll",
                ],
            }
        )
    elif key == "IIoIoI" and args:
        state.memory["Zo"] = {"value": args[0], "extra": args[1:], "source": source}
        event.update(
            {
                "effect": "memory",
                "name": "Zo",
                "value": args[0],
                "evidence": [
                    "main.beautified.js:4484 Xl.IIoIoI maps to Dl",
                    "main.beautified.js:4692 function Dl(t,e){Zo=t,jo=e}",
                ],
            }
        )
    elif key == "oIIoIoII" and args:
        value = args[0]
        state.memory["Jo"] = {"value": value, "zo": int(value) // 1000 if value.isdigit() else None, "source": source}
        event.update(
            {
                "effect": "memory",
                "name": "Jo",
                "value": value,
                "semantic": "Qi marker seed",
                "evidence": [
                    "main.beautified.js:4487 Xl.oIIoIoII maps to Yl",
                    "main.beautified.js:4701 function Yl(t){Jo=t,zo=Math.floor(parseInt(Jo)/1e3)}",
                    "main.beautified.js:2675 function Qi(){return Jo}",
                ],
            }
        )
    elif key == "oIIoIoIo" and args:
        state.memory["Gl"] = {"value": args[0], "source": source}
        event.update(
            {
                "effect": "memory",
                "name": "Gl",
                "value": args[0],
                "evidence": [
                    "main.beautified.js:4488 Xl.oIIoIoIo maps to Gl",
                    "main.beautified.js:4672 function Gl",
                ],
            }
        )
    elif key == "ooooII" and args:
        state.memory["Qo"] = {"value": args[0], "source": source}
        event.update(
            {
                "effect": "memory",
                "name": "Qo",
                "value": args[0],
                "evidence": ["main.beautified.js:4489 Xl.ooooII sets Qo"],
            }
        )
    elif key == "IoIIII" and args:
        state.memory["Yo"] = {"value": args[0], "source": source}
        event.update(
            {
                "effect": "memory",
                "name": "Yo",
                "value": args[0],
                "evidence": ["main.beautified.js:4483 Xl.IoIIII sets Yo"],
            }
        )
    elif key == "oIIooIIo" and args:
        value = args[0]
        domain = args[1] if len(args) > 1 else None
        set_cookie(state, name="_pxhd_candidate", ttl=None, value=value, domain=domain, source=source)
        event.update(
            {
                "effect": "set_cookie",
                "name": "_pxhd_candidate",
                "value": value,
                "domain": domain,
                "semantic": "Bi hidden id",
                "evidence": [
                    "main.beautified.js:4490 Xl.oIIooIIo calls Bi(t,e)",
                    "main.beautified.js:1901 function Bi(t,e,n){... Wn(li,null,t,e) ...}",
                ],
            }
        )
    elif key == "IoIIIo" and args:
        state.memory["Ns"] = {"value": args[0], "source": source}
        event.update(
            {
                "effect": "memory",
                "name": "Ns",
                "value": args[0],
                "semantic": "collector uuid/current marker",
                "evidence": [
                    "main.beautified.js:4526 Xl.IoIIIo",
                    "main.beautified.js:4527 IoIIIo assigns Ns=t",
                    "main.beautified.js:4832 tf meta uses cu: po()",
                ],
            }
        )
    elif key == "oIIooIoo" and len(args) >= 5:
        state.memory["dimension_jump"] = {
            "startWidth": args[0],
            "startHeight": args[1],
            "widthJump": args[2],
            "heightJump": args[3],
            "hash": args[4],
            "source": source,
        }
        event.update(
            {
                "effect": "memory",
                "name": "dimension_jump",
                "value": "|".join(args[:5]),
                "evidence": [
                    "main.beautified.js:4589 Xl.oIIooIoo",
                    "main.beautified.js:4618-4624 builds {startWidth,startHeight,widthJump,heightJump,hash}",
                    "main.beautified.js:4625-4627 invokes challenge callback with dimension jump object",
                ],
            }
        )
    elif key == "IoIoIo" and len(args) >= 2:
        row = {"name": args[0], "value": args[1], "args": args, "source": source}
        state.scores.append(row)
        event.update(
            {
                "effect": "score",
                "name": args[0],
                "value": args[1],
                "evidence": ["main.beautified.js:4406 Xl.IoIoIo calls di.trigger(...)"],
            }
        )
    elif key == "IIooII" and len(args) >= 3:
        state.local_storage[args[0]] = {"ttl": args[1], "value": args[2], "source": source}
        event.update(
            {
                "effect": "local_storage",
                "name": args[0],
                "ttl": args[1],
                "value": args[2],
                "evidence": ["main.beautified.js:4375 Xl.IIooII calls lr(true,{ff:t,ttl:e,val:n})"],
            }
        )
    elif key == "oIooII" and args:
        state.memory["oIooII"] = {"value": args[0], "source": source}
        event.update(
            {
                "effect": "memory",
                "name": "oIooII",
                "value": args[0],
                "evidence": ["main.beautified.js:4383 Xl.oIooII parses comma list and calls lr(false,...)"],
            }
        )
    elif key == "IooIIo" and args:
        state.memory["pow_result"] = {"args": args, "source": source}
        event.update(
            {
                "effect": "pow_result",
                "name": "pow_result",
                "value": "|".join(args),
                "evidence": ["main.beautified.js:4498 Xl.IooIIo handles POW callback when first arg is 1"],
            }
        )
    elif key == "IooIoI" and args:
        state.memory["captcha_work"] = {"args": args, "source": source}
        event.update(
            {
                "effect": "captcha_work",
                "name": "captcha_work",
                "value": "|".join(args),
                "evidence": ["main.beautified.js:4510 Xl.IooIoI calls Hc(...) when first arg is 1"],
            }
        )
    elif key == "oIIoIooo":
        success = args[0] if args else ""
        state.success_events.append({"value": success, "source": source})
        event.update(
            {
                "effect": "challenge_success" if success == "0" else "challenge_terminal",
                "name": "challenge_success",
                "value": success,
                "evidence": [
                    "main.beautified.js:4528 Xl.oIIoIooo",
                    "main.beautified.js:4535 oIIoIooo calls Wc(... [t].concat(r))",
                    "main.beautified.js:2937 Wc invokes registered captcha callback",
                ],
            }
        )
    else:
        state.unknown_events.append(event)
    return event


def collect_parent_messages(trace_path: Path | None) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in read_jsonl(trace_path) if trace_path else []:
        if row.get("kind") != "window.message.recv":
            continue
        data = row.get("data") or {}
        payload = data.get("data")
        msg: Any = payload
        if isinstance(payload, str):
            try:
                msg = json.loads(payload)
            except json.JSONDecodeError:
                pass
        if isinstance(msg, dict) and msg.get("type") in {"cookie", "succeeded", "failed", "block"}:
            out.append(
                {
                    "line": row.get("_line"),
                    "wall_t": row.get("wall_t"),
                    "perf_t": row.get("perf_t"),
                    "href": row.get("href"),
                    "eventOrigin": data.get("eventOrigin"),
                    "type": msg.get("type"),
                    "name": msg.get("name"),
                    "value": msg.get("value"),
                    "expires": msg.get("expires"),
                    "raw": msg,
                }
            )
    return out


def correlate_parent(events: list[dict[str, Any]], parent: list[dict[str, Any]]) -> list[dict[str, Any]]:
    correlations: list[dict[str, Any]] = []
    used: set[int] = set()
    for ev in events:
        if ev.get("effect") not in {"set_cookie", "set_cookie_and_storage", "challenge_success"}:
            continue
        target_type = "succeeded" if ev.get("effect") == "challenge_success" and ev.get("value") == "0" else "cookie"
        target_name = ev.get("name")
        for idx, msg in enumerate(parent):
            if idx in used:
                continue
            if msg.get("type") != target_type:
                continue
            if target_type == "cookie":
                if msg.get("name") != target_name:
                    continue
                if msg.get("value") != ev.get("value"):
                    continue
            used.add(idx)
            correlations.append(
                {
                    "collectorLine": ev.get("collectorLine"),
                    "partIndex": ev.get("partIndex"),
                    "handler": ev.get("handler"),
                    "effect": ev.get("effect"),
                    "name": target_name,
                    "parentLine": msg.get("line"),
                    "parentType": msg.get("type"),
                    "valueMatch": target_type == "succeeded" or msg.get("value") == ev.get("value"),
                }
            )
            break
    return correlations


def replay(decode_path: Path, trace_path: Path | None) -> dict[str, Any]:
    doc = json.loads(decode_path.read_text(encoding="utf-8"))
    state = HumanState()
    events: list[dict[str, Any]] = []
    for entry in doc.get("decodedEntries", []):
        for part_index, part in enumerate(entry.get("parts", [])):
            events.append(
                apply_handler(
                    state,
                    line_no=int(entry.get("lineNo") or 0),
                    part_index=part_index,
                    part=str(part),
                )
            )
    parent = collect_parent_messages(trace_path)
    correlations = correlate_parent(events, parent)
    return {
        "decodePath": str(decode_path),
        "tracePath": str(trace_path) if trace_path else None,
        "counts": {
            "decodedEntries": len(doc.get("decodedEntries", [])),
            "handlerEvents": len(events),
            "cookies": len(state.cookies),
            "localStorage": len(state.local_storage),
            "memory": len(state.memory),
            "scores": len(state.scores),
            "successEvents": len(state.success_events),
            "unknownEvents": len(state.unknown_events),
            "parentMessages": len(parent),
            "parentCorrelations": len(correlations),
        },
        "finalState": {
            "cookies": state.cookies,
            "localStorage": state.local_storage,
            "memory": state.memory,
            "scores": state.scores,
            "successEvents": state.success_events,
        },
        "events": events,
        "parentMessages": parent,
        "parentCorrelations": correlations,
    }


def write_outputs(result: dict[str, Any], out_dir: Path) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    base = base_name(Path(result["decodePath"]))
    json_path = out_dir / f"collector_state_{base}.json"
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    lines: list[str] = []
    lines.append(f"# HUMAN collector state replay: {base}")
    lines.append("")
    lines.append(f"decodePath={result['decodePath']}")
    lines.append(f"tracePath={result['tracePath'] or ''}")
    lines.append("")
    lines.append("## counts")
    for key, value in result["counts"].items():
        lines.append(f"- {key}: {value}")
    lines.append("")
    lines.append("## final cookies")
    lines.append("| name | ttl | valueLen | handler line |")
    lines.append("|---|---:|---:|---:|")
    for name, row in sorted(result["finalState"]["cookies"].items()):
        source = row.get("source") or {}
        lines.append(f"| {name} | {row.get('ttl')} | {len(str(row.get('value') or ''))} | {source.get('collectorLine')} |")
    lines.append("")
    lines.append("## success events")
    for row in result["finalState"]["successEvents"]:
        source = row.get("source") or {}
        lines.append(f"- value={row.get('value')} collectorLine={source.get('collectorLine')} part={source.get('partIndex')}")
    lines.append("")
    lines.append("## parent correlations")
    lines.append("| collector line | part | handler | effect | name | parent line | parent type | value match |")
    lines.append("|---:|---:|---|---|---|---:|---|---|")
    for row in result["parentCorrelations"]:
        lines.append(
            f"| {row.get('collectorLine')} | {row.get('partIndex')} | {row.get('handler')} | {row.get('effect')} | {row.get('name')} | {row.get('parentLine')} | {row.get('parentType')} | {row.get('valueMatch')} |"
        )
    lines.append("")
    lines.append("## handler events")
    lines.append("| collector line | part | handler | effect | name | valueLen |")
    lines.append("|---:|---:|---|---|---|---:|")
    for row in result["events"]:
        value = str(row.get("value") or "")
        lines.append(
            f"| {row.get('collectorLine')} | {row.get('partIndex')} | {row.get('handler')} | {row.get('effect')} | {row.get('name') or ''} | {len(value)} |"
        )
    md_path = out_dir / f"collector_state_{base}.md"
    md_path.write_text("\n".join(lines), encoding="utf-8")
    return json_path, md_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Replay HUMAN collector decoded handlers into an offline state/cookie timeline.")
    parser.add_argument("decode_json", type=Path)
    parser.add_argument("--trace", type=Path, default=None, help="Optional js_internal_trace jsonl for parent postMessage correlation.")
    parser.add_argument("--out-dir", type=Path, default=REPO / "output/protocol_reverse/collector_state")
    args = parser.parse_args()

    result = replay(args.decode_json, args.trace)
    json_path, md_path = write_outputs(result, args.out_dir)
    print(json.dumps({"jsonPath": str(json_path), "mdPath": str(md_path), "counts": result["counts"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
