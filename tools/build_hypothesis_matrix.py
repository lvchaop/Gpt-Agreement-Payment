#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


REPO = Path("/Users/chaopenglv/data/me/Gpt-Agreement-Payment")
PROTO = REPO / "output/protocol_reverse"
OUT = PROTO / "hypothesis_reframe/hypothesis_matrix.json"
PAIR = PROTO / "hypothesis_reframe/selected_contrast_pair.json"


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def evidence(path: Path, claim: str, check_keys: list[str] | None = None) -> dict[str, Any]:
    doc = load_json(path)
    checks = doc.get("checks") if isinstance(doc.get("checks"), dict) else None
    selected = {k: checks.get(k) for k in check_keys} if checks and check_keys else checks
    return {
        "claim": claim,
        "path": str(path),
        "exists": path.exists(),
        "checks": selected,
        "conclusion": doc.get("conclusion"),
    }


def main() -> int:
    selected_pair = load_json(PAIR)
    goal = load_json(PROTO / "goal_audit/pure_protocol_goal_gap_audit.json")
    matrix = {
        "purpose": "Phase 2 hypothesis matrix for pure-protocol HUMAN success reframe.",
        "plan": str(REPO / "docs/pure-protocol-human-hypothesis-plan.md"),
        "selectedContrastPair": str(PAIR),
        "selectedContrastPairChecks": selected_pair.get("phase1Checks"),
        "hypotheses": {
            "H0_packet_not_portable": {
                "claim": "The accepted s00 line933 packet/body/payload/pc is bound to session-side state and cannot be reused as a static success artifact across fresh sessions.",
                "supportingEvidence": [
                    evidence(
                        PROTO / "goal_audit/s00_exact_success_replay_live_audit.json",
                        "Exact observed s00 line933 body SHA was replayed live, decoded cleanly, and returned oIIoIooo|-1 rather than oIIoIooo|0.",
                        [
                            "probeBodyShaMatchesObservedLine933",
                            "observedLine933WasSuccess",
                            "liveReplayReturnsFailure",
                            "liveReplayDoesNotReturnSuccess",
                        ],
                    ),
                    evidence(
                        PROTO / "goal_audit/forced_overlap_payload_pc_split_control_audit.json",
                        "Under fresh forced-overlap lineage, exact s00 seq5 payload+pc with fresh outer session fields returned {do:[]} and no oIIoIooo handler.",
                        [
                            "seq5PayloadAndPcExactS00",
                            "seq5FreshOuter",
                            "seq5ReturnedDoEmpty",
                            "seq5NoOIIoIooo",
                        ],
                    ),
                ],
                "contradictingEvidence": [],
                "missingEvidence": [
                    "No fresh no-browser run has produced collector oIIoIooo|0.",
                    "The exact server-side binding variable is not yet identified.",
                ],
                "currentStatus": "strongly_supported",
                "nextDecisiveTest": "Do not keep static packet replaying. Use collector_state_transition_diff_s00_vs_fresh.json to identify the first state divergence before accepted line933.",
            },
            "H1_body_visible_fields": {
                "claim": "The remaining rejection is caused by visible request body fields that can be fixed by field-level construction.",
                "supportingEvidence": [
                    evidence(
                        PROTO / "goal_audit/collector_request_build_exact_coverage_audit.json",
                        "Observed collector request bodies can be rebuilt exactly from captured material, so body construction is mechanically understood for observed samples.",
                        ["allRunsExact", "allRunsPayloadExact", "allRunsPcExact"],
                    )
                ],
                "contradictingEvidence": [
                    evidence(
                        PROTO / "goal_audit/forced_overlap_template_final_control_audit.json",
                        "Fresh forced-overlap final seq5/seq6 decoded activities equal s00 but still reject.",
                        ["finalDecodedActivitiesEqualS00", "finalStillRejected", "encodedPayloadPcOuterStillDiffer"],
                    ),
                    evidence(
                        PROTO / "goal_audit/h2_dual_activity_equal_control_audit.json",
                        "h2 control with seq5 and seq6 decoded request bodies equal to s00 still rejected.",
                        [
                            "seq5WholeActivitiesEqualS00Line922",
                            "seq5Px561FieldDiffZeroVsS00Line922",
                            "seq6WholeActivityEqualS00Line925",
                            "stillRejected",
                        ],
                    ),
                    evidence(
                        PROTO / "goal_audit/h2_fresh_tail_only_control_audit.json",
                        "Fresh server-bound POW/WASM tail fields alone did not fix rejection.",
                        None,
                    ),
                    evidence(
                        PROTO / "goal_audit/h2_fresh_stack_only_control_audit.json",
                        "Fresh same-session stack field alone did not fix rejection.",
                        None,
                    ),
                ],
                "missingEvidence": [
                    "A lineage-level comparison of state consumption is missing; body-field diffs alone no longer decide the next experiment.",
                ],
                "currentStatus": "weak_low_priority",
                "nextDecisiveTest": "Only revisit visible body fields if first_decisive_divergence.json proves a specific body-generation input divergence changes a later request or server expected state.",
            },
            "H2_transport_order": {
                "claim": "The rejection is primarily caused by IP, HTTP/2 multiplexing, stream order, or response timing.",
                "supportingEvidence": [],
                "contradictingEvidence": [
                    evidence(
                        PROTO / "goal_audit/direct_webshare_ip_hypothesis_audit.json",
                        "Direct Webshare session/IP rotation reached collector but all attempts rejected.",
                        [
                            "allAttemptsUseDirectWebshareEndpoint",
                            "allAttemptsReachedSeq5Collector",
                            "allAttemptsRejected",
                            "distinctEgressIpCount",
                            "hasAnySuccessRow",
                        ],
                    ),
                    evidence(
                        PROTO / "goal_audit/h2_seq6_response_before_seq5_body_control_audit.json",
                        "One h2 TLS session, stream 1/3, full seq6 response before seq5 body, first-failure state, captcha HEAD delay, and fresh server-bound tail still rejected.",
                        [
                            "h2SingleSessionStream1And3",
                            "seq6ResponseEndedBeforeSeq5",
                            "seq5StillRejected",
                            "seq6HasCookieTokenHandlers",
                        ],
                    ),
                    evidence(
                        PROTO / "goal_audit/forced_first_failure_response_order_control_audit.json",
                        "Forced first-failure response order to match s00, then final seq5 still rejected.",
                        [
                            "forcedFirstFailureMatchesS00ResponseOrder",
                            "seq4AfterForcedOverlapReturnedPow",
                            "finalH2Seq6BeforeSeq5Body",
                            "finalSeq5StillRejected",
                        ],
                    ),
                ],
                "missingEvidence": [
                    "Transport can only be revived if state diff proves body/state are identical and transport is the first remaining divergence.",
                ],
                "currentStatus": "mostly_ruled_out_as_primary",
                "nextDecisiveTest": "Do not run more h2/IP permutations unless collector_state_transition_diff proves transport is the first decisive divergence.",
            },
            "H3_collector_server_state": {
                "claim": "s00 experienced a collector-visible state transition before line933 that the no-browser fresh session did not reproduce, so server expected state differs.",
                "supportingEvidence": [
                    evidence(
                        PROTO / "goal_audit/forced_overlap_template_final_control_audit.json",
                        "Response ordering plus decoded final activity equality still rejected, leaving encoded/session/server-state binding as the remaining boundary.",
                        ["finalDecodedActivitiesEqualS00", "finalStillRejected"],
                    ),
                    evidence(
                        PROTO / "goal_audit/s00_seq6_to_seq5_success_bridge_window_audit.json",
                        "Narrow accepted window has no missing runtime network request, suggesting divergence may be earlier in state lineage rather than between seq6 response and seq5 success.",
                        [
                            "runtimeWindowHasNoRequests",
                            "runtimeWindowHasOnlySeq6AndSeq5Responses",
                            "parentBridgeValuesCorrelateToLine926",
                            "successLine948Observed",
                        ],
                    ),
                    evidence(
                        PROTO / "cookie_jar/px_cookie_jar_updater_multi_audit.json",
                        "Decoded px events can reconstruct risk/verify-visible cookie jar for browser traces, so response-handler state is a valid comparison axis.",
                        [
                            "allRunsHaveDecodedPxEvents",
                            "allRunsHaveCorrelatedPx3PxdePxvid",
                            "allRunsRiskProviderMetadataValuesMatchJar",
                            "anyRunProvesContinueRiskVerifyMatchesJar",
                        ],
                    ),
                ],
                "contradictingEvidence": [],
                "missingEvidence": [
                    "collector_state_transition_diff_s00_vs_fresh.json is not built yet.",
                    "first_decisive_divergence.json is not built yet.",
                    "No minimal divergence experiment has been run under the new method.",
                ],
                "currentStatus": "primary_open_hypothesis",
                "nextDecisiveTest": "Build collector_state_transition_diff_s00_vs_fresh.json from the selected contrast pair and extract first_decisive_divergence.json.",
            },
            "H4_browser_runtime_state": {
                "claim": "Accepted line933 generation or acceptance depends on browser-only runtime state outside network body, such as worker/postMessage/iframe/in-memory state.",
                "supportingEvidence": [
                    evidence(
                        PROTO / "goal_audit/s00_seq6_to_seq5_success_bridge_window_audit.json",
                        "s00 parent bridge carries _px3/_pxde values correlated to decoded seq6 response immediately before success.",
                        ["parentBridgeCarriesSeq6Px3Pxde", "parentBridgeValuesCorrelateToLine926"],
                    ),
                    evidence(
                        PROTO / "goal_audit/crcldu_sync_message_boundary_audit.json",
                        "crcldu sync appears as browser/third-frame state artifact without observed direct collector network side effect.",
                        None,
                    ),
                ],
                "contradictingEvidence": [
                    evidence(
                        PROTO / "goal_audit/s00_seq6_to_seq5_success_bridge_window_audit.json",
                        "There is no missing runtime network request in the immediate seq6-response to seq5-success window.",
                        ["runtimeWindowHasNoRequests"],
                    )
                ],
                "missingEvidence": [
                    "accepted_line933_generation_lineage.json is not built yet.",
                    "tf.payload upstream input lineage has not been compared against the selected fresh sample.",
                ],
                "currentStatus": "secondary_open_hypothesis",
                "nextDecisiveTest": "If H3 collector-visible diff does not explain rejection, build accepted_line933_generation_lineage.json and compare browser-only payload inputs.",
            },
            "H5_ms_context_binding": {
                "claim": "Collector acceptance is bound to Microsoft page/risk context outside hsprotect collector state.",
                "supportingEvidence": [],
                "contradictingEvidence": [
                    evidence(
                        PROTO / "risk_verify_build/risk_verify_build_ni109xdjp5zp_1780948211.json",
                        "Risk/verify request material can be rebuilt from observed browser state, but this does not prove collector acceptance independence.",
                        None,
                    )
                ],
                "missingEvidence": [
                    "No dedicated Microsoft context lineage diff has been built for s00 accepted request vs selected fresh request.",
                    "Collector app/session to Microsoft challenge/risk binding is not mapped.",
                ],
                "currentStatus": "open_lower_priority",
                "nextDecisiveTest": "Only after H3/H4 fail to explain divergence, build Microsoft context lineage diff around collector acceptance and risk/verify.",
            },
        },
        "decision": {
            "primaryNextHypothesis": "H3_collector_server_state",
            "nextArtifact": str(PROTO / "hypothesis_reframe/collector_state_transition_diff_s00_vs_fresh.json"),
            "nextScript": str(REPO / "tools/build_collector_state_transition_diff.py"),
            "doNotRunFreshExperimentUntil": str(PROTO / "hypothesis_reframe/first_decisive_divergence.json"),
        },
        "goalAuditSummary": (goal.get("summary") or {}),
    }
    checks = {
        "selectedContrastPairExists": PAIR.exists(),
        "allHypothesesPresent": set(matrix["hypotheses"]) == {
            "H0_packet_not_portable",
            "H1_body_visible_fields",
            "H2_transport_order",
            "H3_collector_server_state",
            "H4_browser_runtime_state",
            "H5_ms_context_binding",
        },
        "primaryNextIsH3": matrix["decision"]["primaryNextHypothesis"] == "H3_collector_server_state",
        "noFreshExperimentBeforeDivergence": matrix["decision"]["doNotRunFreshExperimentUntil"].endswith("first_decisive_divergence.json"),
    }
    matrix["checks"] = checks
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(matrix, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"json": str(OUT), "checks": checks, "decision": matrix["decision"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
