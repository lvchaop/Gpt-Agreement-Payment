#!/usr/bin/env python3
"""Probe trojan pool nodes through sing-box and prune unstable nodes.

Each node is bridged to a local HTTP proxy port by a temporary sing-box
process.  A node is kept only when all probe attempts succeed.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import time
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from proxy_bridge import (  # noqa: E402
    TrojanNode,
    build_sing_box_config,
    load_trojan_pool,
    _probe_node_alive,
)


def _port_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.2)
        return sock.connect_ex(("127.0.0.1", int(port))) != 0


def _find_free_port_range(start: int, count: int) -> int:
    port = int(start)
    while port + count < 65535:
        if all(_port_free(p) for p in range(port, port + count)):
            return port
        port += count + 10
    raise RuntimeError(f"找不到连续空闲端口: start={start} count={count}")


def _wait_ports(ports: list[int], deadline_s: float) -> None:
    deadline = time.time() + deadline_s
    pending = set(ports)
    while pending and time.time() < deadline:
        pending = {p for p in pending if not (not _port_free(p))}
        if pending:
            time.sleep(0.1)
    if pending:
        sample = ",".join(str(p) for p in sorted(pending)[:10])
        raise RuntimeError(f"sing-box 本地端口未就绪: {sample}")


def _probe_one(
    node: TrojanNode,
    *,
    attempts: int,
    timeout_s: float,
    probe_url: str,
) -> dict[str, Any]:
    tries = []
    ok_count = 0
    for attempt in range(1, attempts + 1):
        started = time.time()
        ok, detail = _probe_node_alive(node, timeout_s=timeout_s, url=probe_url)
        elapsed_ms = int((time.time() - started) * 1000)
        tries.append(
            {
                "attempt": attempt,
                "ok": bool(ok),
                "detail": detail,
                "elapsed_ms": elapsed_ms,
            }
        )
        if ok:
            ok_count += 1
        print(
            f"[probe] idx={node.index} {node.region} {node.name} "
            f"{attempt}/{attempts} {'ok' if ok else 'fail'} {detail} {elapsed_ms}ms",
            flush=True,
        )
        if not ok:
            break
    return {
        "index": node.index,
        "region": node.region,
        "name": node.name,
        "url": node.url,
        "local_http_url": node.local_http_url,
        "ok": ok_count == attempts,
        "ok_count": ok_count,
        "attempts": attempts,
        "tries": tries,
    }


def _rewrite_pool_line_file(pool_path: Path, keep_indexes: set[int], backup_path: Path) -> None:
    lines = pool_path.read_text(encoding="utf-8").splitlines()
    output_lines = []
    active_index = 0
    for line in lines:
        text = line.strip()
        if not text or text.startswith("#"):
            output_lines.append(line)
            continue
        if active_index in keep_indexes:
            output_lines.append(line)
        active_index += 1
    shutil.copy2(pool_path, backup_path)
    pool_path.write_text("\n".join(output_lines).rstrip() + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pool", default="output/trojan_pool.txt")
    parser.add_argument("--attempts", type=int, default=10)
    parser.add_argument("--concurrency", type=int, default=10)
    parser.add_argument("--timeout", type=float, default=8.0)
    parser.add_argument("--probe-url", default="http://cloudflare.com/cdn-cgi/trace")
    parser.add_argument("--start-port", type=int, default=28081)
    parser.add_argument("--work-dir", default="output/trojan_pool_probe")
    parser.add_argument("--sing-box", default="sing-box")
    parser.add_argument("--write", action="store_true", help="rewrite pool with only all-pass nodes")
    args = parser.parse_args()

    pool_path = (REPO_ROOT / args.pool).resolve() if not Path(args.pool).is_absolute() else Path(args.pool)
    work_dir = (REPO_ROOT / args.work_dir).resolve() if not Path(args.work_dir).is_absolute() else Path(args.work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)

    initial_nodes = load_trojan_pool(pool_path, http_start_port=args.start_port)
    start_port = _find_free_port_range(args.start_port, len(initial_nodes))
    nodes = load_trojan_pool(pool_path, http_start_port=start_port)
    ports = [node.local_http_port for node in nodes]

    run_id = time.strftime("%Y%m%d-%H%M%S")
    config_path = work_dir / f"sing-box.{run_id}.json"
    log_path = work_dir / f"sing-box.{run_id}.log"
    result_path = work_dir / f"result.{run_id}.json"
    backup_path = pool_path.with_suffix(pool_path.suffix + f".bak.{run_id}")

    config_path.write_text(
        json.dumps(build_sing_box_config(nodes), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    exe = shutil.which(args.sing_box) or args.sing_box
    print(
        f"[probe] pool={pool_path} nodes={len(nodes)} concurrency={args.concurrency} "
        f"attempts={args.attempts} probe_url={args.probe_url} port_range={start_port}-{ports[-1]}",
        flush=True,
    )

    proc: subprocess.Popen[Any] | None = None
    try:
        with log_path.open("ab") as log_f:
            proc = subprocess.Popen(
                [exe, "run", "-c", str(config_path)],
                stdout=log_f,
                stderr=subprocess.STDOUT,
                cwd=str(work_dir),
                start_new_session=True,
            )
        time.sleep(0.8)
        if proc.poll() is not None:
            tail = log_path.read_text(encoding="utf-8", errors="replace")[-2000:]
            raise RuntimeError(f"sing-box 启动失败 exit={proc.returncode}: {tail}")
        _wait_ports(ports, 8.0)

        results = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=args.concurrency) as executor:
            futures = [
                executor.submit(
                    _probe_one,
                    node,
                    attempts=args.attempts,
                    timeout_s=args.timeout,
                    probe_url=args.probe_url,
                )
                for node in nodes
            ]
            for future in concurrent.futures.as_completed(futures):
                results.append(future.result())

        results.sort(key=lambda item: int(item["index"]))
        keep = {int(item["index"]) for item in results if item["ok"]}
        drop = [item for item in results if not item["ok"]]
        payload = {
            "pool": str(pool_path),
            "run_id": run_id,
            "concurrency": args.concurrency,
            "attempts": args.attempts,
            "timeout_s": args.timeout,
            "probe_url": args.probe_url,
            "start_port": start_port,
            "config_path": str(config_path),
            "log_path": str(log_path),
            "backup_path": str(backup_path) if args.write else "",
            "total": len(results),
            "kept": len(keep),
            "dropped": len(drop),
            "results": results,
        }
        result_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

        if args.write:
            _rewrite_pool_line_file(pool_path, keep, backup_path)

        print(
            f"[probe] done total={len(results)} kept={len(keep)} dropped={len(drop)} "
            f"result={result_path}",
            flush=True,
        )
        if args.write:
            print(f"[probe] rewritten={pool_path} backup={backup_path}", flush=True)
        if drop:
            print("[probe] dropped:", flush=True)
            for item in drop:
                failed = [t for t in item["tries"] if not t["ok"]]
                first = failed[0]["detail"] if failed else "unknown"
                print(
                    f"  idx={item['index']} {item['region']} {item['name']} "
                    f"ok={item['ok_count']}/{item['attempts']} first_fail={first}",
                    flush=True,
                )
        return 0
    finally:
        if proc and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)


if __name__ == "__main__":
    raise SystemExit(main())
