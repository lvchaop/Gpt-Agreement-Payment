#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
PROTO = ROOT / "output/protocol_reverse"
GOAL = PROTO / "goal_audit"
MANIFEST = GOAL / "pure_protocol_evidence_manifest.json"
OUT = GOAL / "pure_protocol_evidence_manifest_verify.json"
PLAN = ROOT / "docs/pure-protocol-human-evidence-gated-implementation-plan.md"


def sha256(path: Path) -> str | None:
    if not path.exists() or not path.is_file():
        return None
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    manifest = read_json(MANIFEST)
    rows: list[dict[str, Any]] = []
    for item in manifest.get("files") or []:
        path = Path(item.get("path") or "")
        actual = sha256(path)
        rows.append(
            {
                "id": item.get("id"),
                "path": str(path),
                "exists": path.exists(),
                "expectedSha256": item.get("sha256"),
                "actualSha256": actual,
                "sha256Matches": actual == item.get("sha256"),
                "expectedSize": item.get("size"),
                "actualSize": path.stat().st_size if path.exists() else None,
            }
        )

    mismatches = [row for row in rows if row.get("sha256Matches") is not True]
    missing = [row for row in rows if row.get("exists") is not True]
    checks = {
        "manifestExists": MANIFEST.exists(),
        "manifestFileCount": len(manifest.get("files") or []),
        "verifiedFileCount": len(rows),
        "missingFileCount": len(missing),
        "hashMismatchCount": len(mismatches),
        "allFilesExist": not missing and bool(rows),
        "allHashesMatch": not mismatches and bool(rows),
        "manifestGoalComplete": (manifest.get("checks") or {}).get("goalComplete") is True,
        "goalComplete": False,
        "readyForFreshExperiment": False,
    }

    doc = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "plan": str(PLAN),
        "purpose": "Verify current files against pure_protocol_evidence_manifest.json hashes.",
        "manifest": str(MANIFEST),
        "checks": checks,
        "rows": rows,
        "mismatches": mismatches,
        "decision": {
            "goalComplete": False,
            "readyForFreshExperiment": False,
            "recommendedExperiment": None,
            "nextArtifact": None,
            "nextScript": None,
            "reason": (
                "Manifest verification passed; current files match the recorded hashes."
                if checks["allHashesMatch"]
                else "Manifest verification found file drift; regenerate the manifest only after the drift is intentional and audited."
            ),
        },
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"json": str(OUT), "checks": checks, "decision": doc["decision"]}, ensure_ascii=False, indent=2))
    return 0 if checks["allHashesMatch"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
