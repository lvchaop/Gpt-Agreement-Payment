#!/usr/bin/env python3
"""Pure-protocol Outlook mailbox OAuth authorizer.

This is intentionally standalone: it does not register accounts and is not
wired into pipeline.py.  It authorizes an existing Outlook mailbox to the
portal_protocol.mail_oauth_* application and can persist the token into
output/webui.db:mail_accounts.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sqlite3
import sys
import time
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from config import Config
from outlook_oauth import (
    _requests_oauth_session,
    authorize_outlook_mailbox,
)


def _project_root() -> Path:
    here = Path(__file__).resolve()
    return here.parents[1]


def _parse_account(value: str) -> tuple[str, str]:
    raw = (value or "").strip()
    if not raw:
        return "", ""
    for sep in ("----", ":", ","):
        if sep in raw:
            left, right = raw.split(sep, 1)
            return left.strip(), right.strip()
    return raw, ""


def _load_accounts(args: argparse.Namespace) -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    if args.account:
        rows.append(_parse_account(args.account))
    if args.email:
        rows.append((args.email.strip(), args.password.strip()))
    if args.accounts_file:
        path = Path(args.accounts_file).expanduser().resolve()
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            rows.append(_parse_account(line))
    out: list[tuple[str, str]] = []
    for email, password in rows:
        if not email:
            continue
        if not password:
            raise SystemExit(f"missing password for {email}; use --password or email----password")
        out.append((email, password))
    if not out:
        raise SystemExit("no account provided; use --email/--password, --account, or --accounts-file")
    return out


def _load_unauthorized_accounts_from_db(db_path: Path, *, limit: int = 0) -> list[tuple[str, str]]:
    if not db_path.exists():
        raise SystemExit(f"db not found: {db_path}")
    sql = """
        SELECT email, mail_password
        FROM mail_accounts
        WHERE COALESCE(refresh_token, '') = ''
          AND COALESCE(mail_password, '') <> ''
        ORDER BY id ASC
    """
    params: tuple[Any, ...] = ()
    if limit > 0:
        sql += " LIMIT ?"
        params = (limit,)
    with sqlite3.connect(str(db_path)) as conn:
        rows = conn.execute(sql, params).fetchall()
    return [(str(email).strip(), str(password)) for email, password in rows if str(email).strip()]


def _redact_url(value: str) -> str:
    if not value:
        return ""
    parts = urlsplit(value)
    sensitive = {"code", "access_token", "refresh_token", "id_token", "client_secret"}
    query = urlencode(
        [(key, "***" if key.lower() in sensitive else val) for key, val in parse_qsl(parts.query, keep_blank_values=True)]
    )
    return urlunsplit((parts.scheme, parts.netloc, parts.path, query, parts.fragment))


def _body_marker(text: str) -> str:
    compact = re.sub(r"\s+", " ", (text or "")).strip()
    if not compact:
        return ""
    markers = []
    lowered = compact.lower()
    for item in (
        "account.live.com/abuse",
        "/abuse",
        "identity/confirm",
        "proofs/add",
        "consent",
        "ucaction",
        "ppft",
        "sftag",
        "oauth20_desktop.srf",
        "token-tool/callback",
    ):
        if item in lowered:
            markers.append(item)
    prefix = compact[:500]
    return ("markers=" + ",".join(markers) + " body=" + prefix) if markers else prefix


def _request_payload_evidence(req: Any) -> dict[str, Any]:
    body = getattr(req, "body", None)
    if body is None:
        return {}
    if isinstance(body, bytes):
        raw = body.decode("utf-8", "replace")
    else:
        raw = str(body)
    if not raw:
        return {}
    sensitive = {"passwd", "password", "ppft", "canary", "vanguardflowtoken", "flowtoken", "ctx", "ipt", "verifier", "reply_params"}
    evidence: dict[str, Any] = {"raw_len": len(raw)}
    ctype = ""
    try:
        ctype = str(req.headers.get("Content-Type") or req.headers.get("content-type") or "")
    except Exception:
        pass
    try:
        if "json" in ctype:
            data = json.loads(raw)
            if isinstance(data, dict):
                evidence["json_keys"] = sorted(data.keys())
                evidence["json_fields"] = {
                    k: (f"<len={len(str(v))}>" if k.lower() in sensitive else str(v)[:80])
                    for k, v in data.items()
                }
        else:
            fields = parse_qsl(raw, keep_blank_values=True)
            evidence["form_keys"] = [k for k, _v in fields]
            evidence["form_fields"] = {
                k: (f"<len={len(str(v))}>" if k.lower() in sensitive else str(v)[:80])
                for k, v in fields
            }
    except Exception as e:
        evidence["parse_error"] = str(e)
        evidence["raw_prefix"] = raw[:200]
    return evidence


def _cookie_names(value: str) -> list[str]:
    out: list[str] = []
    for part in (value or "").split(";"):
        name = part.split("=", 1)[0].strip()
        if name:
            out.append(name)
    return out


def _header_evidence(headers: Any) -> dict[str, Any]:
    if not headers:
        return {}
    out: dict[str, Any] = {}
    sensitive = {"authorization", "proxy-authorization", "x-ms-ests-server"}
    try:
        items = headers.items()
    except Exception:
        items = []
    for key, value in items:
        lk = str(key).lower()
        text = str(value)
        if lk == "cookie":
            out["cookie_names"] = _cookie_names(text)
        elif lk == "set-cookie":
            out["set_cookie_names"] = _cookie_names(text)
        elif lk in sensitive or "token" in lk or "secret" in lk:
            out[lk] = f"<len={len(text)}>"
        else:
            out[lk] = text if len(text) <= 1000 else f"<len={len(text)} prefix={text[:300]}>"
    return out


def _install_response_trace(session: Any, trace_path: Path, *, email: str) -> None:
    trace_path.parent.mkdir(parents=True, exist_ok=True)
    counter = {"n": 0}

    def _hook(resp: Any, *args: Any, **kwargs: Any) -> Any:
        counter["n"] += 1
        location = resp.headers.get("location") or resp.headers.get("Location") or ""
        try:
            text = resp.text or ""
        except Exception:
            text = ""
        row = {
            "n": counter["n"],
            "email": email,
            "method": getattr(getattr(resp, "request", None), "method", ""),
            "status": getattr(resp, "status_code", None),
            "url": _redact_url(str(getattr(resp, "url", "") or "")),
            "request_url": _redact_url(str(getattr(getattr(resp, "request", None), "url", "") or "")),
            "request_headers": _header_evidence(getattr(getattr(resp, "request", None), "headers", None)),
            "request_payload": _request_payload_evidence(getattr(resp, "request", None)),
            "location": _redact_url(location),
            "response_headers": _header_evidence(resp.headers),
            "content_type": resp.headers.get("content-type", ""),
            "body_marker": _body_marker(text),
        }
        with trace_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
        return resp

    hooks = getattr(session, "hooks", None)
    if isinstance(hooks, dict):
        hooks.setdefault("response", []).append(_hook)
        return

    original_request = session.request

    def _traced_request(method: str, url: str, **kwargs: Any) -> Any:
        resp = original_request(method, url, **kwargs)
        return _hook(resp)

    session.request = _traced_request


def _log_proxy_exit(session: Any, *, email: str) -> None:
    if str(os.getenv("SKIP_PROXY_EXIT_CHECK", "")).strip().lower() in {"1", "true", "yes"}:
        return
    try:
        resp = session.get("https://api.ipify.org?format=json", timeout=12)
        data = resp.json()
        logging.getLogger(__name__).info(
            "proxy exit evidence email=%s status=%s ip=%s",
            email,
            getattr(resp, "status_code", ""),
            data.get("ip") if isinstance(data, dict) else "",
        )
    except Exception as e:
        logging.getLogger(__name__).info("proxy exit evidence failed email=%s err=%s", email, e)


def _ensure_mail_tables(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS mail_accounts (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          email TEXT NOT NULL UNIQUE COLLATE NOCASE,
          mail_password TEXT DEFAULT '',
          provider TEXT DEFAULT '',
          imap_host TEXT DEFAULT '',
          imap_port INTEGER DEFAULT 993,
          imap_ssl INTEGER DEFAULT 1,
          account_id TEXT DEFAULT '',
          access_token TEXT DEFAULT '',
          refresh_token TEXT DEFAULT '',
          openai_password TEXT DEFAULT '',
          first TEXT DEFAULT '',
          last TEXT DEFAULT '',
          status TEXT DEFAULT 'unused',
          fail_reason TEXT DEFAULT '',
          created_at REAL NOT NULL,
          updated_at REAL NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS oauth_status (
          email TEXT PRIMARY KEY COLLATE NOCASE,
          status TEXT NOT NULL,
          ts TEXT NOT NULL,
          fail_reason TEXT DEFAULT ''
        )
        """
    )


def _write_mail_account(
    db_path: Path,
    *,
    email: str,
    password: str,
    client_id: str,
    access_token: str,
    refresh_token: str,
    status: str,
    fail_reason: str = "",
) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    now = time.time()
    ts = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    with sqlite3.connect(str(db_path)) as conn:
        _ensure_mail_tables(conn)
        conn.execute(
            """
            INSERT INTO mail_accounts(
              email, mail_password, provider, imap_host, imap_port, imap_ssl,
              account_id, access_token, refresh_token, status, fail_reason,
              created_at, updated_at
            ) VALUES (?, ?, 'outlook', 'outlook.office365.com', 993, 1, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(email) DO UPDATE SET
              mail_password=excluded.mail_password,
              provider=excluded.provider,
              imap_host=excluded.imap_host,
              imap_port=excluded.imap_port,
              imap_ssl=excluded.imap_ssl,
              account_id=excluded.account_id,
              access_token=excluded.access_token,
              refresh_token=excluded.refresh_token,
              status=excluded.status,
              fail_reason=excluded.fail_reason,
              updated_at=excluded.updated_at
            """,
            (
                email.lower(),
                password,
                client_id,
                access_token,
                refresh_token,
                status,
                fail_reason,
                now,
                now,
            ),
        )
        conn.execute(
            """
            INSERT INTO oauth_status(email, status, ts, fail_reason)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(email) DO UPDATE SET
              status=excluded.status,
              ts=excluded.ts,
              fail_reason=excluded.fail_reason
            """,
            (email.lower(), "succeeded" if refresh_token else "failed", ts, fail_reason),
        )


def _write_oauth_failure(
    db_path: Path,
    *,
    email: str,
    password: str,
    fail_reason: str,
) -> None:
    now = time.time()
    ts = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    with sqlite3.connect(str(db_path)) as conn:
        _ensure_mail_tables(conn)
        conn.execute(
            """
            INSERT INTO mail_accounts(
              email, mail_password, provider, imap_host, imap_port, imap_ssl,
              status, fail_reason, created_at, updated_at
            ) VALUES (?, ?, 'outlook', 'outlook.office365.com', 993, 1, 'oauth_failed', ?, ?, ?)
            ON CONFLICT(email) DO UPDATE SET
              mail_password=CASE
                WHEN COALESCE(mail_accounts.mail_password, '') = '' THEN excluded.mail_password
                ELSE mail_accounts.mail_password
              END,
              status=excluded.status,
              fail_reason=excluded.fail_reason,
              updated_at=excluded.updated_at
            """,
            (email.lower(), password, fail_reason, now, now),
        )
        conn.execute(
            """
            INSERT INTO oauth_status(email, status, ts, fail_reason)
            VALUES (?, 'failed', ?, ?)
            ON CONFLICT(email) DO UPDATE SET
              status=excluded.status,
              ts=excluded.ts,
              fail_reason=excluded.fail_reason
            """,
            (email.lower(), ts, fail_reason),
        )


def _result_dict(email: str, result: Any) -> dict[str, Any]:
    return {
        "email": email,
        "mail_oauth_client_id": result.client_id,
        "mail_account_id": result.client_id,
        "mail_access_token": result.access_token,
        "mail_refresh_token": result.refresh_token,
        "mail_oauth_scope": result.scope,
        "expires_in": result.expires_in,
        "token_type": result.token_type,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Authorize existing Outlook mailbox to configured OAuth app via pure protocol.",
    )
    parser.add_argument("--config", required=True, help="CTF-reg/cardw JSON config path")
    parser.add_argument("--email", default="", help="Mailbox email")
    parser.add_argument("--password", default="", help="Mailbox password")
    parser.add_argument("--account", default="", help="Single account as email----password")
    parser.add_argument("--accounts-file", default="", help="Lines of email----password")
    parser.add_argument("--from-db", action="store_true", help="Load all mail_accounts rows without refresh_token")
    parser.add_argument("--limit", type=int, default=0, help="Limit --from-db rows; 0 means no limit")
    parser.add_argument("--proxy", default="", help="Override cfg.proxy for OAuth protocol requests")
    parser.add_argument("--no-proxy", action="store_true", help="Clear cfg.proxy for OAuth protocol requests")
    parser.add_argument("--write-mail-accounts", action="store_true", help="Upsert tokens into output/webui.db")
    parser.add_argument("--db", default="", help="SQLite DB path; default output/webui.db")
    parser.add_argument("--trace-dir", default="", help="Write per-response protocol trace JSONL files")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    cfg = Config.from_file(str(Path(args.config).expanduser().resolve()))
    setattr(cfg.portal_protocol, "mail_oauth_har_entry", "true")
    setattr(
        cfg.portal_protocol,
        "user_agent",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36",
    )
    if args.no_proxy:
        cfg.proxy = ""
    elif args.proxy:
        cfg.proxy = args.proxy

    db_path = Path(args.db).expanduser().resolve() if args.db else _project_root() / "output" / "webui.db"
    if args.from_db:
        accounts = _load_unauthorized_accounts_from_db(db_path, limit=args.limit)
        if not accounts:
            raise SystemExit("no unauthorized mail_accounts rows found")
    else:
        accounts = _load_accounts(args)
    outputs: list[dict[str, Any]] = []
    ok = True

    for email, password in accounts:
        try:
            session = _requests_oauth_session(cfg)
            if args.trace_dir:
                safe_email = re.sub(r"[^A-Za-z0-9_.@-]+", "_", email)
                trace_path = Path(args.trace_dir).expanduser().resolve() / f"{safe_email}_{int(time.time())}.jsonl"
                logging.getLogger(__name__).info("trace path email=%s path=%s", email, trace_path)
                _install_response_trace(session, trace_path, email=email)
            _log_proxy_exit(session, email=email)
            result = authorize_outlook_mailbox(cfg, session, email=email, password=password)
            record = _result_dict(email, result)
            outputs.append({"ok": True, **record})
            if args.write_mail_accounts:
                _write_mail_account(
                    db_path,
                    email=email,
                    password=password,
                    client_id=result.client_id,
                    access_token=result.access_token,
                    refresh_token=result.refresh_token,
                    status="unused",
                )
        except Exception as e:
            ok = False
            err = str(e)
            outputs.append({"ok": False, "email": email, "error": err})
            if args.write_mail_accounts:
                _write_oauth_failure(
                    db_path,
                    email=email,
                    password=password,
                    fail_reason=err[:500],
                )

    if args.json:
        print(json.dumps(outputs, ensure_ascii=False, indent=2))
    else:
        for item in outputs:
            if item.get("ok"):
                print(
                    "OK {email} client_id={client_id} rt_len={rt_len} scope={scope}".format(
                        email=item["email"],
                        client_id=item["mail_oauth_client_id"],
                        rt_len=len(item.get("mail_refresh_token") or ""),
                        scope=item.get("mail_oauth_scope") or "",
                    )
                )
            else:
                print(f"FAIL {item['email']} error={item.get('error', '')}", file=sys.stderr)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
