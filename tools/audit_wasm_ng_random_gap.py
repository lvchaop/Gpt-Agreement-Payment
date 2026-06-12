#!/usr/bin/env python3
import json
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
PROTO = REPO / "output/protocol_reverse"
OUTLOOK = REPO / "output/outlook_browser"

S00_TRACE = OUTLOOK / "js_internal_trace_s00ld1lglrw0_1781191381.jsonl"
RUNTIME_TRACE = OUTLOOK / "runtime_trace_wdyobrwf3wkl_1781190721.jsonl"
RANDOM_RECORD = PROTO / "wasm/compute_wasm_ng_nq_once_s00_line933_pxuuid_with_ng_random_record.json"
RANDOM_REPLAY = PROTO / "wasm/compute_wasm_ng_nq_once_s00_line933_pxuuid_with_ng_random_replay.json"
CONSTRUCTOR_AUDIT = PROTO / "goal_audit/s00_success_constructor_spec_audit.json"
OUT = PROTO / "wasm/wasm_ng_random_gap_audit.json"


def read_json(path):
    return json.loads(path.read_text())


def iter_trace(path):
    if not path.exists():
        return
    for line_no, line in enumerate(path.read_text(errors="replace").splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except Exception:
            continue
        if isinstance(row, dict) and row.get("kind", "").startswith("hsprotect."):
            yield line_no, row
            continue
        text = row.get("text") if isinstance(row, dict) else None
        if not text or "__OUTLOOK_JS_INTERNAL_TRACE__" not in text:
            continue
        try:
            yield line_no, json.loads(text.split("__OUTLOOK_JS_INTERNAL_TRACE__", 1)[1])
        except Exception:
            continue


def collect_random_imports(path):
    rows = []
    for line_no, row in iter_trace(path):
        if row.get("kind") != "hsprotect.captcha.wasm.import.return":
            continue
        data = row.get("data") or {}
        active = data.get("active") or {}
        if active.get("fn") != "Ng":
            continue
        if data.get("name") not in {
            "__wbg_getRandomValues_37fa2ca9e4e07fab",
            "__wbg_randomFillSync_dc1e9a60c158336d",
        }:
            continue
        rows.append(
            {
                "line": line_no,
                "name": data.get("name"),
                "hasRandomHex": isinstance(data.get("randomHex"), str),
                "randomLen": data.get("randomLen"),
                "randomHex": data.get("randomHex"),
                "active": active,
            }
        )
    return rows


def collect_after_ng(path):
    rows = []
    for line_no, row in iter_trace(path):
        if row.get("kind") not in {
            "hsprotect.captcha.tbr9.after_ng",
            "hsprotect.captcha.wasm.ng.after",
        }:
            continue
        data = row.get("data") or {}
        rows.append(
            {
                "line": line_no,
                "kind": row.get("kind"),
                "aeaxValue": data.get("aeaxValue"),
                "retPreview": data.get("retPreview"),
                "retLen": data.get("retLen"),
            }
        )
    return rows


def main():
    random_record = read_json(RANDOM_RECORD)
    random_replay = read_json(RANDOM_REPLAY)
    constructor = read_json(CONSTRUCTOR_AUDIT)
    record_calls = random_record.get("randomFillCalls") or []
    replay_calls = random_replay.get("randomFillCalls") or []
    runtime_random_rows = collect_random_imports(RUNTIME_TRACE)
    s00_random_rows = collect_random_imports(S00_TRACE)
    s00_after_ng = collect_after_ng(S00_TRACE)
    accepted_aeax = (
        ((constructor.get("targetSources") or {}).get("AEAxBkUsPjQ=") or {}).get("value")
        or ((constructor.get("px561") or {}).get("d") or {}).get("AEAxBkUsPjQ=")
    )
    out = {
        "purpose": "Pin down the remaining Ws.Ng/AEAx evidence gap: whether the browser trace records the crypto random bytes required to deterministically replay Ng offline.",
        "evidence": {
            "offlineRandomRecord": str(RANDOM_RECORD),
            "offlineRandomReplay": str(RANDOM_REPLAY),
            "s00Trace": str(S00_TRACE),
            "runtimeTraceWithOldImportHook": str(RUNTIME_TRACE),
            "constructorAudit": str(CONSTRUCTOR_AUDIT),
        },
        "offline": {
            "recordRandomLens": [((row.get("detail") or {}).get("len")) for row in record_calls],
            "recordRandomSources": [((row.get("detail") or {}).get("source")) for row in record_calls],
            "replayRandomSources": [((row.get("detail") or {}).get("source")) for row in replay_calls],
            "recordReplayNgSame": random_record.get("output", {}).get("ngValue")
            == random_replay.get("output", {}).get("ngValue"),
            "recordReplayNqSame": random_record.get("output", {}).get("nqValue")
            == random_replay.get("output", {}).get("nqValue"),
            "ngValue": random_record.get("output", {}).get("ngValue"),
            "ngLen": random_record.get("output", {}).get("ngLen"),
            "nqValue": random_record.get("output", {}).get("nqValue"),
            "randomHexSeq": [((row.get("detail") or {}).get("hex")) for row in record_calls],
        },
        "runtime": {
            "oldHookNgRandomReturnRows": runtime_random_rows[:40],
            "oldHookNgRandomReturnRowCount": len(runtime_random_rows),
            "oldHookRowsWithRandomHex": sum(1 for row in runtime_random_rows if row.get("hasRandomHex")),
            "s00NgRandomReturnRows": s00_random_rows[:40],
            "s00NgRandomReturnRowCount": len(s00_random_rows),
            "s00RowsWithRandomHex": sum(1 for row in s00_random_rows if row.get("hasRandomHex")),
            "s00AfterNgRows": s00_after_ng,
        },
        "accepted": {
            "s00AcceptedAeax": accepted_aeax,
            "offlineNgMatchesAcceptedAeax": random_record.get("output", {}).get("ngValue") == accepted_aeax,
        },
        "checks": {
            "offlineNgConsumesNineRandomFills": [((row.get("detail") or {}).get("len")) for row in record_calls]
            == [32, 16, 16, 16, 16, 16, 16, 16, 16],
            "offlineDeterministicReplayProved": random_record.get("output", {}).get("ngValue")
            == random_replay.get("output", {}).get("ngValue")
            and random_record.get("output", {}).get("nqValue") == random_replay.get("output", {}).get("nqValue")
            and all(((row.get("detail") or {}).get("source")) == "provided" for row in replay_calls),
            "oldRuntimeHookSawNgRandomCalls": len(runtime_random_rows) > 0,
            "oldRuntimeHookCapturedRandomHex": any(row.get("hasRandomHex") for row in runtime_random_rows),
            "s00TraceCapturedRandomHex": any(row.get("hasRandomHex") for row in s00_random_rows),
            "s00AfterNgObserved": bool(s00_after_ng),
            "offlineNgStillDiffersFromAcceptedAeax": random_record.get("output", {}).get("ngValue") != accepted_aeax,
        },
        "nextEvidenceNeeded": [
            "Run a browser observation after the import-return patch so hsprotect.captcha.wasm.import.return includes randomHex for each Ng getRandomValues/randomFillSync call.",
            "Feed that ordered randomHex sequence into tools/compute_wasm_nq_once.mjs --random-hex-seq and compare offline Ng to the same trace's hsprotect.captcha.tbr9.after_ng aeaxValue.",
        ],
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=2, ensure_ascii=False))
    print(json.dumps({"out": str(OUT), "checks": out["checks"]}, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
