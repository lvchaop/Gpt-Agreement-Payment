#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import time
import urllib.parse
from pathlib import Path
from typing import Any


REPO = Path("/Users/chaopenglv/data/me/Gpt-Agreement-Payment")
ATTEMPT_DIR = REPO / "output/protocol_reverse/direct_webshare_attempt"
OUT_DIR = REPO / "output/protocol_reverse/goal_audit"


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def redacted_proxy(session: str, host: str, port: int) -> str:
    return f"http://{session}:***@{host}:{port}"


def proxy_url(session: str, password: str, host: str, port: int) -> str:
    return f"http://{urllib.parse.quote(session, safe='')}:{urllib.parse.quote(password, safe='')}@{host}:{port}"


def curl_ip(session: str, password: str, host: str, port: int, url: str, timeout: int) -> dict[str, Any]:
    proxy = proxy_url(session, password, host, port)
    cmd = [
        "curl",
        "-sS",
        "--max-time",
        str(timeout),
        "--proxy",
        proxy,
        "-w",
        "\n%{http_code} %{remote_ip} %{time_total}",
        url,
    ]
    proc = subprocess.run(cmd, text=True, capture_output=True, timeout=timeout + 5)
    stdout = proc.stdout.strip()
    lines = stdout.splitlines()
    body = "\n".join(lines[:-1]).strip() if len(lines) > 1 else ""
    meta = lines[-1].split() if lines else []
    return {
        "cmdRedacted": [redacted_proxy(session, host, port) if part == proxy else part for part in cmd],
        "returncode": proc.returncode,
        "targetUrl": url,
        "body": body,
        "httpCode": meta[0] if len(meta) > 0 else None,
        "remoteIp": meta[1] if len(meta) > 1 else None,
        "timeTotal": meta[2] if len(meta) > 2 else None,
        "stderrTail": proc.stderr[-1000:],
    }


def summarize_attempt(path: Path) -> dict[str, Any]:
    doc = load_json(path)
    combo = (
        doc.get("combo")
        or (((doc.get("steps") or {}).get("seq5Seq6Combo") or {}).get("summary"))
        or {}
    )
    combo_checks = combo.get("checks") or {}
    combo_handlers = combo.get("handlers") or {}
    return {
        "path": str(path.resolve()),
        "session": doc.get("session"),
        "proxyEndpoint": doc.get("proxyEndpoint"),
        "checks": doc.get("checks"),
        "comboJson": combo.get("json"),
        "comboChecks": combo_checks,
        "seq5Handlers": combo_handlers.get("seq5"),
        "seq6Handlers": combo_handlers.get("seq6"),
        "seq5NormalRejectShape": (
            combo_checks.get("seq5Http200") is True
            and combo_checks.get("seq5HasOIIoIooo") is True
            and combo_checks.get("anySuccessHandler") is False
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit whether direct Webshare session/IP rotation alone explains no-browser HUMAN rejection.")
    parser.add_argument("attempts", nargs="*", type=Path)
    parser.add_argument("--password", default="e5wruchrofwl")
    parser.add_argument("--host", default="p.webshare.io")
    parser.add_argument("--port", type=int, default=80)
    parser.add_argument("--ip-url", default="http://api.ipify.org")
    parser.add_argument("--timeout", type=int, default=20)
    parser.add_argument("--out", type=Path, default=OUT_DIR / "direct_webshare_ip_hypothesis_audit.json")
    args = parser.parse_args()

    paths = args.attempts or sorted(ATTEMPT_DIR.glob("direct_webshare_attempt_*.json"))
    rows = []
    for path in paths:
        row = summarize_attempt(path)
        session = row.get("session")
        row["egressProbe"] = curl_ip(session, args.password, args.host, args.port, args.ip_url, args.timeout) if session else None
        rows.append(row)

    egress_ips = [((row.get("egressProbe") or {}).get("body") or "").strip() for row in rows]
    success_rows = [row for row in rows if ((row.get("comboChecks") or {}).get("anySuccessHandler") is True)]
    normal_reject_rows = [row for row in rows if row.get("seq5NormalRejectShape") is True]
    result = {
        "generatedAt": time.time(),
        "purpose": "Test the IP/session hypothesis with direct Webshare no-browser attempts.",
        "inputs": {
            "attemptCount": len(rows),
            "attemptPaths": [row["path"] for row in rows],
            "ipUrl": args.ip_url,
            "proxyEndpoint": f"http://{args.host}:{args.port}",
        },
        "rows": rows,
        "checks": {
            "allAttemptsUseDirectWebshareEndpoint": bool(rows) and all(row.get("proxyEndpoint") == f"http://{args.host}:{args.port}" for row in rows),
            "allAttemptsReachedProgressionPow": bool(rows) and all(((row.get("checks") or {}).get("progression200Pow") is True) for row in rows),
            "allAttemptsReachedSeq5Collector": bool(rows) and all(((row.get("comboChecks") or {}).get("seq5Http200") is True) for row in rows),
            "allAttemptsRejected": bool(rows) and all(((row.get("comboChecks") or {}).get("anySuccessHandler") is False) for row in rows),
            "allAttemptsNormalSeq5RejectShape": bool(rows) and len(normal_reject_rows) == len(rows),
            "allEgressProbeSucceeded": bool(rows) and all(((row.get("egressProbe") or {}).get("returncode") == 0 and (row.get("egressProbe") or {}).get("httpCode") == "200") for row in rows),
            "distinctEgressIpCount": len(set(ip for ip in egress_ips if ip)),
            "hasAnySuccessRow": bool(success_rows),
        },
        "conclusion": (
            "Direct Webshare session/IP rotation alone is not sufficient for no-browser HUMAN success in these attempts."
        ),
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"json": str(args.out), "checks": result["checks"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
