#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import urllib.parse
from pathlib import Path
from typing import Any


REPO = Path("/Users/chaopenglv/data/me/Gpt-Agreement-Payment")


BODY_FIELDS = {
    "payload": "rebuilt by tools/build_human_collector_request.mjs from tf activities + Vs + marker state",
    "appId": "static/runtime meta: PXzC5j78di",
    "tag": "static/runtime meta: YjIYfyxJHRR9",
    "uuid": "runtime meta cu from tf payload",
    "ft": "static/runtime meta: 369",
    "seq": "observed collector sequence",
    "en": "static value NTA",
    "pc": "rebuilt by Jt(ut(activities), cu:tag:ft)",
    "cs": "validated from previous collector handler IoIIII -> Yo",
    "sid": "validated from previous collector handler IIoIIo + Kl(oIIoIoII -> Jo)",
    "vid": "validated from previous collector handler IooIoo -> _pxvid",
    "cts": "validated from previous collector handler oIIooIIo -> Fo",
    "p1": "validated from iframe session_id / _pxParam1",
    "rsc": "validated as incrementing request counter",
}


HEADER_SOURCES = {
    "host": "derived from request URL host",
    "user-agent": "browser/profile material; pure protocol must supply matching UA",
    "accept": "static browser fetch header in samples",
    "accept-language": "browser/profile locale material",
    "accept-encoding": "transport/client capability header",
    "content-type": "static application/x-www-form-urlencoded",
    "content-length": "derived from UTF-8 byte length of request body",
    "referer": "static iframe origin path in samples",
    "origin": "static iframe origin in samples",
    "sec-fetch-dest": "browser fetch metadata header",
    "sec-fetch-mode": "browser fetch metadata header",
    "sec-fetch-site": "browser fetch metadata header",
    "proxy-authorization": "proxy infrastructure header; do not include unless using that proxy transport",
    "connection": "transport/client connection header",
    "cookie": "runtime cookie jar header if present",
}


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


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


def parse_form_ordered(body: str) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for part in str(body or "").split("&"):
        if not part:
            continue
        key, _, value = part.partition("=")
        out.append(
            {
                "key": urllib.parse.unquote_plus(key),
                "rawValue": value,
                "value": urllib.parse.unquote_plus(value),
            }
        )
    return out


def base_from_request_build(path: Path) -> str:
    name = path.name
    return name.removeprefix("collector_request_build_").removesuffix(".json")


def default_state_validation_path(base: str) -> Path:
    return REPO / "output/protocol_reverse/collector_request_state" / f"collector_request_state_validation_{base}.json"


def find_runtime_pair(runtime_rows: list[dict[str, Any]], request_line: int) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    req = next((r for r in runtime_rows if int(r.get("_line") or 0) == request_line), None)
    resp = None
    if req:
        for row in runtime_rows:
            if int(row.get("_line") or 0) <= request_line:
                continue
            if row.get("kind") == "response" and row.get("url") == req.get("url"):
                resp = row
                break
    return req, resp


def body_field_rows(row: dict[str, Any], state_row: dict[str, Any] | None) -> list[dict[str, Any]]:
    form = parse_form_ordered(row.get("rebuiltBody") or row.get("observedBody") or "")
    checks = (state_row or {}).get("checks") or {}
    out: list[dict[str, Any]] = []
    for idx, item in enumerate(form):
        key = item["key"]
        check = checks.get(key)
        out.append(
            {
                "index": idx,
                "key": key,
                "valueLen": len(item["value"]),
                "source": BODY_FIELDS.get(key, "observed from runtime; independent producer not classified"),
                "validated": bool(
                    key in {"payload", "appId", "tag", "uuid", "en", "pc"}
                    and row.get(f"{key}Match") is True
                )
                or bool(key == "en" and item["value"] == "NTA")
                or bool(check and check.get("match") is True)
                or key in {"ft", "seq"},
                "stateCheck": check,
            }
        )
    return out


def header_rows(headers: dict[str, Any], body: str, url: str) -> list[dict[str, Any]]:
    parsed = urllib.parse.urlparse(url)
    rows: list[dict[str, Any]] = []
    for name, value in headers.items():
        lower = str(name).lower()
        expected: str | None = None
        match: bool | None = None
        if lower == "host":
            expected = parsed.netloc
            match = str(value) == expected
        elif lower == "content-length":
            expected = str(len(body.encode("utf-8")))
            match = str(value) == expected
        elif lower == "content-type":
            expected = "application/x-www-form-urlencoded"
            match = str(value).split(";")[0].strip().lower() == expected
        elif lower == "origin":
            expected = "https://iframe.hsprotect.net"
            match = str(value) == expected
        elif lower == "referer":
            expected = "https://iframe.hsprotect.net/"
            match = str(value) == expected
        rows.append(
            {
                "name": lower,
                "value": value,
                "valueLen": len(str(value)),
                "source": HEADER_SOURCES.get(lower, "observed runtime header; source not classified"),
                "expected": expected,
                "match": match,
                "sensitive": lower in {"proxy-authorization", "cookie", "authorization"},
                "pureProtocolStatus": (
                    "derive"
                    if lower in {"host", "content-length", "content-type", "origin", "referer", "accept", "sec-fetch-dest", "sec-fetch-mode", "sec-fetch-site"}
                    else "runtime_material"
                ),
            }
        )
    return rows


def summarize(request_build_path: Path, state_validation_path: Path | None) -> dict[str, Any]:
    build = read_json(request_build_path)
    base = base_from_request_build(request_build_path)
    runtime_path = Path(build.get("runtimePath") or "")
    if runtime_path and not runtime_path.is_absolute():
        runtime_path = REPO / runtime_path
    runtime_rows = read_jsonl(runtime_path)
    state_validation = read_json(state_validation_path) if state_validation_path and state_validation_path.exists() else None
    state_rows = {int(r.get("requestLine") or 0): r for r in (state_validation or {}).get("rows", [])}

    rows: list[dict[str, Any]] = []
    for row in build.get("rows", []):
        request_line = int(row.get("requestLine") or 0)
        req, resp = find_runtime_pair(runtime_rows, request_line)
        body = row.get("rebuiltBody") or row.get("observedBody") or ""
        headers = dict((req or {}).get("headers") or {})
        content_length = headers.get("content-length") or headers.get("Content-Length")
        rows.append(
            {
                "index": row.get("index"),
                "requestLine": request_line,
                "responseLine": (resp or {}).get("_line"),
                "method": (req or {}).get("method") or "POST",
                "url": row.get("url") or (req or {}).get("url"),
                "status": (resp or {}).get("status"),
                "bodyExactMatch": row.get("exactBodyMatch"),
                "rebuiltBodySha256": __import__("hashlib").sha256(body.encode("utf-8")).hexdigest(),
                "rebuiltBodyLenChars": len(body),
                "rebuiltBodyLenBytes": len(body.encode("utf-8")),
                "runtimePostLen": (req or {}).get("post_len"),
                "runtimeContentLengthHeader": content_length,
                "contentLengthMatchesBodyBytes": str(content_length) == str(len(body.encode("utf-8"))) if content_length is not None else None,
                "headerRows": header_rows(headers, body, row.get("url") or (req or {}).get("url") or ""),
                "bodyFieldRows": body_field_rows(row, state_rows.get(request_line)),
                "responseHeaders": (resp or {}).get("headers") or {},
            }
        )

    summary = {
        "requestCount": len(rows),
        "bodyExactMatches": sum(1 for r in rows if r.get("bodyExactMatch") is True),
        "contentLengthMatches": sum(1 for r in rows if r.get("contentLengthMatchesBodyBytes") is True),
        "runtimeRequestsWithHeaders": sum(1 for r in rows if r.get("headerRows")),
        "runtimeResponsesMatched": sum(1 for r in rows if r.get("status") is not None),
        "stateValidationLoaded": bool(state_validation),
        "remainingGaps": [
            "fresh live collector POST acceptance is not proven by this offline material audit",
            "TLS/HTTP2/client transport fingerprint is not represented in JSONL headers",
            "UA/locale/proxy headers are runtime material unless a separate profile generator supplies them",
            "collector response success handler oIIoIooo|0 is not generated for a fresh pure-protocol session here",
        ],
    }
    return {
        "base": base,
        "requestBuildPath": str(request_build_path),
        "runtimePath": str(runtime_path),
        "stateValidationPath": str(state_validation_path) if state_validation_path else None,
        "summary": summary,
        "rows": rows,
    }


def write_outputs(result: dict[str, Any], out_dir: Path) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    base = result["base"]
    json_path = out_dir / f"collector_replay_material_{base}.json"
    md_path = out_dir / f"collector_replay_material_{base}.md"
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    lines: list[str] = []
    lines.append(f"# collector replay material audit: {base}")
    lines.append("")
    lines.append(f"requestBuild={result['requestBuildPath']}")
    lines.append(f"runtime={result['runtimePath']}")
    lines.append(f"stateValidation={result.get('stateValidationPath') or ''}")
    lines.append("")
    lines.append("## summary")
    for key, value in result["summary"].items():
        if key == "remainingGaps":
            continue
        lines.append(f"- {key}: {value}")
    lines.append("")
    lines.append("## requests")
    lines.append("| idx | req line | resp line | status | body exact | body bytes | content-length ok | fields | headers |")
    lines.append("|---:|---:|---:|---:|---|---:|---|---:|---:|")
    for row in result["rows"]:
        lines.append(
            f"| {row['index']} | {row['requestLine']} | {row.get('responseLine') or ''} | {row.get('status') or ''} | "
            f"{row['bodyExactMatch']} | {row['rebuiltBodyLenBytes']} | {row['contentLengthMatchesBodyBytes']} | "
            f"{len(row['bodyFieldRows'])} | {len(row['headerRows'])} |"
        )
    lines.append("")
    lines.append("## body field provenance")
    for row in result["rows"]:
        lines.append(f"### request idx={row['index']} line={row['requestLine']}")
        for field in row["bodyFieldRows"]:
            lines.append(
                f"- `{field['key']}` len={field['valueLen']} validated={field['validated']} source={field['source']}"
            )
    lines.append("")
    lines.append("## header provenance")
    for row in result["rows"]:
        lines.append(f"### request idx={row['index']} line={row['requestLine']}")
        for header in row["headerRows"]:
            lines.append(
                f"- `{header['name']}` len={header['valueLen']} status={header['pureProtocolStatus']} "
                f"match={header['match']} value={header['value']} source={header['source']}"
            )
    lines.append("")
    lines.append("## remaining gaps")
    for gap in result["summary"]["remainingGaps"]:
        lines.append(f"- {gap}")
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return json_path, md_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract replay-ready HTTP material for HUMAN collector POSTs and list remaining pure-protocol gaps.")
    parser.add_argument("request_build", type=Path)
    parser.add_argument("--state-validation", type=Path)
    parser.add_argument("--out-dir", type=Path, default=REPO / "output/protocol_reverse/collector_replay_material")
    args = parser.parse_args()

    base = base_from_request_build(args.request_build)
    state_path = args.state_validation or default_state_validation_path(base)
    result = summarize(args.request_build, state_path)
    json_path, md_path = write_outputs(result, args.out_dir)
    print(json.dumps({"json": str(json_path), "md": str(md_path), "summary": result["summary"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
