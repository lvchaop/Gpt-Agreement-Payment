#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import time
import urllib.parse
from pathlib import Path


REPO = Path("/Users/chaopenglv/data/me/Gpt-Agreement-Payment")
OUT_DIR = REPO / "output/protocol_reverse/webshare_direct_sessions"


def proxy_url(session: str, password: str, host: str, port: int) -> str:
    return f"http://{urllib.parse.quote(session, safe='')}:{urllib.parse.quote(password, safe='')}@{host}:{port}"


def run_curl(url: str, proxy: str, timeout: int) -> dict:
    cmd = [
        "curl",
        "-sS",
        "--connect-timeout",
        "8",
        "--max-time",
        str(timeout),
        "--proxy",
        proxy,
        "-o",
        "/dev/null",
        "-w",
        "%{http_code} %{remote_ip} %{time_namelookup} %{time_connect} %{time_appconnect} %{time_total}",
        url,
    ]
    started = time.time()
    proc = subprocess.run(cmd, cwd=REPO, text=True, capture_output=True, check=False)
    parts = proc.stdout.strip().split()
    return {
        "cmdRedacted": [p if p != proxy else proxy.replace(urllib.parse.urlparse(proxy).password or "", "***") for p in cmd],
        "returncode": proc.returncode,
        "stdout": proc.stdout.strip(),
        "stderr": proc.stderr.strip()[-1000:],
        "elapsedSeconds": time.time() - started,
        "parsed": {
            "httpCode": parts[0] if len(parts) > 0 else "",
            "remoteIp": parts[1] if len(parts) > 1 else "",
            "timeNamelookup": parts[2] if len(parts) > 2 else "",
            "timeConnect": parts[3] if len(parts) > 3 else "",
            "timeAppconnect": parts[4] if len(parts) > 4 else "",
            "timeTotal": parts[5] if len(parts) > 5 else "",
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit direct Webshare sticky sessions without local proxy.")
    parser.add_argument("--base-user", default="ibtvqcnm")
    parser.add_argument("--country", default="JP")
    parser.add_argument("--password", default="e5wruchrofwl")
    parser.add_argument("--host", default="p.webshare.io")
    parser.add_argument("--port", type=int, default=80)
    parser.add_argument("--attempts", type=int, default=3)
    parser.add_argument("--url", default="https://api.ipify.org")
    parser.add_argument("--timeout", type=int, default=20)
    parser.add_argument("--out-dir", type=Path, default=OUT_DIR)
    args = parser.parse_args()

    started = time.time()
    seed = int(started) * 1000
    rows = []
    for idx in range(args.attempts):
        session = f"{args.base_user}-{args.country.upper()}-{seed + idx}"
        proxy = proxy_url(session, args.password, args.host, args.port)
        rows.append({
            "idx": idx,
            "session": session,
            "proxyEndpoint": f"http://{args.host}:{args.port}",
            "targetUrl": args.url,
            "result": run_curl(args.url, proxy, args.timeout),
        })
    doc = {
        "startedAt": started,
        "inputs": {
            "baseUser": args.base_user,
            "country": args.country.upper(),
            "host": args.host,
            "port": args.port,
            "attempts": args.attempts,
            "url": args.url,
            "timeout": args.timeout,
        },
        "rows": rows,
    }
    args.out_dir.mkdir(parents=True, exist_ok=True)
    out = args.out_dir / f"webshare_direct_sessions_{seed}.json"
    out.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "json": str(out),
        "rows": [
            {
                "idx": r["idx"],
                "session": r["session"],
                "returncode": r["result"]["returncode"],
                **r["result"]["parsed"],
            }
            for r in rows
        ],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
