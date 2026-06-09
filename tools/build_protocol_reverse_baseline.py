#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


REPO = Path("/Users/chaopenglv/data/me/Gpt-Agreement-Payment")
OUT_DIR = REPO / "output/protocol_reverse/baseline"


FILES = {
    "plan": REPO / "docs/pure-protocol-human-plan.md",
    "trace_success": REPO / "output/protocol_reverse/trace_classification_ni109xdjp5zp_1780948211.json",
    "trace_summary": REPO / "output/protocol_reverse/trace_classification_summary.json",
    "px561_compare": REPO / "output/protocol_reverse/px561_compare/px561_compare_success_vs_tf_samples.json",
    "collector_decode_success": REPO / "output/protocol_reverse/collector_decode/collector_decode_ni109xdjp5zp_1780948211.json",
    "pow_success": REPO / "output/protocol_reverse/pow_response/pow_response_ni109xdjp5zp_1780948211.json",
    "risk_success": REPO / "output/protocol_reverse/risk_verify/risk_verify_material_ni109xdjp5zp_1780948211.json",
    "captcha_state_fields": REPO / "output/protocol_reverse/source_offsets/captcha_state_submit_fields.json",
    "captcha_remaining_fields": REPO / "output/protocol_reverse/source_offsets/captcha_px561_remaining_fields.json",
    "collector_handlers": REPO / "output/protocol_reverse/px561_collector_handlers/px561_collector_handlers_ni109.json",
}


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def rel(path: Path) -> str:
    return str(path.relative_to(REPO))


def main() -> None:
    missing_files = [rel(path) for path in FILES.values() if not path.exists()]
    if missing_files:
        raise SystemExit(f"missing required evidence files: {missing_files}")

    trace_success = load_json(FILES["trace_success"])
    trace_summary = load_json(FILES["trace_summary"])
    px561 = load_json(FILES["px561_compare"])
    pow_success = load_json(FILES["pow_success"])
    risk_success = load_json(FILES["risk_success"])
    state_fields = load_json(FILES["captcha_state_fields"])
    remaining_fields = load_json(FILES["captcha_remaining_fields"])
    collector_handlers = load_json(FILES["collector_handlers"])

    success_d = px561["success"]["activity"]["d"]
    key_status = {
        "KVkYX28zG2o=": {
            "successValue": success_d.get("KVkYX28zG2o="),
            "staticEvidence": [
                "captcha_state_submit_fields.json: K[n(\"HGASKTZabC1xSx9T\")] = Hn[challengeTime]",
                "captcha_px561_remaining_fields.json: D submit extra key assigns d[key] = jz",
                "main.beautified.js:4504 decodes IooIoI rSplit[1] by ne(..., Vl)",
                "main.beautified.js:4640 sets Vl = 10",
            ],
            "currentStatus": "producer located; numeric value source can be closed by XOR evidence",
        },
        "Ew9iCVZkZD4=": {
            "successValue": success_d.get("Ew9iCVZkZD4="),
            "staticEvidence": [
                "captcha_state_submit_fields.json: K[key] = Hn[fakeToken]",
                "captcha.beautified.js:8154 assigns fakeToken = secondArg.token",
                "captcha.beautified.js:11031 builds secondArg[token] = yz",
                "main.beautified.js:4504 splits IooIoI rRaw by '_' and passes rSplit[0] into Hc/Zc path",
            ],
            "currentStatus": "producer located; bridge from main PX762 call to captcha callback argument still needs exact evidence",
        },
        "TBR9Ugl7emA=": {
            "successValue": success_d.get("TBR9Ugl7emA="),
            "staticEvidence": [
                "captcha_px561_remaining_fields.json: t(v(-540,-543)) decodes to TBR9Ugl7emA=",
                "captcha.beautified.js:11083 assigns r[key] = _s()",
            ],
            "currentStatus": "conflict: static expression is _s(); success value is a long string",
        },
    }

    ioo = collector_handlers["IooIoI"]["hcInputsBeforeRuntimeDecode"]
    encoded_delay = ioo.get("encodedDelaySource")
    decoded_delay = "".join(chr(ord(ch) ^ 10) for ch in encoded_delay) if encoded_delay else None

    result = {
        "objective": "完全纯协议解析 + 复现 HUMAN 成功包",
        "evidenceFiles": {name: rel(path) for name, path in FILES.items()},
        "traceBaseline": {
            "successTrace": {
                "path": trace_success["trace"],
                "status": trace_success["status"],
                "checks": trace_success["checks"],
                "counts": trace_success["counts"],
            },
            "summaryEntries": trace_summary,
            "warning": "trace_classification_summary.json does not include the older full success sample ni109; use trace_classification_ni109...json as authoritative success baseline.",
        },
        "collectorPowRiskBaseline": {
            "collectorSuccessHandler": trace_success["checks"].get("decoded_oIIoIooo_0"),
            "pow": pow_success["results"][0],
            "riskVerifyCounts": risk_success["counts"],
        },
        "px561Baseline": {
            "successSource": px561["success"]["source"],
            "successLine": px561["success"]["line"],
            "fieldCount": px561["success"]["fieldCount"],
            "state": px561["success"]["state"],
            "keyStatus": key_status,
            "iooIoI": {
                "collectorPart": collector_handlers["IooIoI"]["collectorPart"],
                "rSplit": ioo.get("rSplit"),
                "encodedDelaySource": encoded_delay,
                "decodedDelayByXor10": decoded_delay,
                "hashPrefix": ioo.get("observedHashPrefix"),
            },
        },
        "nextEvidenceRequired": [
            "Close exact bridge: main Zc/Lc PX762 call -> captcha-side callback arguments (r,n,t,v,e). Current Fu() evidence alone is insufficient because its visible key decodes to slice, not PX762.",
            "Resolve TBR9Ugl7emA= conflict by proving overwrite, serializer field shift, or alternate producer.",
            "After PX561 fields close, build offline collector body and only then live probe for oIIoIooo|0.",
        ],
        "sourceSnapshots": {
            "stateSubmitRecords": state_fields["records"],
            "stateInitRecords": state_fields["initRecords"],
            "remainingFieldRecords": remaining_fields["records"],
        },
    }

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    json_path = OUT_DIR / "protocol_reverse_baseline_latest.json"
    md_path = OUT_DIR / "protocol_reverse_baseline_latest.md"
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "# Protocol reverse baseline latest",
        "",
        "## evidence files",
        "",
    ]
    for name, path in result["evidenceFiles"].items():
        lines.append(f"- {name}: `{path}`")
    lines += [
        "",
        "## trace baseline",
        "",
        f"- success trace: `{result['traceBaseline']['successTrace']['path']}`",
        f"- status: `{result['traceBaseline']['successTrace']['status']}`",
        f"- warning: {result['traceBaseline']['warning']}",
        "",
        "## PX561 key status",
        "",
        "| key | success value | status |",
        "|---|---|---|",
    ]
    for key, item in key_status.items():
        value = item["successValue"]
        shown = value if not isinstance(value, str) or len(value) <= 96 else value[:96] + "..."
        lines.append(f"| `{key}` | `{shown}` | {item['currentStatus']} |")
    lines += [
        "",
        "## IooIoI delay evidence",
        "",
        f"- collector part: `{collector_handlers['IooIoI']['collectorPart']}`",
        f"- encoded delay source: `{encoded_delay}`",
        f"- `encodedDelaySource XOR 10`: `{decoded_delay}`",
        f"- success `KVkYX28zG2o=`: `{success_d.get('KVkYX28zG2o=')}`",
        "",
        "## next evidence required",
        "",
    ]
    for item in result["nextEvidenceRequired"]:
        lines.append(f"- {item}")
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(json.dumps({"json": rel(json_path), "md": rel(md_path)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
