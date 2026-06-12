#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


REPO = Path("/Users/chaopenglv/data/me/Gpt-Agreement-Payment")
PROTO = REPO / "output/protocol_reverse"
OUT_DIR = PROTO / "goal_audit"

BOOTSTRAP = PROTO / "fresh_bootstrap_probe/fresh_bootstrap_probe_c257e05c-65c3-11f1-a79e-62666cc2b93d_1781202687.json"
SECOND = PROTO / "fresh_second_probe/fresh_second_probe_c257e05c-65c3-11f1-a79e-62666cc2b93d_1781202699.json"
SEQUENCE = PROTO / "fresh_sequence_probe/fresh_sequence_probe_c257e05c-65c3-11f1-a79e-62666cc2b93d_1781202710.json"
FIRST_BUNDLE = PROTO / "fresh_bundle_probe/fresh_bundle_probe_c257e05c-65c3-11f1-a79e-62666cc2b93d_1781202721.json"
FIRST_POW = PROTO / "pow_response/pow_response_fresh_bundle_probe_c257e05c-65c3-11f1-a79e-62666cc2b93d_1781202721.json"
FIRST_NQ = PROTO / "wasm/compute_wasm_nq_once_fresh_history_c257e05c_1781202721_with_ng.json"
FIRST_PX = PROTO / "fresh_px561_probe/fresh_px561_probe_c257e05c-65c3-11f1-a79e-62666cc2b93d_1781202755.json"
FIRST_PX_STATE = PROTO / "fresh_px561_state/fresh_px561_probe_c257e05c-65c3-11f1-a79e-62666cc2b93d_1781202755_state_after_response.json"
POST_PROGRESS = PROTO / "fresh_bundle_progression_probe/fresh_bundle_progression_probe_c257e05c-65c3-11f1-a79e-62666cc2b93d_1781202775.json"
POST_POW = PROTO / "pow_response/pow_response_fresh_bundle_progression_probe_c257e05c-65c3-11f1-a79e-62666cc2b93d_1781202775.json"
POST_NQ = PROTO / "wasm/compute_wasm_nq_once_fresh_history_c257e05c_1781202775_with_ng.json"
SECOND_PX = PROTO / "fresh_px561_probe/fresh_px561_probe_c257e05c-65c3-11f1-a79e-62666cc2b93d_1781202813.json"


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def status(doc: dict[str, Any]) -> int | None:
    return (doc.get("response") or {}).get("status")


def handlers(doc: dict[str, Any]) -> list[str]:
    return list((doc.get("decoded") or {}).get("handlers") or [])


def success(doc: dict[str, Any]) -> bool:
    return (doc.get("decoded") or {}).get("hasSuccessHandler") is True


def pow_solved(path: Path) -> bool:
    doc = read_json(path)
    return any(row.get("matchesTarget") is True and row.get("value") for row in doc.get("results") or [])


def nq_checks(path: Path) -> dict[str, Any]:
    return read_json(path).get("checks") or {}


def px_summary(path: Path) -> dict[str, Any]:
    doc = read_json(path)
    meta = (doc.get("material") or {}).get("meta") or {}
    return {
        "path": str(path.resolve()),
        "sent": doc.get("sent"),
        "status": status(doc),
        "handlers": handlers(doc),
        "hasSuccessHandler": success(doc),
        "partsTail": ((doc.get("decoded") or {}).get("parts") or [])[-5:],
        "checks": (doc.get("material") or {}).get("checks"),
        "meta": {
            key: meta.get(key)
            for key in [
                "templateJsTraceLine",
                "seq",
                "rsc",
                "stateSource",
                "powSource",
                "nqSource",
                "newPxTail",
            ]
        },
    }


def build() -> dict[str, Any]:
    bootstrap = read_json(BOOTSTRAP)
    second = read_json(SECOND)
    sequence = read_json(SEQUENCE)
    first_bundle = read_json(FIRST_BUNDLE)
    first_px_state = read_json(FIRST_PX_STATE)
    post_progress = read_json(POST_PROGRESS)
    checks = {
        "bootstrapHttp200": status(bootstrap) == 200,
        "secondHttp200": status(second) == 200,
        "sequenceAllHttp200": all((step.get("response") or {}).get("status") == 200 for step in sequence.get("steps") or []),
        "firstBundleHttp200": status(first_bundle) == 200,
        "firstBundleHasPow": (first_bundle.get("decoded") or {}).get("hasPowResult") is True,
        "firstPowSolved": pow_solved(FIRST_POW),
        "firstNqComputed": nq_checks(FIRST_NQ).get("nqValueNonEmpty") is True and nq_checks(FIRST_NQ).get("usedPxUuidImportPath") is True,
        "firstPxSentAndRejected": status(read_json(FIRST_PX)) == 200 and success(read_json(FIRST_PX)) is False,
        "firstPxStateUpdated": (first_px_state.get("checks") or {}).get("px3Changed") is True and (first_px_state.get("checks") or {}).get("pxdeChanged") is True,
        "postProgressionAllHttp200": all((step.get("response") or {}).get("status") == 200 for step in post_progress.get("steps") or []),
        "postProgressionReturnedPow": any((step.get("decoded") or {}).get("hasPowResult") is True for step in post_progress.get("steps") or []),
        "postPowSolved": pow_solved(POST_POW),
        "postNqComputed": nq_checks(POST_NQ).get("nqValueNonEmpty") is True and nq_checks(POST_NQ).get("usedPxUuidImportPath") is True,
        "secondPxSentAndRejected": status(read_json(SECOND_PX)) == 200 and success(read_json(SECOND_PX)) is False,
    }
    return {
        "purpose": "Audit a clean fresh no-browser session that explicitly mirrors first PX561 failure shape before advancing to a second success-shape PX561 attempt.",
        "inputs": {
            "bootstrap": str(BOOTSTRAP.resolve()),
            "second": str(SECOND.resolve()),
            "sequence": str(SEQUENCE.resolve()),
            "firstBundle": str(FIRST_BUNDLE.resolve()),
            "firstPow": str(FIRST_POW.resolve()),
            "firstNq": str(FIRST_NQ.resolve()),
            "firstPx": str(FIRST_PX.resolve()),
            "firstPxState": str(FIRST_PX_STATE.resolve()),
            "postProgression": str(POST_PROGRESS.resolve()),
            "postPow": str(POST_POW.resolve()),
            "postNq": str(POST_NQ.resolve()),
            "secondPx": str(SECOND_PX.resolve()),
        },
        "firstPx": px_summary(FIRST_PX),
        "postProgression": {
            "path": str(POST_PROGRESS.resolve()),
            "statuses": [(step.get("response") or {}).get("status") for step in post_progress.get("steps") or []],
            "handlers": [(step.get("decoded") or {}).get("handlers") for step in post_progress.get("steps") or []],
            "hasPow": [(step.get("decoded") or {}).get("hasPowResult") for step in post_progress.get("steps") or []],
            "finalState": {key: (post_progress.get("finalState") or {}).get(key) for key in ["uuid", "jo", "ci", "cs", "powChallenge"]},
        },
        "secondPx": px_summary(SECOND_PX),
        "checks": checks,
        "conclusion": (
            "A clean fresh no-browser run reached first bundle POW, sent a line566-shaped first PX561 request with solved POW and offline Ws.NQ TBR9, "
            "received the expected rejection plus updated _px3/_pxde, then advanced seq3/seq4 to a new POW and sent a line922-shaped second PX561 request. "
            "The second request still returned oIIoIooo|-1. Therefore merely replaying the observed first-failure history before the success-shape request is not sufficient."
        ),
    }


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    result = build()
    out = OUT_DIR / "fresh_first_failure_history_audit.json"
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"json": str(out), "checks": result["checks"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
