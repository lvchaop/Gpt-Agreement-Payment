#!/usr/bin/env python3
"""
Convert Sub2API codex-session import payloads to local CPA auth-file payloads.

Evidence in this repository:
- pipeline.py Sub2API branch posts:
  {"content": json.dumps(auth_body), "name": "...", ...}
- pipeline.py CPA branch posts:
  params={"name": name}, json=auth_body

Also supports Sub2API account export files shaped as:
  {"accounts": [{"name": "...", "credentials": {...}, ...}], "proxies": ...}

Default output keeps both CPA parts:
  {"name": "...", "body": {...auth json...}}

Use --body-only when you only need the JSON body passed to CPA.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


AUTH_KEYS = {
    "email",
    "access_token",
    "refresh_token",
    "id_token",
    "account_id",
    "plan_tag",
}


def load_input(path: str) -> Any:
    text = sys.stdin.read() if path == "-" else Path(path).read_text(encoding="utf-8")
    text = text.strip()
    if not text:
        raise ValueError("input is empty")

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        items = []
        for lineno, line in enumerate(text.splitlines(), 1):
            line = line.strip()
            if not line:
                continue
            try:
                items.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid JSON/JSONL at line {lineno}: {exc}") from exc
        return items


def parse_content(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, str):
        value = value.strip()
        if not value:
            raise ValueError("Sub2API content is empty")
        parsed = json.loads(value)
        if not isinstance(parsed, dict):
            raise ValueError("Sub2API content JSON must be an object")
        return parsed
    raise ValueError(f"unsupported content type: {type(value).__name__}")


def looks_like_auth_body(obj: dict[str, Any]) -> bool:
    return bool(AUTH_KEYS.intersection(obj.keys())) and (
        "access_token" in obj or "refresh_token" in obj or "id_token" in obj
    )


def convert_one(obj: Any, *, default_name: str = "") -> dict[str, Any]:
    if not isinstance(obj, dict):
        raise ValueError(f"item must be object, got {type(obj).__name__}")

    # Sub2API import/codex-session payload.
    if "content" in obj:
        body = parse_content(obj["content"])
        name = str(obj.get("name") or default_name or "").strip()
        return {"name": name, "body": body}

    # Sub2API account export item.
    if isinstance(obj.get("credentials"), dict):
        body = dict(obj["credentials"])
        if "account_id" not in body:
            account_id = (
                body.get("chatgpt_user_id")
                or body.get("chatgpt_account_id")
                or obj.get("account_id")
                or ""
            )
            if account_id:
                body["account_id"] = account_id
        if "plan_tag" not in body:
            plan_tag = body.get("plan_type") or obj.get("plan_tag") or ""
            if plan_tag:
                body["plan_tag"] = plan_tag
        name = str(obj.get("name") or default_name or body.get("email") or "").strip()
        return {"name": name, "body": body}

    # Already a CPA auth body; wrap it so batch output is uniform.
    if looks_like_auth_body(obj):
        name = str(obj.get("name") or default_name or obj.get("email") or "").strip()
        body = dict(obj)
        body.pop("name", None)
        return {"name": name, "body": body}

    raise ValueError("object is neither Sub2API payload with content nor CPA auth body")


def convert(data: Any, *, default_name: str = "") -> Any:
    if isinstance(data, dict) and isinstance(data.get("accounts"), list):
        return [convert_one(item, default_name=default_name) for item in data["accounts"]]
    if isinstance(data, list):
        return [convert_one(item, default_name=default_name) for item in data]
    return convert_one(data, default_name=default_name)


def body_only(data: Any) -> Any:
    if isinstance(data, list):
        return [item["body"] for item in data]
    return data["body"]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Convert Sub2API codex-session JSON payload to local CPA auth-file JSON."
    )
    parser.add_argument("input", help="input JSON/JSONL file, or '-' for stdin")
    parser.add_argument("-o", "--output", help="output file; default stdout")
    parser.add_argument("--default-name", default="", help="CPA auth-file name when input has no name")
    parser.add_argument(
        "--body-only",
        action="store_true",
        help="output only CPA JSON body, not {name, body} wrapper",
    )
    parser.add_argument("--compact", action="store_true", help="write compact JSON")
    args = parser.parse_args()

    try:
        data = load_input(args.input)
        out = convert(data, default_name=args.default_name)
        if args.body_only:
            out = body_only(out)
    except Exception as exc:
        print(f"sub2api_to_cpa: {exc}", file=sys.stderr)
        return 1

    if args.compact:
        text = json.dumps(out, ensure_ascii=False, separators=(",", ":")) + "\n"
    else:
        text = json.dumps(out, ensure_ascii=False, indent=2) + "\n"

    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
