#!/usr/bin/env python3
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
PLAN = ROOT / "docs/pure-protocol-human-methodological-execution-plan.md"
OUT = ROOT / "output/protocol_reverse/hypothesis_reframe/non_json_evidence_blindspot_audit.json"

SCAN_ROOTS = [
    ROOT / "output/protocol_reverse",
    ROOT / "output/outlook_browser",
    ROOT / "output/run_logs",
    ROOT / "output/evidence_packages",
]

TEXT_SUFFIXES = {
    ".log",
    ".txt",
    ".md",
    ".html",
    ".jsonl",
    ".har",
    ".patch",
}

SUCCESS_PATTERNS = [
    "oIIoIooo|0",
    '"hasSuccessHandler": true',
    "hasSuccessHandler: true",
    '"risk_verify_state_continue": true',
    '"create_account_redirectUrl": true',
    '"redirectUrl"',
    "state=continue",
]

NEGATIVE_PATTERNS = [
    "oIIoIooo|-1",
    '"hasSuccessHandler": false',
    "hasSuccessHandler: false",
    "tf_payload_failure_stage",
    "AEAx-only",
]

PURE_PROTOCOL_HINTS = [
    "pure-protocol",
    "pure_protocol",
    "no-browser",
    "no_browser",
    "direct_webshare",
    "collector_live_probe",
    "fresh_sequence",
    "fresh_bundle",
    "fresh_px561",
    "fresh_second",
    "fresh_bootstrap",
    "seq5",
    "seq6",
]

BROWSER_HINTS = [
    "browser_sampling",
    "outlook_browser",
    "camoufox",
    "runtime_success",
    "runtime_trace",
    "js_internal_trace",
    "challenge_after_press",
    "challenge_initial",
    "browser success",
]

REFERENCE_HINTS = [
    "baseline",
    "plan",
    "manifest",
    "README",
    "docs/",
    "goal_audit",
    "cookie_jar",
    "analysis",
    "evidence_package",
    "package_manifest",
]

NEGATIVE_CONCLUSION_HINTS = [
    "responsehassuccesshandler` | `false",
    "responsehassuccesshandler: false",
    "has no oIIoIooo|0",
    "not a human success packet",
    "not the end-to-end pure protocol human success poc",
    "but not the end-to-end pure protocol human success poc",
    "pureprotocolready: `false",
    "pureprotocolready` | `false",
    "pure protocolready` | `false",
    "current evidence does not support",
    "post-success effect",
]

MAX_READ_BYTES = 2_000_000


def rel(path: Path) -> str:
    return str(path.relative_to(ROOT))


def safe_read_text(path: Path) -> tuple[str, bool, str | None]:
    try:
        data = path.read_bytes()[:MAX_READ_BYTES]
    except OSError as exc:
        return "", False, f"read_error:{exc}"
    if b"\x00" in data[:4096]:
        return "", False, "binary_nul"
    try:
        return data.decode("utf-8"), True, None
    except UnicodeDecodeError:
        try:
            return data.decode("utf-8", errors="ignore"), True, "utf8_decode_ignored_errors"
        except Exception as exc:  # pragma: no cover - defensive
            return "", False, f"decode_error:{exc}"


def classify(path: Path, text: str, success_hits: list[str], negative_hits: list[str]) -> tuple[str, bool, str]:
    path_s = rel(path)
    lowered = (path_s + "\n" + text[:20000]).lower()

    has_browser = any(h.lower() in lowered for h in BROWSER_HINTS)
    has_reference = any(h.lower() in lowered for h in REFERENCE_HINTS)
    has_pure = any(h.lower() in lowered for h in PURE_PROTOCOL_HINTS)
    has_negative_conclusion = any(h in lowered for h in NEGATIVE_CONCLUSION_HINTS)

    if has_browser:
        return (
            "browser_runtime_or_sampling_reference",
            False,
            "Contains browser/Camoufox/runtime/browser-sampling markers; success tokens here are not replayable no-browser proof.",
        )

    if "output/evidence_packages/" in path_s and ("runtime_success" in path_s or "outlook_browser" in lowered):
        return (
            "packaged_browser_evidence_reference",
            False,
            "Evidence package contains captured browser evidence, not an independently replayable pure-protocol success.",
        )

    if has_negative_conclusion:
        return (
            "derived_audit_negative_or_post_success_reference",
            False,
            "The artifact contains success-like text only inside an audit that explicitly says the path is negative, incomplete, or post-success.",
        )

    if has_reference:
        return (
            "documentation_or_manifest_reference",
            False,
            "Documentation/manifest/baseline files may mention success criteria or browser success, but are not live no-browser replay output.",
        )

    if has_pure and success_hits and not negative_hits:
        return (
            "pure_protocol_success_candidate_unclassified",
            True,
            "Pure-protocol hints and success tokens were found without a negative token; requires manual review before promotion.",
        )

    if has_pure:
        return (
            "pure_protocol_probe_or_log",
            False,
            "Pure-protocol probe/log file either has no success token or contains negative evidence; not a replayable success proof.",
        )

    if success_hits:
        return (
            "unclassified_success_signal",
            True,
            "Success-like token appeared outside known browser/reference/pure-protocol categories.",
        )

    return (
        "non_success_text_artifact",
        False,
        "No success-like token found.",
    )


def iter_files() -> list[Path]:
    files: list[Path] = []
    seen: set[Path] = set()
    for root in SCAN_ROOTS:
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            if path.suffix.lower() not in TEXT_SUFFIXES:
                continue
            resolved = path.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            files.append(path)
    return sorted(files)


def build() -> dict[str, Any]:
    files = iter_files()
    rows: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    category_counts: dict[str, int] = {}
    success_signal_rows: list[dict[str, Any]] = []
    unclassified_rows: list[dict[str, Any]] = []
    replayable_rows: list[dict[str, Any]] = []

    for path in files:
        text, readable, read_note = safe_read_text(path)
        if not readable:
            skipped.append({"path": rel(path), "reason": read_note})
            continue

        success_hits = [pat for pat in SUCCESS_PATTERNS if pat in text]
        negative_hits = [pat for pat in NEGATIVE_PATTERNS if pat in text]
        category, unclassified, reason = classify(path, text, success_hits, negative_hits)
        category_counts[category] = category_counts.get(category, 0) + 1

        row = {
            "path": rel(path),
            "suffix": path.suffix.lower(),
            "size": path.stat().st_size,
            "category": category,
            "successHits": success_hits,
            "negativeHits": negative_hits,
            "isUnclassifiedSuccessSignal": unclassified,
            "isReplayableFreshNoBrowserSuccessEvidence": False,
            "reason": reason,
        }
        rows.append(row)
        if success_hits:
            success_signal_rows.append(row)
        if unclassified:
            unclassified_rows.append(row)
        if row["isReplayableFreshNoBrowserSuccessEvidence"]:
            replayable_rows.append(row)

    browser_reference_success = [
        r for r in success_signal_rows if r["category"] in {"browser_runtime_or_sampling_reference", "packaged_browser_evidence_reference"}
    ]
    reference_success = [r for r in success_signal_rows if r["category"] == "documentation_or_manifest_reference"]
    pure_protocol_success_candidates = [
        r for r in success_signal_rows if r["category"] in {"pure_protocol_success_candidate_unclassified", "pure_protocol_probe_or_log"}
    ]

    checks = {
        "planExists": PLAN.exists(),
        "scanRootCount": len([p for p in SCAN_ROOTS if p.exists()]),
        "scannedTextFileCount": len(rows),
        "skippedFileCount": len(skipped),
        "categoryCount": len(category_counts),
        "successSignalFileCount": len(success_signal_rows),
        "browserReferenceSuccessSignalCount": len(browser_reference_success),
        "documentationOrManifestSuccessSignalCount": len(reference_success),
        "pureProtocolSuccessSignalFileCount": len(pure_protocol_success_candidates),
        "unclassifiedSuccessSignalCount": len(unclassified_rows),
        "replayableFreshNoBrowserSuccessEvidenceCount": len(replayable_rows),
        "hasReplayableFreshNoBrowserSuccessEvidence": bool(replayable_rows),
        "readyForFreshExperiment": False,
        "goalComplete": False,
    }

    return {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "plan": str(PLAN),
        "purpose": "Audit non-JSON local text evidence for fresh no-browser HUMAN success signals missed by JSON-only scans.",
        "scanRoots": [str(p) for p in SCAN_ROOTS],
        "textSuffixes": sorted(TEXT_SUFFIXES),
        "checks": checks,
        "categoryCounts": dict(sorted(category_counts.items())),
        "successSignalRows": success_signal_rows,
        "unclassifiedSuccessSignalRows": unclassified_rows,
        "replayableFreshNoBrowserSuccessRows": replayable_rows,
        "skippedRows": skipped[:200],
        "decision": {
            "goalComplete": False,
            "readyForFreshExperiment": False,
            "recommendedExperiment": None,
            "reason": (
                "Non-JSON text/log/HAR/markdown/html/jsonl evidence did not produce a replayable fresh no-browser success artifact. "
                "Any network run still requires a single pre-accept, client-visible, pure-protocol constructible transition candidate."
            ),
        },
    }


def main() -> int:
    doc = build()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"json": str(OUT), "checks": doc["checks"], "decision": doc["decision"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
