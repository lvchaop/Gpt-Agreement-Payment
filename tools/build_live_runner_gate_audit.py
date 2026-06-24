#!/usr/bin/env python3
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
PROTO = ROOT / "output/protocol_reverse"
HYP = PROTO / "hypothesis_reframe"
RESET = PROTO / "reset_plan"
GOAL = PROTO / "goal_audit"
OUT = HYP / "live_runner_gate_audit.json"

INPUTS = {
    "proofScriptReproducibility": HYP / "proof_script_reproducibility_audit.json",
    "evidenceGateChain": GOAL / "pure_protocol_evidence_gate_chain_audit.json",
    "candidateIntake": HYP / "promoted_transition_candidate_intake.json",
    "resetTerminal": RESET / "reset_terminal_boundary_audit.json",
    "convergentEvidenceEntranceMatrix": HYP / "convergent_evidence_entrance_matrix.json",
    "manifestCoverageGap": HYP / "manifest_coverage_gap_audit.json",
    "minimalTransitionExperiment": HYP / "minimal_promoted_transition_experiment.json",
    "evidenceGatedPoc": GOAL / "evidence_gated_end_to_end_pure_protocol_poc.json",
    "finalReplayAudit": GOAL / "final_pure_protocol_replay_audit.json",
}

NETWORK_MARKERS = [
    "http.client.",
    "requests.",
    "httpx.",
    "urllib.request",
    "aiohttp",
    "HSPROTECT_PROXY_URL",
    "set_tunnel(",
    "--send",
    "fetch(",
    "axios",
    "WebSocket",
]

LIVE_NAME_RE = re.compile(r"(probe|live|fresh|webshare|direct|attempt|experiment|poc|replay)", re.I)

CURRENT_GATE_MARKERS = [
    "promotedSingleTransitionCandidateCount",
    "readyForFreshExperiment",
    "reset_terminal_boundary_audit.json",
    "promoted_transition_candidate_intake.json",
]

LEGACY_CONTROL_MARKERS = [
    "coherent_encoder_variant_experiment_manifest.json",
    "readyForOneControlledFreshExperiment",
]

AUTHORITATIVE_ENTRYPOINTS = {
    "run_minimal_promoted_transition_experiment.py",
    "run_evidence_gated_end_to_end_pure_protocol_poc.py",
    "build_final_pure_protocol_replay_audit.py",
}


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def checks(doc: dict[str, Any]) -> dict[str, Any]:
    return doc.get("checks") or {}


def rel(path: Path) -> str:
    return str(path.relative_to(ROOT))


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def invoked_scripts_from_rows(doc: dict[str, Any]) -> set[str]:
    out: set[str] = set()
    for row in (doc.get("rows") or doc.get("steps") or []):
        argv = row.get("argv") or []
        if not isinstance(argv, list):
            continue
        for arg in argv:
            if isinstance(arg, str) and arg.startswith("tools/"):
                out.add(arg)
    return out


def classify(path: Path, text: str, proof_invoked: set[str], gate_invoked: set[str]) -> dict[str, Any]:
    name = path.name
    r = rel(path)
    network_hits = [marker for marker in NETWORK_MARKERS if marker in text]
    live_name = LIVE_NAME_RE.search(name) is not None
    current_gate_hits = [marker for marker in CURRENT_GATE_MARKERS if marker in text]
    legacy_gate_hits = [marker for marker in LEGACY_CONTROL_MARKERS if marker in text]
    authoritative = name in AUTHORITATIVE_ENTRYPOINTS
    proof_called = r in proof_invoked
    gate_called = r in gate_invoked

    is_live_runner = bool(network_hits) and live_name
    has_current_gate = authoritative and len(current_gate_hits) >= 2
    has_legacy_gate = bool(legacy_gate_hits)
    proof_invoked_ungated = proof_called and is_live_runner and not has_current_gate and not has_legacy_gate
    gate_invoked_ungated = gate_called and is_live_runner and not has_current_gate and not has_legacy_gate

    if not is_live_runner:
        category = "not_live_network_runner"
        reason = "No live-runner filename plus network marker combination."
    elif has_current_gate:
        category = "current_authoritative_gated_entrypoint"
        reason = "Authoritative entrypoint checks promoted transition and readyForFreshExperiment before network execution."
    elif has_legacy_gate:
        category = "legacy_controlled_live_probe"
        reason = "Historical controlled live probe guarded by a superseded manifest; not a current experiment entrypoint."
    elif proof_called or gate_called:
        category = "problem_ungated_invoked_live_runner"
        reason = "Live/network runner is invoked by current proof or gate chain without current promoted-transition gate."
    else:
        category = "historical_ungated_live_runner_not_current_entrypoint"
        reason = "Historical live/probe script can send network when manually invoked, but current proof/gate chain does not call it."

    return {
        "path": r,
        "fileName": name,
        "isLiveRunner": is_live_runner,
        "networkHits": network_hits,
        "hasCurrentPromotedTransitionGate": has_current_gate,
        "hasLegacyControlGate": has_legacy_gate,
        "authoritativeEntrypoint": authoritative,
        "proofInvoked": proof_called,
        "gateChainInvoked": gate_called,
        "proofInvokedUngated": proof_invoked_ungated,
        "gateChainInvokedUngated": gate_invoked_ungated,
        "category": category,
        "reason": reason,
    }


def main() -> int:
    docs = {name: read_json(path) for name, path in INPUTS.items()}
    proof = docs["proofScriptReproducibility"]
    gate = docs["evidenceGateChain"]
    c_candidate = checks(docs["candidateIntake"])
    c_reset = checks(docs["resetTerminal"])
    c_convergent = checks(docs["convergentEvidenceEntranceMatrix"])
    c_manifest_gap = checks(docs["manifestCoverageGap"])
    c_minimal = checks(docs["minimalTransitionExperiment"])
    c_poc = checks(docs["evidenceGatedPoc"])
    c_final = checks(docs["finalReplayAudit"])

    proof_invoked = invoked_scripts_from_rows(proof)
    gate_invoked = invoked_scripts_from_rows(gate)

    rows = []
    for path in sorted(TOOLS.glob("*")):
        if path.suffix not in {".py", ".mjs", ".js"}:
            continue
        rows.append(classify(path, read_text(path), proof_invoked, gate_invoked))

    live_rows = [row for row in rows if row["isLiveRunner"]]
    authoritative_rows = [row for row in rows if row["authoritativeEntrypoint"]]
    current_gated = [row for row in live_rows if row["hasCurrentPromotedTransitionGate"]]
    legacy_gated = [row for row in live_rows if row["hasLegacyControlGate"]]
    proof_ungated = [row for row in live_rows if row["proofInvokedUngated"]]
    gate_ungated = [row for row in live_rows if row["gateChainInvokedUngated"]]
    historical_ungated = [
        row for row in live_rows
        if row["category"] == "historical_ungated_live_runner_not_current_entrypoint"
    ]

    no_current_network_attempt = (
        c_candidate.get("promotedSingleTransitionCandidateCount") in {None, 0}
        and c_reset.get("readyForFreshExperiment") is not True
        and c_convergent.get("recommendedNextEntranceCount") in {None, 0}
        and c_manifest_gap.get("proposalWorthyUnmanifestedDirectoryCount") in {None, 0}
        and c_minimal.get("networkAttemptExecuted") is not True
        and c_poc.get("networkAttemptExecuted") is not True
        and c_final.get("networkAttemptExecuted") is not True
    )

    checks_out = {
        "allInputsExist": all(path.exists() for path in INPUTS.values()),
        "scannedToolFileCount": len(rows),
        "liveRunnerCount": len(live_rows),
        "authoritativeHarnessCount": len(authoritative_rows),
        "authoritativeHarnessBlockedCount": (
            sum(1 for row in authoritative_rows if row["fileName"] == "run_minimal_promoted_transition_experiment.py" and c_minimal.get("networkAttemptExecuted") is not True)
            + sum(1 for row in authoritative_rows if row["fileName"] == "run_evidence_gated_end_to_end_pure_protocol_poc.py" and c_poc.get("networkAttemptExecuted") is not True)
            + sum(1 for row in authoritative_rows if row["fileName"] == "build_final_pure_protocol_replay_audit.py" and c_final.get("networkAttemptExecuted") is not True)
        ),
        "currentAuthoritativeGatedEntrypointCount": len(current_gated),
        "legacyControlledLiveProbeCount": len(legacy_gated),
        "historicalUngatedLiveRunnerNotCurrentEntrypointCount": len(historical_ungated),
        "proofInvokedUngatedLiveRunnerCount": len(proof_ungated),
        "gateChainInvokedUngatedLiveRunnerCount": len(gate_ungated),
        "candidateIntakePromotedCount": c_candidate.get("promotedSingleTransitionCandidateCount"),
        "resetReadyForFreshExperiment": c_reset.get("readyForFreshExperiment") is True,
        "convergentRecommendedNextEntranceCount": c_convergent.get("recommendedNextEntranceCount"),
        "manifestCoverageProposalWorthyUnmanifestedDirectoryCount": c_manifest_gap.get("proposalWorthyUnmanifestedDirectoryCount"),
        "minimalTransitionNetworkAttemptExecuted": c_minimal.get("networkAttemptExecuted") is True,
        "evidenceGatedPocNetworkAttemptExecuted": c_poc.get("networkAttemptExecuted") is True,
        "finalReplayNetworkAttemptExecuted": c_final.get("networkAttemptExecuted") is True,
        "currentNetworkAttemptBlocked": no_current_network_attempt,
        "readyForFreshExperiment": False,
        "goalComplete": False,
    }

    doc = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "purpose": "Static audit of live/fresh/probe/network-capable runner scripts so historical runners cannot be mistaken for current authorized experiment entrypoints.",
        "inputs": {name: str(path) for name, path in INPUTS.items()},
        "proofInvokedScripts": sorted(proof_invoked),
        "gateChainInvokedScripts": sorted(gate_invoked),
        "liveRunnerRows": live_rows,
        "authoritativeHarnessRows": authoritative_rows,
        "proofInvokedUngatedLiveRunners": proof_ungated,
        "gateChainInvokedUngatedLiveRunners": gate_ungated,
        "historicalUngatedLiveRunnersNotCurrentEntrypoints": historical_ungated,
        "checks": checks_out,
        "decision": {
            "goalComplete": False,
            "readyForFreshExperiment": False,
            "recommendedExperiment": None,
            "nextArtifact": None,
            "nextScript": None,
            "reason": (
                "Current proof/gate chain does not invoke ungated live runners; authoritative network entrypoints remain blocked because no promoted transition candidate exists."
            ),
        },
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"json": str(OUT), "checks": checks_out, "decision": doc["decision"]}, ensure_ascii=False, indent=2))
    return 0 if checks_out["allInputsExist"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
