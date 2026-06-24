#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import importlib.util
import json
import urllib.parse
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "output/protocol_reverse/hypothesis_reframe/remaining_encoder_variant_build_matrix.json"
BUILDER = ROOT / "tools/probe_human_fresh_px561.py"
DECODE_TOOL = ROOT / "tools/decode_bundle_payload_with_marker.py"


STATE_PROBE = ROOT / "output/protocol_reverse/fresh_bundle_progression_probe/fresh_bundle_progression_probe_9acd2880-6677-11f1-8a37-62666cc2b93d_1781279943.json"
POW_JSON = ROOT / "output/protocol_reverse/pow_response/pow_response_fresh_bundle_progression_probe_9acd2880-6677-11f1-8a37-62666cc2b93d_1781279943.json"
NQ_JSON = ROOT / "output/protocol_reverse/wasm/compute_wasm_ng_nq_once_forced_overlap_final_9acd2880_1781279930_with_ng.json"


def load(rel: str) -> Any:
    return json.loads((ROOT / rel).read_text(encoding="utf-8"))


def load_module(path: Path, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def parse_form(body: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for part in str(body or "").split("&"):
        if not part:
            continue
        key, _, raw = part.partition("=")
        out[urllib.parse.unquote_plus(key)] = urllib.parse.unquote(raw)
    return out


def summarize_material(material: dict[str, Any], dec: Any) -> dict[str, Any]:
    body = material.get("body") or ""
    form = parse_form(body)
    meta = material.get("meta") or {}
    decoded = dec.decode_payload(form.get("payload", ""), meta.get("marker", ""), meta.get("payloadUuid") or form.get("uuid", ""))
    return {
        "bodySha256": sha(body),
        "bodyLenBytes": len(body.encode("utf-8")),
        "payloadSha256": sha(form.get("payload", "")),
        "payloadLen": len(form.get("payload", "")),
        "pc": form.get("pc"),
        "pcSha256": sha(form.get("pc", "")),
        "uuid": form.get("uuid"),
        "ci": form.get("ci"),
        "csSha256": sha(form.get("cs", "")),
        "marker": meta.get("marker"),
        "markerJo": meta.get("markerJo"),
        "markerSha256": sha(meta.get("marker") or ""),
        "checks": material.get("checks"),
        "metaSubset": {
            k: meta.get(k)
            for k in [
                "payloadUuidSource",
                "pcUuidSource",
                "markerSource",
                "formOuterSource",
                "payloadSource",
                "pcSource",
                "bodySource",
                "computedPc",
                "templatePc",
            ]
        },
        "decode": {
            "markerMatch": decoded.get("markerMatch"),
            "jsonError": decoded.get("jsonError"),
            "baseSha256": sha(decoded.get("base") or ""),
            "decodedTextSha256": sha(decoded.get("decodedText") or ""),
            "jsonItemCount": len(decoded.get("json")) if isinstance(decoded.get("json"), list) else None,
            "activityTypes": [a.get("t") for a in decoded.get("json")] if isinstance(decoded.get("json"), list) else [],
        },
    }


def main() -> int:
    coupled = load("output/protocol_reverse/hypothesis_reframe/coupled_encoder_variant_audit.json")
    encoded = load("output/protocol_reverse/hypothesis_reframe/encoded_payload_pc_form_diff_map.json")
    builder = load_module(BUILDER, "probe_human_fresh_px561")
    dec = load_module(DECODE_TOOL, "decode_bundle_payload_with_marker")

    variants = coupled.get("justifiedUntestedVariants") or []
    built = []
    for idx, variant in enumerate(variants):
        material = builder.build_material(
            send=False,
            include_proxy_authorization=False,
            header_mode="safe",
            aeax_source="template",
            bzt_source="template",
            bzt_value=None,
            template_line=922,
            runtime_line=933,
            seq="5",
            rsc="6",
            state_probe=STATE_PROBE,
            fresh_bundle=None,
            pow_json=POW_JSON,
            nq_json=NQ_JSON,
            ng_nq_json=NQ_JSON,
            stack_source="template",
            tail_source="template",
            inner_uuid_source="template",
            non_px_activity_source="template",
            payload_uuid_source=variant["payloadUuidSource"],
            pc_uuid_source=variant["pcUuidSource"],
            marker_source=variant["markerSource"],
            form_outer_source=variant["formOuterSource"],
            payload_source=variant["payloadSource"],
            pc_source=variant["pcSource"],
            body_source="built",
            stack_probe=None,
        )
        built.append({
            "index": idx,
            "variant": variant,
            "summary": summarize_material(material, dec),
        })

    # Compare built variants to the selected fresh and s00 summaries from encoded diff.
    selected_fresh = encoded.get("fresh", {}).get("form", {})
    s00 = encoded.get("s00", {}).get("form", {})
    selected_payload_sha = selected_fresh.get("payloadSha256")
    s00_payload_sha = s00.get("payloadSha256")
    selected_pc = selected_fresh.get("pc")
    s00_pc = s00.get("pc")
    for item in built:
        summary = item["summary"]
        item["comparison"] = {
            "payloadEqualsSelectedFresh": summary["payloadSha256"] == selected_payload_sha,
            "payloadEqualsS00": summary["payloadSha256"] == s00_payload_sha,
            "pcEqualsSelectedFresh": summary["pc"] == selected_pc,
            "pcEqualsS00": summary["pc"] == s00_pc,
            "decodedBaseEqualsSelectedFresh": summary["decode"]["baseSha256"] == encoded.get("fresh", {}).get("decoded", {}).get("baseSha256"),
            "decodedBaseEqualsS00": summary["decode"]["baseSha256"] == encoded.get("s00", {}).get("decoded", {}).get("baseSha256"),
        }

    unique_payloads = sorted({item["summary"]["payloadSha256"] for item in built})
    unique_pcs = sorted({item["summary"]["pc"] for item in built})
    template_payload_variants = [item for item in built if item["comparison"]["payloadEqualsS00"]]
    selected_payload_variants = [item for item in built if item["comparison"]["payloadEqualsSelectedFresh"]]

    result = {
        "purpose": "Offline-build the four remaining encoder variants and compare them to s00 and selected fresh without sending network traffic.",
        "plan": str(ROOT / "docs/pure-protocol-human-hypothesis-plan.md"),
        "inputs": {
            "coupledEncoderVariantAudit": str(ROOT / "output/protocol_reverse/hypothesis_reframe/coupled_encoder_variant_audit.json"),
            "encodedPayloadPcFormDiffMap": str(ROOT / "output/protocol_reverse/hypothesis_reframe/encoded_payload_pc_form_diff_map.json"),
            "builder": str(BUILDER),
        },
        "builtVariants": built,
        "summary": {
            "variantCount": len(built),
            "uniquePayloadCount": len(unique_payloads),
            "uniquePcCount": len(unique_pcs),
            "payloadEqualsS00VariantCount": len(template_payload_variants),
            "payloadEqualsSelectedFreshVariantCount": len(selected_payload_variants),
            "allDecodedBaseEqualS00": all(item["comparison"]["decodedBaseEqualsS00"] for item in built),
            "allDecodedBaseEqualSelectedFresh": all(item["comparison"]["decodedBaseEqualsSelectedFresh"] for item in built),
        },
        "decision": {
            "readyForFreshExperiment": False,
            "recommendedExperiment": None,
            "reason": "The four variants only change encoding/pc surfaces while preserving the same decoded base. They still form a family, not a single evidenced transition; network testing one would be arbitrary.",
            "nextArtifact": str(ROOT / "output/protocol_reverse/hypothesis_reframe/hypothesis_reframe_status.json"),
            "nextScript": str(ROOT / "tools/build_hypothesis_reframe_status.py"),
        },
        "checks": {
            "serverInternalAuditRequiresThisArtifact": (load("output/protocol_reverse/hypothesis_reframe/server_internal_state_gap_audit.json").get("decision") or {}).get("nextArtifact") == str(OUT),
            "builtAllRemainingVariants": len(built) == len(variants) == 4,
            "allDecodeMarkerMatch": all(item["summary"]["decode"]["markerMatch"] is True for item in built),
            "allDecodeJsonOk": all(item["summary"]["decode"]["jsonError"] is None for item in built),
            "allDecodedBaseEqualS00": all(item["comparison"]["decodedBaseEqualsS00"] for item in built),
            "variantFamilyNotSingle": len(built) > 1,
            "readyForFreshExperiment": False,
        },
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(OUT), "checks": result["checks"], "summary": result["summary"], "decision": result["decision"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
