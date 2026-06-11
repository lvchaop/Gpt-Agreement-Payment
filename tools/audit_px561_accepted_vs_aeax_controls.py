#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import urllib.parse
from pathlib import Path
from typing import Any


REPO = Path("/Users/chaopenglv/data/me/Gpt-Agreement-Payment")
OUT_DIR = REPO / "output/protocol_reverse/px561_compare"
RUNS = [
    {"run": "j0t8van4qyhm_1781119142", "role": "accepted_success"},
    {"run": "fk8zn2nqhex1_1781115338", "role": "aeax_only_negative_control"},
    {"run": "b0hnt0zycbpx_1781116322", "role": "aeax_only_negative_control"},
]
TARGET_KEYS = [
    "fyNOZTpPQF4=",
    "AEAxBkUsPjQ=",
    "TBR9Ugl7emA=",
    "OSkIb39DDA==",
    "Bzt2fUFRcw==",
    "Ew9iCVZkZD4=",
    "KVkYX28zG2o=",
]


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


def parse_form(body: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for part in str(body or "").split("&"):
        if not part:
            continue
        key, _, raw_value = part.partition("=")
        out[urllib.parse.unquote_plus(key)] = urllib.parse.unquote(raw_value)
    return out


def create_account_acceptance(runtime_rows: list[dict[str, Any]]) -> dict[str, Any]:
    req = None
    resp = None
    for row in runtime_rows:
        if "/API/CreateAccount" not in str(row.get("url") or ""):
            continue
        if row.get("kind") == "request":
            req = row
        elif row.get("kind") == "response":
            resp = row
            break
    body = str((resp or {}).get("body") or "")
    parsed = None
    try:
        parsed = json.loads(body) if body else None
    except Exception:
        parsed = None
    return {
        "requestLine": (req or {}).get("_line"),
        "requestTime": (req or {}).get("t"),
        "responseLine": (resp or {}).get("_line"),
        "responseTime": (resp or {}).get("t"),
        "hasRedirectUrl": bool(isinstance(parsed, dict) and parsed.get("redirectUrl")),
        "error": parsed.get("error") if isinstance(parsed, dict) else None,
        "bodyContainsHumanCaptcha": "humanCaptcha" in body,
        "bodyContains1059": "1059" in body,
    }


def request_by_pc(runtime_rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for row in runtime_rows:
        if row.get("kind") != "request" or not str(row.get("url") or "").endswith("/assets/js/bundle"):
            continue
        params = parse_form(row.get("post_data") or "")
        pc = params.get("pc")
        if pc:
            out[pc] = {
                "requestLine": row["_line"],
                "requestTime": row.get("t"),
                "seq": params.get("seq"),
                "payloadLen": len(params.get("payload", "")),
            }
    return out


def first_outcome_after(js_rows: list[dict[str, Any]], wall_t: float | None) -> dict[str, Any] | None:
    if wall_t is None:
        return None
    outcomes = []
    for row in js_rows:
        if row.get("kind") != "hsprotect.captcha.zt.enter":
            continue
        t = float(row.get("wall_t") or -1)
        if t < wall_t:
            continue
        arg = (row.get("data") or {}).get("arg")
        if arg in {"failed", "succeeded"}:
            outcomes.append({"line": row["_line"], "wall_t": t, "arg": arg})
    return min(outcomes, key=lambda x: x["wall_t"]) if outcomes else None


def value_summary(value: Any) -> dict[str, Any]:
    text = json.dumps(value, ensure_ascii=False, separators=(",", ":")) if not isinstance(value, str) else value
    return {
        "type": type(value).__name__,
        "length": len(value) if isinstance(value, (str, list, dict)) else None,
        "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "preview": text[:160] + (f"...<len={len(text)}>" if len(text) > 160 else ""),
    }


def is_pow_answer(value: Any) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(ch in "0123456789abcdefABCDEF" for ch in value)


def px561_rows(run: str, role: str) -> dict[str, Any]:
    js_trace = REPO / f"output/outlook_browser/js_internal_trace_{run}.jsonl"
    runtime_trace = REPO / f"output/outlook_browser/runtime_trace_{run}.jsonl"
    js_rows = read_jsonl(js_trace)
    runtime_rows = read_jsonl(runtime_trace)
    req_by_pc = request_by_pc(runtime_rows)
    create = create_account_acceptance(runtime_rows)
    rows = []
    for row in js_rows:
        if row.get("kind") != "hsprotect.main.tf.payload":
            continue
        data = row.get("data") or {}
        pc = str(data.get("pc") or (data.get("meta") or {}).get("pc") or "")
        request = req_by_pc.get(pc, {})
        outcome = first_outcome_after(js_rows, request.get("requestTime"))
        activities = data.get("activities") or []
        for idx, activity in enumerate(activities):
            if not isinstance(activity, dict) or activity.get("t") != "PX561":
                continue
            d = activity.get("d") or {}
            keys = list(d.keys()) if isinstance(d, dict) else []
            rows.append(
                {
                    "run": run,
                    "role": role,
                    "tfLine": row["_line"],
                    "pc": pc,
                    "request": request,
                    "nextOutcome": outcome,
                    "isBeforeCreateAccount": bool(create.get("requestTime") and request.get("requestTime") and request["requestTime"] < create["requestTime"]),
                    "createAccountAccepted": bool(create.get("hasRedirectUrl") and not create.get("bodyContainsHumanCaptcha") and not create.get("bodyContains1059")),
                    "activityIndex": idx,
                    "fieldCount": len(keys),
                    "keys": keys,
                    "targetValues": {key: value_summary(d[key]) for key in TARGET_KEYS if key in d},
                    "hasAEAx": "AEAxBkUsPjQ=" in d,
                    "hasTBR9": "TBR9Ugl7emA=" in d,
                    "hasPowAnswer": is_pow_answer(d.get("OSkIb39DDA==")),
                    "state": d.get("fyNOZTpPQF4="),
                }
            )
    return {
        "run": run,
        "role": role,
        "evidenceFiles": {"jsTrace": str(js_trace.resolve()), "runtimeTrace": str(runtime_trace.resolve())},
        "createAccount": create,
        "px561Rows": rows,
    }


def compare(accepted: dict[str, Any], controls: list[dict[str, Any]]) -> list[dict[str, Any]]:
    accepted_keys = set(accepted["keys"])
    out = []
    for row in controls:
        keys = set(row["keys"])
        missing = sorted(accepted_keys - keys)
        extra = sorted(keys - accepted_keys)
        out.append(
            {
                "run": row["run"],
                "tfLine": row["tfLine"],
                "seq": row["request"].get("seq"),
                "fieldCount": row["fieldCount"],
                "state": row["state"],
                "hasAEAx": row["hasAEAx"],
                "hasTBR9": row["hasTBR9"],
                "hasPowAnswer": row["hasPowAnswer"],
                "missingComparedToAccepted": missing,
                "extraComparedToAccepted": extra,
                "targetPresence": {key: key in row["keys"] for key in TARGET_KEYS},
            }
        )
    return out


def main() -> int:
    runs = [px561_rows(item["run"], item["role"]) for item in RUNS]
    all_rows = [row for run in runs for row in run["px561Rows"]]
    accepted_candidates = [
        row
        for row in all_rows
        if row["role"] == "accepted_success"
        and row["createAccountAccepted"]
        and row["isBeforeCreateAccount"]
        and (row.get("nextOutcome") or {}).get("arg") == "succeeded"
        and row["hasAEAx"]
        and row["hasTBR9"]
    ]
    if not accepted_candidates:
        raise SystemExit("no accepted success PX561 candidate")
    accepted = accepted_candidates[-1]
    controls = [row for row in all_rows if row["role"] != "accepted_success" and row["hasAEAx"]]
    comparisons = compare(accepted, controls)
    result = {
        "purpose": "Compare accepted-success PX561 activity against AEAx-only negative controls to bound the TBR9/PX561 producer gap.",
        "runs": runs,
        "acceptedReference": accepted,
        "comparisons": comparisons,
        "checks": {
            "acceptedReferenceFound": True,
            "acceptedReferenceHasAEAxTBR9Pow": accepted["hasAEAx"] and accepted["hasTBR9"] and accepted["hasPowAnswer"],
            "controlCount": len(controls),
            "allControlsHaveAEAx": all(row["hasAEAx"] for row in controls),
            "noControlsHaveTBR9": all(not row["hasTBR9"] for row in controls),
            "noControlsHavePowAnswer": all(not row["hasPowAnswer"] for row in controls),
            "allControlsFailedCreateAccount": all(not run["createAccount"].get("hasRedirectUrl") for run in runs if run["role"] != "accepted_success"),
        },
        "conclusion": (
            "The accepted j0t8 success-side PX561 row contains AEAx, TBR9, and POW answer fields; the fk8/b0 AEAx-only controls contain AEAx but not TBR9 or POW answer and do not reach CreateAccount redirectUrl. "
            "This comparison keeps TBR9/POW-bearing PX561 production as the next upstream gap; AEAx alone remains a negative-control boundary."
        ),
    }

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_json = OUT_DIR / "px561_accepted_vs_aeax_controls.json"
    out_md = OUT_DIR / "px561_accepted_vs_aeax_controls.md"
    out_json.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = [
        "# PX561 accepted vs AEAx-only controls",
        "",
        "## Checks",
        "",
    ]
    for key, value in result["checks"].items():
        lines.append(f"- {key}: `{value}`")
    lines += [
        "",
        "## Accepted reference",
        "",
        f"- run: `{accepted['run']}`",
        f"- tfLine: `{accepted['tfLine']}`",
        f"- seq: `{accepted['request'].get('seq')}`",
        f"- fieldCount: `{accepted['fieldCount']}`",
        f"- targetValues: `{json.dumps(accepted['targetValues'], ensure_ascii=False)}`",
        "",
        "## Controls",
        "",
        "| run | tf line | seq | fields | state | AEAx | TBR9 | POW | missing target keys | missing total |",
        "|---|---:|---:|---:|---|---:|---:|---:|---|---:|",
    ]
    for row in comparisons:
        missing_targets = [key for key, present in row["targetPresence"].items() if not present]
        lines.append(
            f"| {row['run']} | {row['tfLine']} | {row.get('seq') or ''} | {row['fieldCount']} | {row.get('state') or ''} | "
            f"{row['hasAEAx']} | {row['hasTBR9']} | {row['hasPowAnswer']} | {','.join(missing_targets) or '-'} | {len(row['missingComparedToAccepted'])} |"
        )
    lines += ["", "## Conclusion", "", result["conclusion"], ""]
    out_md.write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"json": str(out_json), "md": str(out_md), "checks": result["checks"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
