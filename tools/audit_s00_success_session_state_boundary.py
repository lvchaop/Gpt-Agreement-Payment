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
SUCCESS_LINE = 933
SESSION_FIELDS = ["cs", "sid", "vid", "cts", "ci", "rsc", "p1"]
OBSERVED_FIELDS = ["uuid", "tag", "ft", "seq", "en"]


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def check_file(path: Path) -> dict[str, Any]:
    return {"path": str(path.resolve()), "exists": path.exists()}


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
    out: dict[str, str] = {}
    for part in str(body or "").split("&"):
        if not part:
            continue
        key, _, value = part.partition("=")
        out[urllib.parse.unquote_plus(key)] = urllib.parse.unquote_plus(value)
    return out


def runtime_params(build: dict[str, Any]) -> dict[str, str]:
    evidence = build.get("evidenceFiles") or {}
    runtime_path = Path(evidence.get("runtimeTrace") or "")
    if runtime_path and not runtime_path.is_absolute():
        runtime_path = REPO / runtime_path
    for row in read_jsonl(runtime_path):
        if int(row.get("_line") or 0) == SUCCESS_LINE:
            return parse_form(str(row.get("post_data") or ""))
    return {}


def field_check(row: dict[str, Any], field: str) -> dict[str, Any]:
    check = (row.get("checks") or {}).get(field) or {}
    return {
        "expected": check.get("expected"),
        "observed": check.get("observed"),
        "match": check.get("match") is True,
        "source": check.get("source"),
    }


def build_audit() -> dict[str, Any]:
    state_path = PROTO / f"collector_request_state/collector_request_state_validation_bundle_request_build_{RUN_ID}.json"
    build_path = PROTO / f"bundle_request_build/bundle_request_build_{RUN_ID}.json"
    spec_path = PROTO / "goal_audit/s00_success_constructor_spec_audit.json"
    replay_path = PROTO / "goal_audit/s00_exact_success_replay_live_audit.json"
    value_chain_path = PROTO / "goal_audit/s00_same_session_px561_value_chain_audit.json"

    state = read_json(state_path)
    build = read_json(build_path)
    spec = read_json(spec_path)
    replay = read_json(replay_path)
    value_chain = read_json(value_chain_path)

    state_row = next(r for r in state.get("rows") or [] if int(r.get("requestLine") or 0) == SUCCESS_LINE)
    build_row = next(r for r in build.get("rows") or [] if int(r.get("requestLine") or 0) == SUCCESS_LINE)
    spec_checks = spec.get("checks") or {}
    replay_checks = replay.get("checks") or {}
    value_chain_checks = value_chain.get("checks") or {}
    runtime_line_params = runtime_params(build)

    session_checks = {field: field_check(state_row, field) for field in SESSION_FIELDS}
    observed_runtime_params = {
        field: runtime_line_params.get(field) for field in OBSERVED_FIELDS if runtime_line_params.get(field) is not None
    }
    observed_runtime_params["pc"] = build_row.get("observedPc")
    observed_runtime_params["paramOrder"] = build_row.get("paramOrder")

    checks = {
        "line933Exists": bool(state_row and build_row),
        **{f"line933{field.upper()}Match": session_checks[field]["match"] for field in SESSION_FIELDS},
        "line933UuidTagFtSeqEnObserved": all(observed_runtime_params.get(field) for field in OBSERVED_FIELDS),
        "line933PcConstructible": spec_checks.get("tfMaterialPcMatchesRequest") is True
        and spec_checks.get("bundleRebuildBodyExact") is True,
        "line933BodyExactBuild": build_row.get("bodyMatch") is True and spec_checks.get("bundleRebuildBodyExact") is True,
        "line933SameSessionValueChainSuccess": value_chain_checks.get("line933HandlerSuccess") is True
        and value_chain_checks.get("successRowSameSessionCoherent") is True,
        "staleReplayStillFails": replay_checks.get("liveReplayReturnsFailure") is True
        and replay_checks.get("liveReplayDoesNotReturnSuccess") is True,
    }
    checks["sessionStateBoundaryClosedForObservedLine933"] = all(
        checks[f"line933{field.upper()}Match"] for field in SESSION_FIELDS
    )
    checks["pureProtocolSessionGenerationStillMissing"] = True
    checks["pureProtocolReady"] = False

    return {
        "purpose": "Audit s00 line 933 successful collector request session-state constructor boundary.",
        "runId": RUN_ID,
        "successRequestLine": SUCCESS_LINE,
        "evidenceFiles": {
            "stateValidation": check_file(state_path),
            "bundleRequestBuild": check_file(build_path),
            "successConstructorSpec": check_file(spec_path),
            "exactSuccessReplayLive": check_file(replay_path),
            "sameSessionValueChain": check_file(value_chain_path),
        },
        "line933": {
            "appliedCollectorLines": state_row.get("appliedCollectorLines"),
            "sessionState": state_row.get("state"),
            "sessionChecks": session_checks,
            "observedRuntimeParams": observed_runtime_params,
            "build": {
                "materialSourceLine": build_row.get("materialSourceLine"),
                "serializedSha256": build_row.get("serializedSha256"),
                "observedPayloadLen": build_row.get("observedPayloadLen"),
                "rebuiltPayloadLen": build_row.get("rebuiltPayloadLen"),
                "observedPc": build_row.get("observedPc"),
                "rebuiltPc": build_row.get("rebuiltPc"),
                "payloadMatch": build_row.get("payloadMatch"),
                "pcMatch": build_row.get("pcMatch"),
                "bodyMatch": build_row.get("bodyMatch"),
            },
        },
        "checks": checks,
        "remainingGaps": [
            "uuid/tag/ft/seq/en are observed from runtime line 933; this audit does not prove a fresh no-browser generator for them.",
            "cs/sid/vid/cts/ci/rsc/p1 for observed line 933 match decoded prior collector/runtime state, but stale replay returning oIIoIooo|-1 proves copied fixed state is not a live PoC.",
            "AEAx live-accepted substitution, Bzt pure timing policy, and non-tail PX561 minimal protocol material remain outside this session-state boundary audit.",
        ],
        "conclusion": (
            "For observed s00 line 933, collector-decoded state plus runtime-visible counters/params explains the successful request's session boundary, "
            "and body/pc/payload are byte-rebuildable. This closes the observed-artifact constructor boundary for line 933 only; "
            "the live exact replay failure keeps the end-to-end pure protocol PoC unproved."
        ),
    }


def write_markdown(result: dict[str, Any], path: Path) -> None:
    lines = [
        "# s00 line 933 session-state boundary audit",
        "",
        f"- runId: `{result['runId']}`",
        f"- successRequestLine: `{result['successRequestLine']}`",
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
        "## Line 933 session fields",
        "",
        "| field | match | observed | expected source |",
        "|---|---:|---|---|",
    ]
    for field, check in (result["line933"]["sessionChecks"] or {}).items():
        source = check.get("source")
        lines.append(
            f"| `{field}` | `{check.get('match')}` | `{check.get('observed')}` | `{json.dumps(source, ensure_ascii=False)[:220]}` |"
        )
    lines += [
        "",
        "## Remaining gaps",
        "",
        *[f"- {gap}" for gap in result["remainingGaps"]],
        "",
        "## Conclusion",
        "",
        result["conclusion"],
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    result = build_audit()
    json_path = OUT_DIR / "s00_success_session_state_boundary_audit.json"
    md_path = OUT_DIR / "s00_success_session_state_boundary_audit.md"
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    write_markdown(result, md_path)
    print(json.dumps({"json": str(json_path), "md": str(md_path), "checks": result["checks"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
