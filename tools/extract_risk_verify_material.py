#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


REPO = Path("/Users/chaopenglv/data/me/Gpt-Agreement-Payment")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as fh:
        for line_no, line in enumerate(fh, 1):
            if not line.strip():
                continue
            row = json.loads(line)
            row["_line"] = line_no
            rows.append(row)
    return rows


def maybe_json(text: Any) -> Any:
    if not isinstance(text, str) or not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def base_name(path: Path) -> str:
    name = path.name.removesuffix(".jsonl").removesuffix(".json")
    for prefix in ("runtime_trace_", "collector_state_"):
        if name.startswith(prefix):
            return name[len(prefix):]
    return name


def find_http_pairs(runtime: Path) -> list[dict[str, Any]]:
    rows = read_jsonl(runtime)
    pairs: list[dict[str, Any]] = []
    pending: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        url = row.get("url", "")
        if row.get("kind") == "request":
            pending.setdefault(url, []).append(row)
        elif row.get("kind") == "response":
            queue = pending.get(url) or []
            req = queue.pop(0) if queue else None
            pairs.append({"request": req, "response": row})
    return pairs


def extract_cookie_sources(state_doc: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    parent_by_line = {row.get("line"): row for row in state_doc.get("parentMessages", [])}
    parent_by_event: dict[tuple[Any, Any, str], dict[str, Any]] = {}
    for row in state_doc.get("parentCorrelations", []):
        key = (row.get("collectorLine"), row.get("partIndex"), row.get("name"))
        parent_by_event[key] = parent_by_line.get(row.get("parentLine")) or {}
    sources: dict[str, list[dict[str, Any]]] = {}
    for ev in state_doc.get("events", []):
        if ev.get("effect") not in {"set_cookie", "set_cookie_and_storage"}:
            continue
        name = ev.get("name")
        value = ev.get("value")
        if not name or value is None:
            continue
        sources.setdefault(name, []).append(
            {
                "collectorLine": ev.get("collectorLine"),
                "partIndex": ev.get("partIndex"),
                "handler": ev.get("handler"),
                "effect": ev.get("effect"),
                "ttl": ev.get("ttl"),
                "domain": ev.get("domain"),
                "value": value,
                "parentMessage": parent_by_event.get((ev.get("collectorLine"), ev.get("partIndex"), name)),
            }
        )
    return sources


def find_cookie_source(sources: dict[str, list[dict[str, Any]]], logical_name: str, value: str) -> dict[str, Any] | None:
    candidates = sources.get(logical_name) or []
    for row in candidates:
        if row.get("value") == value:
            return row
    return None


def summarize_risk_pair(pair: dict[str, Any], sources: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    req = pair.get("request") or {}
    resp = pair.get("response") or {}
    req_body = maybe_json(req.get("post_data"))
    resp_body = maybe_json(resp.get("body"))
    challenge_solution = (req_body or {}).get("challengeSolution") or {}
    risk_meta = ((req_body or {}).get("riskProviderMetadata") or [{}])[0] if isinstance((req_body or {}).get("riskProviderMetadata"), list) else {}

    value_sources = {}
    for field, cookie_name in (("px3", "_px3"), ("pxde", "_pxde"), ("pxvid", "_pxvid")):
        value = challenge_solution.get(field) or risk_meta.get(field)
        if value:
            source = find_cookie_source(sources, cookie_name, value)
            if source:
                parent = source.get("parentMessage") or {}
                req_t = req.get("t")
                parent_t = parent.get("wall_t")
                source = {
                    **source,
                    "temporalProof": {
                        "parentWallTime": parent_t,
                        "requestTime": req_t,
                        "parentBeforeRequest": (
                            isinstance(parent_t, (int, float))
                            and isinstance(req_t, (int, float))
                            and parent_t <= req_t
                        ),
                    },
                }
            value_sources[field] = source

    return {
        "requestLine": req.get("_line"),
        "responseLine": resp.get("_line"),
        "url": req.get("url") or resp.get("url"),
        "status": resp.get("status"),
        "requestHeaders": req.get("headers"),
        "requestTime": req.get("t"),
        "requestBody": req_body,
        "responseHeaders": resp.get("headers"),
        "responseTime": resp.get("t"),
        "responseBody": resp_body,
        "state": (resp_body or {}).get("state") if isinstance(resp_body, dict) else None,
        "hasChallengeSolution": bool(challenge_solution),
        "challengeSolution": challenge_solution,
        "riskProviderMetadata": (req_body or {}).get("riskProviderMetadata") if isinstance(req_body, dict) else None,
        "valueSources": value_sources,
    }


def analyze(runtime: Path, collector_state: Path) -> dict[str, Any]:
    state_doc = json.loads(collector_state.read_text(encoding="utf-8"))
    sources = extract_cookie_sources(state_doc)
    pairs = find_http_pairs(runtime)
    risk_pairs = [
        summarize_risk_pair(pair, sources)
        for pair in pairs
        if pair.get("request") and "risk/verify" in str(pair["request"].get("url", ""))
    ]
    create_pairs = []
    for pair in pairs:
        req = pair.get("request") or {}
        resp = pair.get("response") or {}
        if "API/CreateAccount" not in str(req.get("url", "")):
            continue
        create_pairs.append(
            {
                "requestLine": req.get("_line"),
                "responseLine": resp.get("_line"),
                "url": req.get("url"),
                "status": resp.get("status"),
                "requestHeaders": req.get("headers"),
                "requestBody": maybe_json(req.get("post_data")),
                "responseHeaders": resp.get("headers"),
                "responseBody": maybe_json(resp.get("body")),
            }
        )

    token_links: list[dict[str, Any]] = []
    for idx, row in enumerate(risk_pairs):
        body = row.get("responseBody") or {}
        token = body.get("continuationToken") if isinstance(body, dict) else None
        if not token:
            continue
        for next_row in risk_pairs[idx + 1:]:
            req_body = next_row.get("requestBody") or {}
            if req_body.get("continuationToken") == token:
                token_links.append(
                    {
                        "from": f"risk.response:{row.get('responseLine')}",
                        "to": f"risk.request:{next_row.get('requestLine')}",
                        "field": "continuationToken",
                        "match": True,
                    }
                )
        for create in create_pairs:
            req_body = create.get("requestBody") or {}
            if req_body.get("ContinuationToken") == token:
                token_links.append(
                    {
                        "from": f"risk.response:{row.get('responseLine')}",
                        "to": f"create.request:{create.get('requestLine')}",
                        "field": "ContinuationToken",
                        "match": True,
                    }
                )

    final_continue = [row for row in risk_pairs if row.get("state") == "continue"]
    return {
        "runtimeTrace": str(runtime),
        "collectorState": str(collector_state),
        "counts": {
            "riskVerifyRequests": len(risk_pairs),
            "createAccountRequests": len(create_pairs),
            "riskContinueResponses": len(final_continue),
            "tokenLinks": len(token_links),
        },
        "cookieSources": sources,
        "riskVerify": risk_pairs,
        "createAccount": create_pairs,
        "tokenLinks": token_links,
    }


def write_outputs(result: dict[str, Any], out_dir: Path) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    base = base_name(Path(result["runtimeTrace"]))
    json_path = out_dir / f"risk_verify_material_{base}.json"
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    lines: list[str] = []
    lines.append(f"# risk/verify replay material: {base}")
    lines.append("")
    lines.append(f"runtimeTrace={result['runtimeTrace']}")
    lines.append(f"collectorState={result['collectorState']}")
    lines.append("")
    lines.append("## counts")
    for key, value in result["counts"].items():
        lines.append(f"- {key}: {value}")
    lines.append("")
    lines.append("## risk/verify calls")
    lines.append("| request line | response line | status | state | challengeSolution | px3 source | pxde source | pxvid source | all parent messages before request |")
    lines.append("|---:|---:|---:|---|---|---|---|---|---|")
    for row in result["riskVerify"]:
        sources = row.get("valueSources") or {}
        def src(name: str) -> str:
            s = sources.get(name)
            if not s:
                return ""
            return f"collectorLine={s.get('collectorLine')} part={s.get('partIndex')} handler={s.get('handler')}"
        temporal_values = [
            ((sources.get(name) or {}).get("temporalProof") or {}).get("parentBeforeRequest")
            for name in ("px3", "pxde", "pxvid")
            if sources.get(name)
        ]
        all_before = bool(temporal_values) and all(v is True for v in temporal_values)
        lines.append(
            f"| {row.get('requestLine')} | {row.get('responseLine')} | {row.get('status')} | {row.get('state')} | {row.get('hasChallengeSolution')} | {src('px3')} | {src('pxde')} | {src('pxvid')} | {all_before} |"
        )
    lines.append("")
    lines.append("## token links")
    for link in result["tokenLinks"]:
        lines.append(f"- {link['from']} -> {link['to']} via {link['field']} match={link['match']}")
    lines.append("")
    lines.append("## CreateAccount")
    for row in result["createAccount"]:
        body = row.get("responseBody") or {}
        lines.append(
            f"- requestLine={row.get('requestLine')} responseLine={row.get('responseLine')} status={row.get('status')} redirectUrl={bool(isinstance(body, dict) and body.get('redirectUrl'))}"
        )
    md_path = out_dir / f"risk_verify_material_{base}.md"
    md_path.write_text("\n".join(lines), encoding="utf-8")
    return json_path, md_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Extract Microsoft risk/verify replay material and prove HUMAN token provenance from collector state.")
    parser.add_argument("runtime_trace", type=Path)
    parser.add_argument("--collector-state", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, default=REPO / "output/protocol_reverse/risk_verify")
    args = parser.parse_args()
    result = analyze(args.runtime_trace, args.collector_state)
    json_path, md_path = write_outputs(result, args.out_dir)
    print(json.dumps({"jsonPath": str(json_path), "mdPath": str(md_path), "counts": result["counts"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
