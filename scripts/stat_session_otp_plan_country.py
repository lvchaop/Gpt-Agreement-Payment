#!/usr/bin/env python3
"""统计 session_otp_snapshots 中不同 plan 账号的 OTP 提交时间和国家。

默认按邮箱关联 output/webui.db 的 registered_accounts.last_plan_type，
输出 self_serve_business_usage_based 和 team 两类账号。
"""
from __future__ import annotations

import argparse
import csv
import json
import sqlite3
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SNAPSHOT_DIR = ROOT / "output" / "session_otp_snapshots"
DEFAULT_DB = ROOT / "output" / "webui.db"
DEFAULT_CSV = ROOT / "output" / "session_otp_plan_country_stats.csv"
DEFAULT_JSON = ROOT / "output" / "session_otp_plan_country_stats.json"


def _text(value: Any) -> str:
    return str(value or "").strip()


def _lower(value: Any) -> str:
    return _text(value).lower()


def _dt_from_epoch(value: Any) -> tuple[str, str]:
    try:
        ts = float(value)
    except Exception:
        return "", ""
    dt_utc = datetime.fromtimestamp(ts, timezone.utc)
    dt_local = dt_utc.astimezone()
    return dt_utc.isoformat(), dt_local.isoformat()


def load_latest_accounts(db_path: Path) -> dict[str, dict[str, Any]]:
    if not db_path.exists():
        raise FileNotFoundError(f"DB 不存在: {db_path}")
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT *
        FROM registered_accounts
        ORDER BY id ASC
        """
    ).fetchall()
    latest: dict[str, dict[str, Any]] = {}
    for row in rows:
        item = dict(row)
        email = _lower(item.get("email"))
        if email:
            latest[email] = item
    return latest


def _first_dict(*values: Any) -> dict[str, Any]:
    for value in values:
        if isinstance(value, dict):
            return value
    return {}


def _workspace_summary(snapshot: dict[str, Any]) -> tuple[str, int, str]:
    session = _first_dict(
        (((snapshot.get("otp_validate_response") or {}).get("oai-client-auth-session")) or {}),
    )
    workspaces = session.get("workspaces")
    if not isinstance(workspaces, list):
        return "", 0, ""
    kinds = []
    org_ids = []
    for item in workspaces:
        if not isinstance(item, dict):
            continue
        kind = _text(item.get("kind"))
        if kind:
            kinds.append(kind)
        if kind == "organization" and item.get("id"):
            org_ids.append(_text(item.get("id")))
    return ",".join(kinds), len(org_ids), ",".join(org_ids)


def parse_snapshot(path: Path, account: dict[str, Any] | None) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"snapshot 不是 JSON object: {path}")

    email = _lower(data.get("email") or path.stem)
    account = account or {}
    plan_type = _lower(account.get("last_plan_type"))

    # 现有快照中的 otp_validated_at 是 verify_otp() 返回后写入的时间，
    # 不是发起 email-otp/validate 请求前的精确时间。
    otp_utc, otp_local = _dt_from_epoch(data.get("otp_validated_at"))
    otp_resp = _first_dict(data.get("otp_validate_response"))
    auth_session = _first_dict(otp_resp.get("oai-client-auth-session"))
    country_hint = _text(auth_session.get("country_code_hint")).upper()

    proxy_stage = _first_dict(data.get("proxy_stage_plan"))
    proxy_meta = _first_dict(data.get("proxy_meta"))
    register_meta = _first_dict(
        proxy_stage.get("register_meta"),
        proxy_meta.get("register"),
    )
    payment_meta = _first_dict(
        proxy_stage.get("payment_meta"),
        proxy_meta.get("payment"),
    )
    register_region = _text(
        proxy_stage.get("register_region")
        or register_meta.get("region")
    ).upper()
    payment_region = _text(
        proxy_stage.get("payment_region")
        or payment_meta.get("region")
    ).upper()
    proxy_country = country_hint or register_region or payment_region
    workspace_kinds, org_workspace_count, org_workspace_ids = _workspace_summary(data)

    return {
        "email": email,
        "plan_type": plan_type,
        "account_id": account.get("id") or "",
        "last_check_status": account.get("last_check_status") or "",
        "last_check_message": account.get("last_check_message") or "",
        "otp_validated_at": data.get("otp_validated_at") or "",
        "otp_validated_utc": otp_utc,
        "otp_validated_local": otp_local,
        "otp_submit_completed_at": data.get("otp_validated_at") or "",
        "otp_submit_completed_utc": otp_utc,
        "otp_submit_completed_local": otp_local,
        "snapshot_saved_at": data.get("saved_at") or "",
        "snapshot_updated_at": data.get("snapshot_updated_at") or "",
        "country_code_hint": country_hint,
        "proxy_country": proxy_country,
        "register_region": register_region,
        "payment_region": payment_region,
        "proxy": data.get("proxy") or "",
        "proxy_name": register_meta.get("name") or payment_meta.get("name") or "",
        "proxy_server": register_meta.get("server") or payment_meta.get("server") or "",
        "page_type": data.get("page_type") or "",
        "continue_url": data.get("continue_url") or "",
        "workspace_kinds": workspace_kinds,
        "org_workspace_count": org_workspace_count,
        "org_workspace_ids": org_workspace_ids,
        "snapshot_path": str(path),
    }


def build_stats(rows: list[dict[str, Any]]) -> dict[str, Any]:
    by_plan: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_plan[row["plan_type"]].append(row)

    plans: dict[str, Any] = {}
    for plan, items in sorted(by_plan.items()):
        plans[plan] = {
            "count": len(items),
            "country_code_hint": dict(Counter(i["country_code_hint"] or "<missing>" for i in items)),
            "proxy_country": dict(Counter(i["proxy_country"] or "<missing>" for i in items)),
            "register_region": dict(Counter(i["register_region"] or "<missing>" for i in items)),
            "payment_region": dict(Counter(i["payment_region"] or "<missing>" for i in items)),
            "page_type": dict(Counter(i["page_type"] or "<missing>" for i in items)),
            "org_workspace_count_gt0": sum(1 for i in items if int(i.get("org_workspace_count") or 0) > 0),
        }
    return {
        "total": len(rows),
        "plans": plans,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot-dir", default=str(DEFAULT_SNAPSHOT_DIR))
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--plans", default="self_serve_business_usage_based,team",
                        help="逗号分隔的 last_plan_type；空字符串表示全部")
    parser.add_argument("--csv", default=str(DEFAULT_CSV))
    parser.add_argument("--json", default=str(DEFAULT_JSON))
    parser.add_argument("--print-rows", action="store_true")
    args = parser.parse_args()

    snapshot_dir = Path(args.snapshot_dir)
    db_path = Path(args.db)
    if not snapshot_dir.exists():
        raise FileNotFoundError(f"snapshot-dir 不存在: {snapshot_dir}")

    wanted = {_lower(p) for p in str(args.plans or "").split(",") if _lower(p)}
    accounts = load_latest_accounts(db_path)
    rows: list[dict[str, Any]] = []
    skipped_no_account = 0
    skipped_plan = 0
    errors: list[str] = []

    for path in sorted(snapshot_dir.glob("*.json")):
        try:
            email = _lower(path.stem)
            account = accounts.get(email)
            if not account:
                skipped_no_account += 1
                continue
            row = parse_snapshot(path, account)
            if wanted and row["plan_type"] not in wanted:
                skipped_plan += 1
                continue
            rows.append(row)
        except Exception as e:
            errors.append(f"{path}: {type(e).__name__}: {e}")

    fieldnames = [
        "email",
        "plan_type",
        "account_id",
        "last_check_status",
        "last_check_message",
        "otp_validated_at",
        "otp_validated_utc",
        "otp_validated_local",
        "otp_submit_completed_at",
        "otp_submit_completed_utc",
        "otp_submit_completed_local",
        "snapshot_saved_at",
        "snapshot_updated_at",
        "country_code_hint",
        "proxy_country",
        "register_region",
        "payment_region",
        "proxy",
        "proxy_name",
        "proxy_server",
        "page_type",
        "workspace_kinds",
        "org_workspace_count",
        "org_workspace_ids",
        "continue_url",
        "snapshot_path",
    ]

    csv_path = Path(args.csv)
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in fieldnames})

    stats = build_stats(rows)
    stats.update({
        "snapshot_dir": str(snapshot_dir),
        "db": str(db_path),
        "csv": str(csv_path),
        "matched": len(rows),
        "skipped_no_account": skipped_no_account,
        "skipped_plan": skipped_plan,
        "errors": errors,
    })
    json_path = Path(args.json)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps({"stats": stats, "rows": rows}, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps(stats, ensure_ascii=False, indent=2))
    print(f"\nCSV: {csv_path}")
    print(f"JSON: {json_path}")
    if args.print_rows:
        for row in rows:
            print(json.dumps(row, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
