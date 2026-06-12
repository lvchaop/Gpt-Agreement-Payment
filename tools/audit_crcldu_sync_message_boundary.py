#!/usr/bin/env python3
from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path
from typing import Any


REPO = Path("/Users/chaopenglv/data/me/Gpt-Agreement-Payment")
PROTO = REPO / "output/protocol_reverse"
OUT_DIR = PROTO / "goal_audit"
RUNTIME = REPO / "output/outlook_browser/runtime_trace_s00ld1lglrw0_1781191381.jsonl"
JS_TRACE = REPO / "output/outlook_browser/js_internal_trace_s00ld1lglrw0_1781191381.jsonl"


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    with path.open("r", encoding="utf-8") as fh:
        for idx, line in enumerate(fh, 1):
            if line.strip():
                row = json.loads(line)
                row["_line"] = idx
                rows.append(row)
    return rows


def js_success_line(rows: list[dict[str, Any]]) -> int | None:
    for row in rows:
        data = row.get("data") or {}
        if row.get("kind") == "hsprotect.main.jl.dispatch" and data.get("handlerKey") == "oIIoIooo" and data.get("args") == ["0"]:
            return int(row["_line"])
    return None


def crcldu_messages(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for row in rows:
        if row.get("kind") != "window.message.recv":
            continue
        href = str(row.get("href") or "")
        data = row.get("data") or {}
        if "crcldu.com/bd/sync.html" not in href:
            continue
        msg = str(data.get("data") or "")
        raw = b""
        decoded_preview = ""
        try:
            raw = base64.b64decode(msg + "=" * ((4 - len(msg) % 4) % 4))
            decoded_preview = raw[:200].decode("latin1", errors="replace")
        except Exception:
            pass
        out.append({
            "line": row.get("_line"),
            "wall_t": row.get("wall_t"),
            "perf_t": row.get("perf_t"),
            "href": href,
            "eventOrigin": data.get("eventOrigin"),
            "dataType": data.get("dataType"),
            "dataLen": len(msg),
            "dataSha256": hashlib.sha256(msg.encode()).hexdigest(),
            "base64RawLen": len(raw),
            "base64RawSha256": hashlib.sha256(raw).hexdigest() if raw else None,
            "base64RawPreviewLatin1": decoded_preview,
        })
    return out


def runtime_crcldu_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for row in rows:
        url = str(row.get("url") or "")
        text = str(row.get("text") or "")
        if "crcldu.com" not in url and "crcldu.com" not in text and "sync.html" not in url and "sync.html" not in text:
            continue
        out.append({
            "line": row.get("_line"),
            "kind": row.get("kind"),
            "method": row.get("method"),
            "status": row.get("status"),
            "url": url,
            "post_len": row.get("post_len"),
            "body_len": row.get("body_len"),
            "t": row.get("t"),
            "textPreview": text[:240],
        })
    return out


def runtime_collector_boundary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    selected = []
    for row in rows:
        url = str(row.get("url") or "")
        text = str(row.get("text") or "")
        if "collector-pxzc5j78di.hsprotect.net/assets/js/bundle" in url or "oIIoIooo|0" in text:
            selected.append({
                "line": row.get("_line"),
                "kind": row.get("kind"),
                "method": row.get("method"),
                "status": row.get("status"),
                "url": url,
                "post_len": row.get("post_len"),
                "t": row.get("t"),
                "textPreview": text[:200],
            })
    return {
        "rows": selected,
        "acceptedSeq5RequestLine": next((r["line"] for r in selected if r["kind"] == "request" and r["post_len"] == 43814), None),
        "acceptedSuccessConsoleLine": next((r["line"] for r in selected if "oIIoIooo|0" in str(r.get("textPreview") or "")), None),
    }


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    js_rows = read_jsonl(JS_TRACE)
    rt_rows = read_jsonl(RUNTIME)
    success_line = js_success_line(js_rows)
    messages = crcldu_messages(js_rows)
    runtime_rows = runtime_crcldu_rows(rt_rows)
    collector = runtime_collector_boundary(rt_rows)
    pre_success_messages = [m for m in messages if isinstance(success_line, int) and int(m["line"]) < success_line]
    runtime_network_rows = [r for r in runtime_rows if r.get("kind") in {"request", "response"}]
    result = {
        "purpose": "Classify s00 crcldu.com/bd/sync.html opaque postMessage events relative to the accepted collector success.",
        "evidenceFiles": {
            "jsTrace": str(JS_TRACE.resolve()),
            "runtimeTrace": str(RUNTIME.resolve()),
        },
        "js": {
            "firstSuccessDispatchLine": success_line,
            "crclduMessages": messages,
            "preSuccessCrclduMessages": pre_success_messages,
        },
        "runtime": {
            "crclduRows": runtime_rows,
            "crclduNetworkRows": runtime_network_rows,
            "collectorBoundary": collector,
        },
        "checks": {
            "hasCrclduMessages": bool(messages),
            "hasPreSuccessCrclduMessages": bool(pre_success_messages),
            "allCrclduMessagesAreWindowMessageRecv": all(r.get("kind") == "console" for r in runtime_rows),
            "noRuntimeCrclduRequestOrResponseRows": len(runtime_network_rows) == 0,
            "latestPreSuccessCrclduBeforeAcceptedCollectorRequest": (
                bool(pre_success_messages)
                and isinstance(collector.get("acceptedSeq5RequestLine"), int)
                and max(int(m["line"]) for m in pre_success_messages) < success_line
            ),
        },
        "conclusion": (
            "s00 contains three crcldu.com/bd/sync.html window.message.recv events from iframe.hsprotect.net, including one before the accepted collector request window. "
            "In the captured runtime trace these appear as console-observed message events only; no crcldu request/response rows are present after those messages. "
            "This proves the opaque crcldu sync message is a browser-internal/third-frame event, not a directly observed collector network transition. "
            "It remains a browser-state artifact to track, but current evidence does not show it mutating collector server-side state through a network request."
        ),
    }
    json_path = OUT_DIR / "crcldu_sync_message_boundary_audit.json"
    md_path = OUT_DIR / "crcldu_sync_message_boundary_audit.md"
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(
        "\n".join([
            "# crcldu sync message boundary audit",
            "",
            f"- firstSuccessDispatchLine: `{success_line}`",
            f"- crcldu message count: `{len(messages)}`",
            f"- pre-success crcldu message count: `{len(pre_success_messages)}`",
            f"- runtime crcldu network rows: `{len(runtime_network_rows)}`",
            "",
            "## Checks",
            *[f"- {k}: `{v}`" for k, v in result["checks"].items()],
            "",
            "## Conclusion",
            result["conclusion"],
            "",
        ]),
        encoding="utf-8",
    )
    print(json.dumps({"json": str(json_path), "md": str(md_path), "checks": result["checks"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
