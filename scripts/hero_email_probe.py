#!/usr/bin/env python3
"""Probe or buy a HeroSMS email activation for a target site/domain."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = ROOT / "output" / "hero_email_activation.json"
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/126.0.0.0 Safari/537.36"
)


class HeroEmailError(RuntimeError):
    pass


def _resolve_path(path: str) -> Path:
    resolved = Path(path).expanduser()
    if not resolved.is_absolute():
        resolved = ROOT / resolved
    return resolved.resolve()


def _api_key(args: argparse.Namespace) -> str:
    token = (args.api_key or "").strip()
    if token:
        return token
    return (os.environ.get(args.api_key_env) or "").strip()


def _request_json(
    *,
    base_url: str,
    api_key: str,
    method: str,
    path: str,
    params: dict[str, Any] | None = None,
    body: dict[str, Any] | None = None,
    user_agent: str = DEFAULT_USER_AGENT,
    timeout_s: float = 30.0,
) -> Any:
    base = base_url.rstrip("/")
    url = f"{base}{path}"
    if params:
        query = urllib.parse.urlencode(
            {key: val for key, val in params.items() if val not in (None, "")}
        )
        if query:
            url = f"{url}?{query}"

    data = None
    headers = {
        "Accept": "application/json",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Authorization": f"ApiKey {api_key}",
        "User-Agent": user_agent,
    }
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"

    req = urllib.request.Request(url, data=data, method=method.upper(), headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            if not raw.strip():
                return {"status_code": resp.status, "data": None}
            try:
                return json.loads(raw)
            except json.JSONDecodeError as exc:
                raise HeroEmailError(f"Hero returned non-JSON response: {raw[:500]}") from exc
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            payload = json.loads(raw) if raw.strip() else {}
        except json.JSONDecodeError:
            payload = {"raw": raw[:500]}
        raise HeroEmailError(
            json.dumps(
                {
                    "status_code": exc.code,
                    "method": method.upper(),
                    "path": path,
                    "error": payload,
                    "hint": (
                        "Cloudflare 1010 means this HTTP client signature was blocked; "
                        "try --user-agent with a real browser UA or run from a different egress IP."
                        if isinstance(payload, dict) and payload.get("error_code") == 1010
                        else ""
                    ),
                },
                ensure_ascii=False,
            )
        ) from exc
    except urllib.error.URLError as exc:
        raise HeroEmailError(f"Hero request failed: {exc.reason}") from exc


def _payload_data(payload: Any) -> Any:
    if isinstance(payload, dict) and "data" in payload:
        return payload["data"]
    return payload


def list_domains(args: argparse.Namespace, api_key: str) -> list[dict[str, Any]]:
    payload = _request_json(
        base_url=args.base_url,
        api_key=api_key,
        method="GET",
        path="/emails/domains",
        params={"site": args.site},
        user_agent=args.user_agent,
        timeout_s=args.timeout_s,
    )
    data = _payload_data(payload)
    if not isinstance(data, list):
        raise HeroEmailError(f"unexpected /emails/domains payload: {json.dumps(payload, ensure_ascii=False)[:500]}")
    return [row for row in data if isinstance(row, dict)]


def _domain_name(row: dict[str, Any]) -> str:
    return str(row.get("name") or row.get("domain") or "").strip()


def choose_domain(
    rows: list[dict[str, Any]],
    preferred: str,
    *,
    min_count: int = 1,
) -> dict[str, Any] | None:
    preferred = preferred.strip().lower()
    exact: list[dict[str, Any]] = []
    fuzzy: list[dict[str, Any]] = []
    for row in rows:
        name = _domain_name(row).lower()
        count = int(row.get("count") or 0)
        if count < min_count:
            continue
        if name == preferred:
            exact.append(row)
        elif preferred and preferred in name:
            fuzzy.append(row)
    candidates = exact or fuzzy
    if not candidates:
        return None
    return sorted(candidates, key=lambda row: float(row.get("cost") or 0.0))[0]


def buy_email(args: argparse.Namespace, api_key: str, domain: str) -> Any:
    return _request_json(
        base_url=args.base_url,
        api_key=api_key,
        method="POST",
        path="/emails",
        body={"site": args.site, "domain": domain},
        user_agent=args.user_agent,
        timeout_s=args.timeout_s,
    )


def buy_email_batch(args: argparse.Namespace, api_key: str, domain: str) -> Any:
    body: dict[str, Any] = {
        "site": args.site,
        "domain": domain,
        "count": args.count,
    }
    if args.service:
        body["service"] = args.service
    return _request_json(
        base_url=args.base_url,
        api_key=api_key,
        method="POST",
        path="/emails/batch",
        body=body,
        user_agent=args.user_agent,
        timeout_s=args.timeout_s,
    )


def get_email(args: argparse.Namespace, api_key: str, email_id: str) -> Any:
    return _request_json(
        base_url=args.base_url,
        api_key=api_key,
        method="GET",
        path=f"/emails/{urllib.parse.quote(str(email_id), safe='')}",
        user_agent=args.user_agent,
        timeout_s=args.timeout_s,
    )


def reorder_email(args: argparse.Namespace, api_key: str, email_id: str) -> Any:
    return _request_json(
        base_url=args.base_url,
        api_key=api_key,
        method="POST",
        path=f"/emails/{urllib.parse.quote(str(email_id), safe='')}/reorder",
        user_agent=args.user_agent,
        timeout_s=args.timeout_s,
    )


def _print_json(payload: Any) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))


def _extract_email_ids(payload: Any) -> list[str]:
    data = _payload_data(payload)
    ids: list[str] = []

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            raw_id = value.get("id") or value.get("emailId") or value.get("email_id")
            if raw_id not in (None, ""):
                ids.append(str(raw_id))
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    walk(data)
    return list(dict.fromkeys(ids))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--site", default="chatgpt.com", help="Target site passed to Hero, default chatgpt.com")
    parser.add_argument("--domain", default="gmail.com", help="Preferred email domain, default gmail.com")
    parser.add_argument("--count", type=int, default=1, help="Number of email activations to buy, 1-10")
    parser.add_argument("--service", default="", help="Optional Hero service code for /emails/batch")
    parser.add_argument("--base-url", default="https://hero-sms.com/api/v1")
    parser.add_argument("--user-agent", default=DEFAULT_USER_AGENT)
    parser.add_argument("--api-key-env", default="HERO_SMS_API_KEY")
    parser.add_argument("--api-key", default="", help="Optional token; prefer env var to avoid shell history")
    parser.add_argument("--timeout-s", type=float, default=30.0)
    parser.add_argument("--buy", action="store_true", help="Actually POST /emails and spend balance")
    parser.add_argument("--poll", action="store_true", help="After buying, poll /emails/{id} for status/message")
    parser.add_argument("--poll-seconds", type=int, default=180)
    parser.add_argument("--poll-interval-s", type=float, default=5.0)
    parser.add_argument("--email-id", default="", help="Only poll an existing Hero email activation id")
    parser.add_argument("--reorder", action="store_true", help="POST /emails/{emailId}/reorder instead of GET")
    parser.add_argument("--out", default=str(DEFAULT_OUT), help="Where to save purchase/poll result")
    args = parser.parse_args()

    if args.count < 1 or args.count > 10:
        raise SystemExit("--count must be between 1 and 10; Hero /emails/batch documents 1 to 10")

    api_key = _api_key(args)
    if not api_key:
        raise SystemExit(f"missing API key: set {args.api_key_env} or pass --api-key")

    if args.email_id:
        result = reorder_email(args, api_key, args.email_id) if args.reorder else get_email(args, api_key, args.email_id)
        if args.reorder:
            out = _resolve_path(args.out)
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        _print_json(result)
        return 0

    domains = list_domains(args, api_key)
    picked = choose_domain(domains, args.domain, min_count=args.count)
    summary = {
        "site": args.site,
        "preferred_domain": args.domain,
        "available_domain_count": len(domains),
        "requested_count": args.count,
        "picked": picked,
        "matching_domains": [
            row for row in domains
            if args.domain.lower() in _domain_name(row).lower()
        ],
    }

    if not args.buy:
        summary["next_step"] = "add --buy to purchase the picked domain"
        _print_json(summary)
        return 0

    if picked is None:
        raise SystemExit(f"no available domain matching {args.domain!r} for site={args.site!r}")

    domain = _domain_name(picked)
    purchase = (
        buy_email(args, api_key, domain)
        if args.count == 1
        else buy_email_batch(args, api_key, domain)
    )
    result: dict[str, Any] = {
        "site": args.site,
        "domain": domain,
        "requested_count": args.count,
        "price_hint": picked.get("cost"),
        "estimated_total": (
            float(picked.get("cost") or 0.0) * args.count
            if picked.get("cost") not in (None, "")
            else None
        ),
        "purchase": purchase,
    }

    email_ids = _extract_email_ids(purchase)
    result["email_ids"] = email_ids

    if args.poll and email_ids:
        deadline = time.monotonic() + max(0, args.poll_seconds)
        polls: list[dict[str, Any]] = []
        while True:
            round_statuses = []
            for email_id in email_ids:
                round_statuses.append(get_email(args, api_key, email_id))
            polls.append({"ts": time.time(), "items": round_statuses})
            statuses = [_payload_data(item) for item in round_statuses]
            done = all(
                isinstance(status_data, dict)
                and (
                    status_data.get("status") in {"SUCCESS", "CANCEL"}
                    or status_data.get("value")
                    or status_data.get("message")
                )
                for status_data in statuses
            )
            if done:
                break
            if time.monotonic() >= deadline:
                break
            time.sleep(max(0.1, args.poll_interval_s))
        result["polls"] = polls

    out = _resolve_path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    result["saved_to"] = str(out)
    _print_json(result)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except HeroEmailError as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1)
