#!/usr/bin/env python3
from __future__ import annotations

import json
import urllib.parse
from pathlib import Path
from typing import Any


REPO = Path("/Users/chaopenglv/data/me/Gpt-Agreement-Payment")
PROTO = REPO / "output/protocol_reverse"
OUT_DIR = PROTO / "goal_audit"
RUN_ID = "s00ld1lglrw0_1781191381"
RUNTIME_TRACE = REPO / f"output/outlook_browser/runtime_trace_{RUN_ID}.jsonl"
JS_TRACE = REPO / f"output/outlook_browser/js_internal_trace_{RUN_ID}.jsonl"
STATIC_JS = REPO / "output/outlook_browser/js_static_analysis/main.beautified.js"


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as fh:
        for line_no, line in enumerate(fh, 1):
            if line.strip():
                row = json.loads(line)
                row["_line"] = line_no
                rows.append(row)
    return rows


def parse_form(body: str) -> dict[str, str]:
    return dict(urllib.parse.parse_qsl(str(body or ""), keep_blank_values=True))


def line_ref(start: int, end: int, note: str) -> dict[str, Any]:
    return {"file": str(STATIC_JS), "lines": f"{start}-{end}", "note": note}


def request_rows(runtime_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in runtime_rows:
        if row.get("kind") != "request" or "/assets/js/bundle" not in str(row.get("url") or ""):
            continue
        params = parse_form(str(row.get("post_data") or ""))
        rows.append(
            {
                "line": row.get("_line"),
                "t": row.get("t"),
                "appId": params.get("appId"),
                "tag": params.get("tag"),
                "uuid": params.get("uuid"),
                "ft": params.get("ft"),
                "seq": params.get("seq"),
                "en": params.get("en"),
                "rsc": params.get("rsc"),
                "cs": params.get("cs"),
                "sidPresent": "sid" in params,
                "ci": params.get("ci"),
                "paramOrder": [part.partition("=")[0] for part in str(row.get("post_data") or "").split("&") if part],
            }
        )
    return rows


def tf_payload_rows(js_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in js_rows:
        if row.get("kind") != "hsprotect.main.tf.payload":
            continue
        data = row.get("data") or {}
        meta = data.get("meta") or {}
        activities = data.get("activities") or []
        first_d = ((activities[0] or {}).get("d") or {}) if activities and isinstance(activities[0], dict) else {}
        rows.append(
            {
                "line": row.get("_line"),
                "perf_t": row.get("perf_t"),
                "activityTypes": [a.get("t") for a in activities if isinstance(a, dict)],
                "meta": {
                    "appID": meta.get("appID"),
                    "tag": meta.get("tag"),
                    "cu": meta.get("cu"),
                    "pc": meta.get("pc"),
                },
                "qi": data.get("qi"),
                "cs": data.get("cs"),
                "markerLen": data.get("markerLen"),
                "firstActivityUuidField": first_d.get("FUFvS1Mga38="),
                "firstActivityEventIndex": first_d.get("HUlnQ1slanM="),
                "firstActivityPerfOrWall": first_d.get("R3c9PQEXNg8="),
                "firstActivityWall": first_d.get("QS07ZwRKPlU="),
            }
        )
    return rows


def sequence(values: list[str | None], start: int) -> bool:
    try:
        return [int(v) for v in values] == list(range(start, start + len(values)))
    except (TypeError, ValueError):
        return False


def build_audit() -> dict[str, Any]:
    runtime_rows = read_jsonl(RUNTIME_TRACE)
    js_rows = read_jsonl(JS_TRACE)
    requests = request_rows(runtime_rows)
    tf_rows = tf_payload_rows(js_rows)

    app_ids = sorted({r.get("appId") for r in requests if r.get("appId")})
    tags = sorted({r.get("tag") for r in requests if r.get("tag")})
    fts = sorted({r.get("ft") for r in requests if r.get("ft")})
    ens = sorted({r.get("en") for r in requests if r.get("en")})
    uuids = sorted({r.get("uuid") for r in requests if r.get("uuid")})
    tf_uuids = sorted({r.get("meta", {}).get("cu") for r in tf_rows if r.get("meta", {}).get("cu")})

    checks = {
        "runtimeBundleRequestsFound": len(requests) == 7,
        "appIdConstantMatchesRuntime": app_ids == ["PXzC5j78di"],
        "tagConstantMatchesRuntime": tags == ["YjIYfyxJHRR9"],
        "ftConstantMatchesRuntime": fts == ["369"],
        "enConstantMatchesRuntime": ens == ["NTA"],
        "uuidStableAcrossBundleRequests": len(uuids) == 1,
        "uuidMatchesTfMetaCu": len(uuids) == 1 and uuids == tf_uuids,
        "seqIsZeroBasedTfCounter": sequence([r.get("seq") for r in requests], 0),
        "rscIsOneBasedSendCounter": sequence([r.get("rsc") for r in requests], 1),
        "tfPayloadRowsFound": len(tf_rows) >= len(requests),
        "freshUuidAlgorithmStaticIdentified": True,
        "freshOuterParamsProtocolGenerationProved": False,
    }

    return {
        "purpose": "Map s00 outer /assets/js/bundle params to static JS and runtime evidence before fresh-state construction.",
        "runId": RUN_ID,
        "evidenceFiles": {
            "runtimeTrace": str(RUNTIME_TRACE),
            "jsTrace": str(JS_TRACE),
            "staticJs": str(STATIC_JS),
        },
        "staticEvidence": {
            "constants": [
                line_ref(406, 408, "gt=client tag, yt=ft, bt=appId constants"),
                line_ref(4804, 4805, "ql='NTA', $l=0 sequence counter"),
                line_ref(4837, 4837, "form appends payload/appId/tag/uuid/ft/seq/en in this order"),
            ],
            "uuid": [
                line_ref(1053, 1074, "decoded form field names include uuid and _pxUuid storage key"),
                line_ref(1551, 1573, "uuid.v1-like io() generator"),
                line_ref(1593, 1595, "po() reads existing _pxUuid/local uuid or creates io(), then stores _pxUuid"),
                line_ref(4827, 4837, "po() feeds pc key, meta cu, and form uuid"),
            ],
            "seqAndRsc": [
                line_ref(4804, 4837, "$l initialized 0 and form seq uses $l++"),
                line_ref(8374, 8374, "wv send counter initialized 0"),
                line_ref(8423, 8424, "Fv appends rsc=++wv before send"),
            ],
            "activityState": [
                line_ref(3455, 3464, "ds assigns activity event index/time before queueing"),
                line_ref(8523, 8523, "send path adds current wall time, uuid, Sv/Tv to queued activities before tf()"),
            ],
        },
        "runtimeEvidence": {
            "bundleRequests": requests,
            "tfPayloadRows": tf_rows,
        },
        "checks": checks,
        "closedForObservedRun": [
            "appId/tag/ft/en are static constants and match every observed bundle request.",
            "uuid is stable across every observed bundle request and matches every tf.payload meta.cu sample.",
            "seq and rsc are monotonic counters matching static $l++ and ++wv behavior.",
        ],
        "remainingFreshStateGaps": [
            "po()/io() identifies how a fresh _pxUuid can be created, but this audit has not run a no-browser live session that uses a generated uuid and receives accepted collector state.",
            "Parameter order is still copied from observed runtime requests; static tf() explains the fixed prefix order, but optional-field order/minimality still needs a fresh constructor probe.",
            "cs/sid/vid/cts/ci are decoded from collector responses in the observed session; fresh protocol still must drive the initial collector exchange and prove the returned state is accepted in a later PX561 success body.",
            "Non-tail PX561 activity material, AEAx live-accepted generation, and Bzt timing policy remain outside this outer-param audit.",
        ],
        "conclusion": (
            "The remaining outer params for observed s00 are mapped to concrete static producers and runtime samples. "
            "This supports fresh-state construction, but does not itself prove a browserless live accepted HUMAN packet."
        ),
    }


def write_markdown(result: dict[str, Any], path: Path) -> None:
    lines = [
        "# s00 fresh-state parameter source audit",
        "",
        f"- runId: `{result['runId']}`",
        "",
        "## Checks",
        "",
        "| check | value |",
        "|---|---:|",
    ]
    for key, value in result["checks"].items():
        lines.append(f"| `{key}` | `{value}` |")
    lines += [
        "",
        "## Closed for observed run",
        "",
        *[f"- {item}" for item in result["closedForObservedRun"]],
        "",
        "## Remaining fresh-state gaps",
        "",
        *[f"- {gap}" for gap in result["remainingFreshStateGaps"]],
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    result = build_audit()
    json_path = OUT_DIR / "s00_fresh_state_param_sources_audit.json"
    md_path = OUT_DIR / "s00_fresh_state_param_sources_audit.md"
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    write_markdown(result, md_path)
    print(json.dumps({"json": str(json_path), "md": str(md_path), "checks": result["checks"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
