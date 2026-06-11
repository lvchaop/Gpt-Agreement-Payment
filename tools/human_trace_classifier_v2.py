#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


REPO = Path("/Users/chaopenglv/data/me/Gpt-Agreement-Payment")
PROTO = REPO / "output/protocol_reverse"
OUT_DIR = PROTO / "trace_classification_v2"

TARGET_KEYS = [
    "Ew9iCVZkZD4=",
    "KVkYX28zG2o=",
    "fyNOZTpPQF4=",
    "AEAxBkUsPjQ=",
    "TBR9Ugl7emA=",
    "Bzt2fUFRcw==",
    "OSkIb39DDA==",
]

OBSERVATION_CONTROL_FILES = [
    PROTO / "source_offsets/tbr9_aeax_success_failure_reconciliation_20260611.json",
    PROTO / "source_offsets/tbr9_aeax_negative_control_b0_20260611.json",
]


def read_json(path: Path) -> Any | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def run_id_from_trace_classification(path: Path) -> str:
    return path.name.removesuffix(".json").removeprefix("trace_classification_")


def classify_stage(checks: dict[str, Any], counts: dict[str, Any]) -> str:
    success_chain = all(
        checks.get(k)
        for k in [
            "decoded_oIIoIooo_0",
            "dispatch_oIIoIooo_0",
            "ot_succeeded",
            "captcha_succeeded_event",
            "parent_postmessage_succeeded",
            "risk_verify_state_continue",
            "create_account_redirectUrl",
        ]
    )
    if success_chain:
        return "full_success_decoded"
    if (
        checks.get("ot_succeeded")
        and checks.get("captcha_succeeded_event")
        and checks.get("parent_postmessage_succeeded")
        and checks.get("risk_verify_state_continue")
        and checks.get("create_account_redirectUrl")
    ):
        return "browser_success_no_collector_decode"
    if checks.get("risk_verify_state_continue") and checks.get("create_account_redirectUrl"):
        return "microsoft_continue_no_human_decode"
    if counts.get("tf_payloads") or counts.get("full_chain_tf_payload_events"):
        return "tf_payload_failure_stage"
    if checks.get("captcha_succeeded_event") and checks.get("parent_postmessage_succeeded"):
        if counts.get("pow_hits"):
            return "captcha_success_pow_seen_no_risk"
        return "captcha_success_message_only"
    if checks.get("parent_postmessage_succeeded"):
        return "parent_success_message_only"
    return "no_success_evidence"


def source_version_index() -> dict[str, dict[str, Any]]:
    audit = read_json(PROTO / "source_offsets/hsprotect_source_version_audit.json") or {}
    out: dict[str, dict[str, Any]] = {}
    for run in audit.get("runs") or []:
        rid = run.get("run")
        if not rid:
            continue
        js_network = run.get("jsNetwork") or []
        main_etags = []
        captcha_etags = []
        main_urls = []
        captcha_urls = []
        for item in js_network:
            url = str(item.get("url") or "")
            etag = item.get("etag")
            if "main.min.js" in url:
                if etag and etag not in main_etags:
                    main_etags.append(etag)
                if url and url not in main_urls:
                    main_urls.append(url)
            if "captcha.js" in url:
                if etag and etag not in captcha_etags:
                    captcha_etags.append(etag)
                if url and url not in captcha_urls:
                    captcha_urls.append(url)
        out[rid] = {
            "sourceAuditPath": str((PROTO / "source_offsets/hsprotect_source_version_audit.json").resolve()),
            "mainEtags": main_etags,
            "captchaEtags": captcha_etags,
            "mainUrls": main_urls,
            "captchaUrls": captcha_urls,
            "stackUrlCount": run.get("stackUrlCount"),
        }
    return out


def summarize_bundle_activity(run_id: str) -> dict[str, Any]:
    path = PROTO / "bundle_activity_matches" / f"bundle_activity_matches_{run_id}.json"
    data = read_json(path)
    if data is None:
        return {"path": str(path.resolve()), "exists": False}
    requests_summary = []
    px561_targets: list[dict[str, Any]] = []
    for req in data.get("requests") or []:
        req_summary = {
            "requestLine": req.get("requestLine"),
            "seq": req.get("seq"),
            "url": req.get("url"),
            "payloadLen": req.get("payloadLen"),
            "markerMatch": req.get("markerMatch"),
            "jsonItemCount": req.get("jsonItemCount"),
            "activitiesWithMatchesCount": len(req.get("activitiesWithMatches") or []),
        }
        requests_summary.append(req_summary)
        for item in req.get("activitiesWithMatches") or []:
            activity = item.get("activity") or {}
            d = activity.get("d") or {}
            if item.get("type") == "PX561" or activity.get("t") == "PX561":
                px561_targets.append(
                    {
                        "requestLine": req.get("requestLine"),
                        "seq": req.get("seq"),
                        "activityIndex": item.get("index"),
                        "dKeyCount": len(d),
                        "targetValues": {k: d.get(k) for k in TARGET_KEYS if k in d},
                        "targetPresence": {k: k in d for k in TARGET_KEYS},
                        "matches": item.get("matches") or [],
                    }
                )
    return {
        "path": str(path.resolve()),
        "exists": True,
        "requestCount": len(data.get("requests") or []),
        "requests": requests_summary,
        "px561Targets": px561_targets,
    }


def summarize_payload_chain(run_id: str) -> dict[str, Any]:
    path = PROTO / "payload_chain" / f"payload_chain_{run_id}.json"
    data = read_json(path)
    if data is None:
        return {"path": str(path.resolve()), "exists": False}
    matches = data.get("matches") or []
    return {
        "path": str(path.resolve()),
        "exists": True,
        "counts": data.get("counts") or {},
        "firstCollector": (data.get("collectorRequests") or [None])[0],
        "matchSummary": [
            {
                "requestLine": m.get("requestLine"),
                "tfLine": m.get("tfLine"),
                "exactPayloadMatch": m.get("exactPayloadMatch"),
                "seq": m.get("seq"),
                "ft": m.get("ft"),
                "en": m.get("en"),
                "optionalParams": m.get("optionalParams"),
            }
            for m in matches[:8]
        ],
    }


def summarize_cookie_timeline(run_id: str) -> dict[str, Any]:
    path = PROTO / "cookie_timeline" / f"cookie_timeline_{run_id}.json"
    data = read_json(path)
    if data is None:
        return {"path": str(path.resolve()), "exists": False}
    names: list[str] = []
    decoded_events = data.get("decodedEvents") or []
    for ev in decoded_events:
        name = ev.get("name")
        if name and name not in names:
            names.append(name)
    return {
        "path": str(path.resolve()),
        "exists": True,
        "counts": data.get("counts") or {},
        "decodedNames": names,
        "hasChallengeSuccess": "challenge_success" in names,
        "correlations": data.get("correlations") or [],
    }


def summarize_pow(run_id: str) -> dict[str, Any]:
    path = PROTO / "pow_response" / f"pow_response_{run_id}.json"
    data = read_json(path)
    if data is None:
        return {"path": str(path.resolve()), "exists": False}
    return {
        "path": str(path.resolve()),
        "exists": True,
        "powPartCount": data.get("powPartCount"),
        "resultCount": len(data.get("results") or []),
        "results": data.get("results") or [],
    }


def summarize_risk_verify(run_id: str) -> dict[str, Any]:
    path = PROTO / "risk_verify" / f"risk_verify_material_{run_id}.json"
    data = read_json(path)
    if data is None:
        return {"path": str(path.resolve()), "exists": False}
    risk = data.get("riskVerify") or []
    create = data.get("createAccount") or []
    token_links = data.get("tokenLinks") or []
    return {
        "path": str(path.resolve()),
        "exists": True,
        "counts": data.get("counts") or {},
        "riskRequestLines": [x.get("requestLine") for x in risk],
        "riskStates": [
            ((x.get("responseBody") or {}).get("state") if isinstance(x.get("responseBody"), dict) else None)
            for x in risk
        ],
        "createAccountRequestLines": [x.get("requestLine") for x in create],
        "createAccountHasRedirect": [
            "redirectUrl" in (x.get("responseBody") or {}) if isinstance(x.get("responseBody"), dict) else False
            for x in create
        ],
        "tokenLinkCount": len(token_links),
    }


def normalize_observation_control(path: Path) -> dict[str, Any] | None:
    data = read_json(path)
    if data is None:
        return {"path": str(path.resolve()), "exists": False}

    if "new_runtime_observation_sample" in data:
        sample = data["new_runtime_observation_sample"]
        create = sample.get("create_account") or {}
        pre_i = sample.get("pre_i_px561") or {}
        tf = sample.get("final_px561_tf_payload") or {}
        return {
            "path": str(path.resolve()),
            "exists": True,
            "run": sample.get("run"),
            "stage": "aeax_only_negative_control",
            "jsTrace": sample.get("js_internal_trace"),
            "runtimeTrace": sample.get("runtime_trace"),
            "preIHasTBR": bool(pre_i.get("hasTbrInSnapshot")),
            "preIHasAEAx": pre_i.get("aeaxLen") is not None,
            "finalTfHasTBR": bool(tf.get("hasTBR")),
            "finalTfHasAEAx": bool(tf.get("hasAEAx")),
            "cookieBridgeOk": bool((sample.get("cookie_bridge") or {}).get("ok")),
            "createAccountStatus": create.get("status"),
            "createAccountHasRedirect": bool(create.get("hasRedirect")),
            "createAccountErrorCode": create.get("error_code"),
            "createAccountErrorField": create.get("error_field"),
            "limitation": sample.get("limitation"),
        }

    run = data.get("run") or {}
    create = data.get("create_account") or {}
    pre_i = data.get("pre_i_px561") or {}
    final_tf = data.get("final_tf_payload") or {}
    px_activity = next((a for a in final_tf.get("activities") or [] if a.get("t") == "PX561"), {})
    error = create.get("error") or {}
    return {
        "path": str(path.resolve()),
        "exists": True,
        "run": run.get("id"),
        "stage": "aeax_only_negative_control",
        "jsTrace": run.get("js_internal_trace"),
        "runtimeTrace": run.get("runtime_trace"),
        "preIHasTBR": bool(pre_i.get("snapshot_has_tbr")),
        "preIHasAEAx": bool(pre_i.get("snapshot_has_aeax")),
        "finalTfHasTBR": bool(px_activity.get("hasTBR")),
        "finalTfHasAEAx": bool(px_activity.get("hasAEAx")),
        "cookieBridgeOk": bool((data.get("px_cookie_bridge") or {}).get("ok")),
        "createAccountStatus": create.get("status"),
        "createAccountHasRedirect": bool(create.get("hasRedirect")),
        "createAccountErrorCode": error.get("code"),
        "createAccountErrorField": error.get("field"),
        "limitation": data.get("conclusion"),
    }


def build_observation_controls() -> list[dict[str, Any]]:
    controls = []
    for path in OBSERVATION_CONTROL_FILES:
        item = normalize_observation_control(path)
        if item is not None:
            controls.append(item)
    return controls


def build_index() -> dict[str, Any]:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    source_versions = source_version_index()
    runs = []
    for path in sorted(PROTO.glob("trace_classification_*.json")):
        if path.name == "trace_classification_summary.json":
            continue
        tc = read_json(path) or {}
        run_id = run_id_from_trace_classification(path)
        checks = tc.get("checks") or {}
        counts = tc.get("counts") or {}
        runs.append(
            {
                "run": run_id,
                "stage": classify_stage(checks, counts),
                "traceClassificationPath": str(path.resolve()),
                "jsTrace": tc.get("trace"),
                "runtimeTrace": tc.get("runtime_trace"),
                "checks": checks,
                "counts": counts,
                "sourceVersion": source_versions.get(run_id, {"existsInSourceAudit": False}),
                "bundleActivity": summarize_bundle_activity(run_id),
                "payloadChain": summarize_payload_chain(run_id),
                "cookieTimeline": summarize_cookie_timeline(run_id),
                "pow": summarize_pow(run_id),
                "riskVerify": summarize_risk_verify(run_id),
            }
        )
    return {
        "repo": str(REPO),
        "targetKeys": TARGET_KEYS,
        "runCount": len(runs),
        "runs": runs,
        "observationControlCount": len([x for x in build_observation_controls() if x.get("exists")]),
        "observationControls": build_observation_controls(),
        "sourceVersionAudit": str((PROTO / "source_offsets/hsprotect_source_version_audit.json").resolve()),
    }


def md_value(value: Any, max_len: int = 140) -> str:
    text = json.dumps(value, ensure_ascii=False) if not isinstance(value, str) else value
    text = text.replace("\n", "\\n")
    if len(text) > max_len:
        return text[:max_len] + f"...<len={len(text)}>"
    return text


def write_markdown(index: dict[str, Any], path: Path) -> None:
    lines = [
        "# HUMAN trace classifier v2 evidence index",
        "",
        f"- repo: `{index['repo']}`",
        f"- runCount: `{index['runCount']}`",
        f"- observationControlCount: `{index.get('observationControlCount', 0)}`",
        f"- sourceVersionAudit: `{index['sourceVersionAudit']}`",
        "",
        "## stage summary",
        "",
        "| run | stage | main etag | captcha etag | tf payloads | POW hits/results | risk continue | create redirect | decoded cookies | PX561 target |",
        "|---|---|---|---|---:|---:|---:|---:|---:|---|",
    ]
    for run in index["runs"]:
        sv = run["sourceVersion"]
        rv_counts = (run["riskVerify"].get("counts") or {}) if run["riskVerify"].get("exists") else {}
        cookie_counts = (run["cookieTimeline"].get("counts") or {}) if run["cookieTimeline"].get("exists") else {}
        pow_result_count = run["pow"].get("resultCount") if run["pow"].get("exists") else 0
        px_targets = run["bundleActivity"].get("px561Targets") or []
        px_summary = "missing"
        if px_targets:
            target = px_targets[0]
            present = [k for k, v in (target.get("targetPresence") or {}).items() if v]
            px_summary = f"line {target.get('requestLine')} seq {target.get('seq')} keys {len(present)}/{len(TARGET_KEYS)}"
        lines.append(
            "| {run} | {stage} | {main} | {captcha} | {tf} | {powhits}/{powres} | {risk} | {redir} | {cookies} | {px} |".format(
                run=run["run"],
                stage=run["stage"],
                main=md_value(sv.get("mainEtags", ["missing"])),
                captcha=md_value(sv.get("captchaEtags", ["missing"])),
                tf=run["counts"].get("tf_payloads"),
                powhits=run["counts"].get("pow_hits"),
                powres=pow_result_count,
                risk=rv_counts.get("riskContinueResponses", "missing"),
                redir=run["checks"].get("create_account_redirectUrl"),
                cookies=cookie_counts.get("decodedCookieOrSuccessEvents", "missing"),
                px=px_summary,
            )
        )
    lines += ["", "## full success decoded target evidence", ""]
    for run in index["runs"]:
        if run["stage"] != "full_success_decoded":
            continue
        lines.append(f"### {run['run']}")
        lines.append("")
        lines.append(f"- traceClassification: `{run['traceClassificationPath']}`")
        lines.append(f"- bundleActivity: `{run['bundleActivity']['path']}`")
        lines.append(f"- cookieTimeline: `{run['cookieTimeline']['path']}`")
        lines.append(f"- riskVerify: `{run['riskVerify']['path']}`")
        lines.append("")
        for target in run["bundleActivity"].get("px561Targets") or []:
            lines.append(
                f"- PX561 target: requestLine=`{target.get('requestLine')}` seq=`{target.get('seq')}` "
                f"activityIndex=`{target.get('activityIndex')}` dKeyCount=`{target.get('dKeyCount')}`"
            )
            for key in TARGET_KEYS:
                lines.append(f"  - `{key}`: `{md_value((target.get('targetValues') or {}).get(key))}`")
        lines.append("")
    controls = [c for c in index.get("observationControls", []) if c.get("exists")]
    lines += ["", "## observation negative controls", ""]
    if not controls:
        lines.append("- none")
    else:
        lines += [
            "| run | stage | pre-i TBR | pre-i AEAx | tf TBR | tf AEAx | cookie bridge | CreateAccount | evidence |",
            "|---|---|---:|---:|---:|---:|---:|---|---|",
        ]
        for control in controls:
            create_summary = "status={status} redirect={redirect} error={code}/{field}".format(
                status=control.get("createAccountStatus"),
                redirect=control.get("createAccountHasRedirect"),
                code=control.get("createAccountErrorCode"),
                field=control.get("createAccountErrorField"),
            )
            lines.append(
                "| {run} | {stage} | {pre_tbr} | {pre_aeax} | {tf_tbr} | {tf_aeax} | {bridge} | {create} | `{path}` |".format(
                    run=control.get("run"),
                    stage=control.get("stage"),
                    pre_tbr=control.get("preIHasTBR"),
                    pre_aeax=control.get("preIHasAEAx"),
                    tf_tbr=control.get("finalTfHasTBR"),
                    tf_aeax=control.get("finalTfHasAEAx"),
                    bridge=control.get("cookieBridgeOk"),
                    create=create_summary,
                    path=control.get("path"),
                )
            )
    lines += [
        "## evidence gaps exposed by v2",
        "",
        "- `full_success_decoded` is currently proven only for `ni109xdjp5zp_1780948211`.",
        "- `fk8zn2nqhex1_1781115338` and `b0hnt0zycbpx_1781116322` are AEAx-only negative controls: they have pre-i/$c.yc/tf.payload evidence but CreateAccount returns `1059/humanCaptcha` instead of `redirectUrl`.",
        "- `sv2n3df1y8fi_1780946111` reaches browser/Microsoft success checks but has no decoded collector artifact in current v2 inputs.",
        "- `hcxwyrtiudbg_1780949301`, `whsnxy8ag5ji_1781017142`, and `i294e72kliud_1781017380` are tf.payload failure-stage controls, not success same-stage payloads.",
        "- Source etag evidence is available only for runs present in `hsprotect_source_version_audit.json`; all other runs are marked missing instead of inferred.",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    index = build_index()
    json_path = OUT_DIR / "human_trace_classifier_v2_summary.json"
    md_path = OUT_DIR / "human_trace_classifier_v2_summary.md"
    json_path.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
    write_markdown(index, md_path)
    print(json.dumps({"json": str(json_path), "md": str(md_path), "runCount": index["runCount"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
