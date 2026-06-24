#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
HYP = ROOT / "output/protocol_reverse/hypothesis_reframe"
GOAL = ROOT / "output/protocol_reverse/goal_audit"
MANIFEST = HYP / "coherent_encoder_variant_experiment_manifest.json"
OUT = GOAL / "coherent_encoder_variant_live_probe_audit.json"


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, doc: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")


def run_cmd(cmd: list[str], timeout: float) -> dict[str, Any]:
    started = time.time()
    proc = subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True, check=False, timeout=timeout)
    parsed = None
    if proc.stdout.strip().startswith("{"):
        parsed = json.loads(proc.stdout)
    return {
        "cmd": cmd,
        "returncode": proc.returncode,
        "startedAt": started,
        "endedAt": time.time(),
        "stdoutTail": proc.stdout[-12000:],
        "stderrTail": proc.stderr[-12000:],
        "parsedJson": parsed,
    }


def load_combo_from_attempt(attempt_summary: dict[str, Any]) -> dict[str, Any]:
    attempt_path = (((attempt_summary.get("parsedJson") or {}).get("json")))
    if not attempt_path:
        return {}
    attempt = read_json(Path(attempt_path))
    combo_path = (((attempt.get("steps") or {}).get("finalSeq5Seq6Combo") or {}).get("summary") or {}).get("json")
    if not combo_path:
        return {"attempt": attempt, "combo": {}}
    return {"attempt": attempt, "combo": read_json(Path(combo_path))}


def build() -> dict[str, Any]:
    manifest = read_json(MANIFEST)
    c_manifest = manifest.get("checks") or {}
    if c_manifest.get("readyForOneControlledFreshExperiment") is not True:
        return {
            "generatedAt": datetime.now(timezone.utc).isoformat(),
            "manifest": str(MANIFEST),
            "checks": {
                "manifestReady": False,
                "executed": False,
                "goalComplete": False,
            },
            "decision": {
                "goalComplete": False,
                "readyForFreshExperiment": False,
                "reason": "Manifest does not authorize the controlled experiment.",
            },
        }

    cmd = [
        "python3",
        "tools/run_human_first_failure_overlap_attempt.py",
        "--timeout",
        "45",
        "--run-final-combo",
        "--header-mode",
        "runtime-exact",
        "--aeax-source",
        "offline-ng",
        "--bzt-source",
        "solve",
        "--final-stack-source",
        "template",
        "--final-tail-source",
        "template",
        "--final-inner-uuid-source",
        "template",
        "--final-non-px-activity-source",
        "template",
        "--final-seq6-activity-source",
        "template",
        "--final-aeax-source",
        "template",
        "--final-bzt-source",
        "template",
        "--final-payload-uuid-source",
        "template",
        "--final-pc-uuid-source",
        "payload",
        "--final-marker-source",
        "fresh",
        "--final-form-outer-source",
        "fresh",
        "--final-payload-source",
        "built",
        "--final-pc-source",
        "computed",
        "--final-body-source",
        "built",
    ]
    execution = run_cmd(cmd, timeout=420)
    loaded = load_combo_from_attempt(execution)
    attempt = loaded.get("attempt") or {}
    combo = loaded.get("combo") or {}
    seq5 = ((combo.get("results") or {}).get("seq5") or {})
    seq6 = ((combo.get("results") or {}).get("seq6") or {})
    seq5_resp = seq5.get("response") or {}
    seq6_resp = seq6.get("response") or {}
    seq5_dec = seq5.get("decoded") or {}
    seq6_dec = seq6.get("decoded") or {}
    seq5_handlers = seq5_dec.get("handlers") or []
    seq6_handlers = seq6_dec.get("handlers") or []
    any_success = ((combo.get("checks") or {}).get("anySuccessHandler") is True)
    seq5_has_success = any(str(h.get("key") or "") == "oIIoIooo" and str(h.get("status") or "") == "0" for h in seq5_handlers if isinstance(h, dict))
    seq6_has_success = any(str(h.get("key") or "") == "oIIoIooo" and str(h.get("status") or "") == "0" for h in seq6_handlers if isinstance(h, dict))

    checks = {
        "manifestReady": True,
        "executed": execution.get("returncode") == 0,
        "attemptJsonExists": bool((execution.get("parsedJson") or {}).get("json")),
        "finalComboExists": bool(combo),
        "freshWebshareSession": str((execution.get("parsedJson") or {}).get("session") or "").startswith("ibtvqcnm-JP-"),
        "forcedFirstFailureResponseOrder": (attempt.get("checks") or {}).get("overlapSeq3ResponseFirst") is True,
        "seq4AfterOverlapPow": (attempt.get("checks") or {}).get("seq4AfterOverlap200Pow") is True,
        "seq5Http200": seq5_resp.get("status") == 200,
        "seq6Http200": seq6_resp.get("status") == 200,
        "seq5HasSuccess0": seq5_has_success,
        "seq6HasSuccess0": seq6_has_success,
        "anyCollectorSuccess": any_success or seq5_has_success or seq6_has_success,
        "seq5ReturnedDoEmpty": seq5_resp.get("bodyText") == "{\"do\":[]}\n",
        "seq5ReturnedMinusOne": any(str(h.get("key") or "") == "oIIoIooo" and str(h.get("status") or "") == "-1" for h in seq5_handlers if isinstance(h, dict)),
        "riskVerifyAttempted": False,
        "createAccountAttempted": False,
        "goalComplete": False,
    }

    return {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "manifest": str(MANIFEST),
        "purpose": "Run the one authorized coherent encoder variant fresh-session probe.",
        "command": cmd,
        "execution": execution,
        "artifacts": {
            "attempt": (execution.get("parsedJson") or {}).get("json"),
            "finalCombo": (((attempt.get("steps") or {}).get("finalSeq5Seq6Combo") or {}).get("summary") or {}).get("json") if attempt else None,
        },
        "checks": checks,
        "responseSummary": {
            "seq5": {
                "status": seq5_resp.get("status"),
                "bodyText": seq5_resp.get("bodyText"),
                "handlers": seq5_handlers,
                "materialChecks": ((seq5.get("material") or {}).get("checks")),
                "materialMeta": ((seq5.get("material") or {}).get("meta")),
            },
            "seq6": {
                "status": seq6_resp.get("status"),
                "bodyText": seq6_resp.get("bodyText"),
                "handlers": seq6_handlers,
            },
        },
        "decision": {
            "goalComplete": False,
            "readyForFreshExperiment": False,
            "recommendedExperiment": None,
            "nextArtifact": None,
            "nextScript": None,
            "reason": (
                "Collector success was observed; downstream risk/verify and CreateAccount replay must be run before claiming final PoC."
                if checks["anyCollectorSuccess"]
                else "The only authorized coherent encoder variant did not produce collector HUMAN success; no downstream risk/verify replay is justified from this probe."
            ),
        },
    }


def main() -> int:
    doc = build()
    write_json(OUT, doc)
    print(json.dumps({"json": str(OUT), "checks": doc["checks"], "artifacts": doc.get("artifacts"), "decision": doc["decision"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
