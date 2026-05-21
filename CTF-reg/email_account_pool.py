"""CSV-backed email account pool for IMAP mailbox mode.

The Cloudflare catch-all path can mint arbitrary addresses.  Real Gmail /
Outlook mailboxes are different: the caller must provide concrete accounts and
their IMAP credentials.  This module keeps that list local on disk and exposes a
small reservation API for registration flows.
"""
from __future__ import annotations

import csv
import os
import random
import re
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional


DEFAULT_COLUMNS = [
    "email",
    "mail_password",
    "provider",
    "imap_host",
    "imap_port",
    "imap_ssl",
    "account_id",
    "access_token",
    "refresh_token",
    "openai_password",
    "first",
    "last",
    "status",
    "fail_reason",
    "updated_at",
]

_FIRST_NAMES = [
    "James", "John", "Emily", "Sophia", "Michael", "Oliver", "Emma",
    "William", "Amelia", "Lucas", "Mia", "Ethan", "Noah", "Ava",
    "Liam", "Isabella", "Mason", "Charlotte", "Logan", "Harper",
]
_LAST_NAMES = [
    "Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia",
    "Miller", "Davis", "Wilson", "Anderson", "Taylor", "Thomas",
    "Moore", "Jackson", "Martin", "Walker",
]


@dataclass
class EmailAccount:
    email: str
    mail_password: str
    provider: str = ""
    imap_host: str = ""
    imap_port: int = 993
    imap_ssl: bool = True
    account_id: str = ""
    access_token: str = ""
    refresh_token: str = ""
    openai_password: str = ""
    first: str = ""
    last: str = ""
    status: str = "unused"
    fail_reason: str = ""
    updated_at: str = ""

    @property
    def email_local(self) -> str:
        return self.email.split("@", 1)[0] if "@" in self.email else self.email

    @property
    def password(self) -> str:
        return self.openai_password or default_openai_password(self.email)

    def to_persona(self):
        """Return a Persona-compatible object used by browser_register."""
        from persona import Persona

        first = self.first or random.choice(_FIRST_NAMES)
        last = self.last or random.choice(_LAST_NAMES)
        return Persona(
            first=first,
            last=last,
            email_local=self.email_local,
            email=self.email,
            password=self.password,
        )

    def sanitized(self) -> dict:
        return {
            "email": self.email,
            "provider": self.provider or infer_provider(self.email),
            "imap_host": self.imap_host or provider_defaults(self.provider or infer_provider(self.email))[0],
            "imap_port": self.imap_port,
            "imap_ssl": self.imap_ssl,
            "account_id": "set" if self.account_id else "",
            "access_token": "set" if self.access_token else "",
            "refresh_token": "set" if self.refresh_token else "",
            "openai_password": "set" if self.openai_password else "auto",
            "first": self.first,
            "last": self.last,
            "status": self.status,
            "fail_reason": self.fail_reason,
            "updated_at": self.updated_at,
        }


def infer_provider(email: str) -> str:
    domain = (email.split("@", 1)[1] if "@" in email else "").lower()
    if domain in ("gmail.com", "googlemail.com"):
        return "gmail"
    if domain in ("outlook.com", "hotmail.com", "live.com", "msn.com"):
        return "outlook"
    return "custom"


def provider_defaults(provider: str) -> tuple[str, int, bool]:
    p = (provider or "").strip().lower()
    if p == "gmail":
        return "imap.gmail.com", 993, True
    if p == "outlook":
        return "outlook.office365.com", 993, True
    return "", 993, True


def default_openai_password(email: str) -> str:
    local = (email or "").split("@", 1)[0]
    pwd = local[::-1]
    if len(pwd) < 8:
        pwd = pwd + "@2026Ai"
    return pwd


def _bool(v, default: bool = True) -> bool:
    if v in (None, ""):
        return default
    return str(v).strip().lower() in ("1", "true", "yes", "y", "on", "ssl")


def _int(v, default: int = 993) -> int:
    try:
        return int(v)
    except Exception:
        return default


def _normalise_row(row: dict) -> dict:
    email = (row.get("email") or row.get("mail") or row.get("username") or "").strip().lower()
    provider = (row.get("provider") or infer_provider(email)).strip().lower()
    host, port, ssl = provider_defaults(provider)
    out = {k: "" for k in DEFAULT_COLUMNS}
    out.update({k: str(v or "").strip() for k, v in row.items() if k})
    out["email"] = email
    out["mail_password"] = (
        row.get("mail_password")
        or row.get("password")
        or row.get("app_password")
        or ""
    ).strip()
    out["provider"] = provider
    out["imap_host"] = (row.get("imap_host") or host or "").strip()
    out["imap_port"] = str(_int(row.get("imap_port") or port, port))
    out["imap_ssl"] = "true" if _bool(row.get("imap_ssl"), ssl) else "false"
    out["account_id"] = (
        row.get("account_id")
        or row.get("id")
        or row.get("user_id")
        or row.get("uid")
        or ""
    ).strip()
    out["access_token"] = (
        row.get("access_token")
        or row.get("token")
        or row.get("oauth_token")
        or row.get("imap_token")
        or ""
    ).strip()
    out["refresh_token"] = (row.get("refresh_token") or "").strip()
    out["openai_password"] = (row.get("openai_password") or "").strip()
    out["first"] = (row.get("first") or "").strip()
    out["last"] = (row.get("last") or "").strip()
    out["status"] = (row.get("status") or "unused").strip().lower()
    out["fail_reason"] = (row.get("fail_reason") or "").strip()
    out["updated_at"] = (row.get("updated_at") or "").strip()
    return out


def parse_accounts_text(text: str) -> list[dict]:
    """Parse CSV or simple mailbox/password lines into pool rows.

    Preferred format is `email----password`, or
    `email----password----client_id----refresh_token`. The WebUI also accepts
    the common pasted form `email_password` as long as the email address itself
    is complete before the separator underscore.
    """
    raw = (text or "").strip()
    if not raw:
        return []

    first_line = next((ln for ln in raw.splitlines() if ln.strip()), "")
    if "," in first_line and "email" in first_line.lower():
        rows = [_normalise_row(r) for r in csv.DictReader(raw.splitlines())]
        return [r for r in rows if r.get("email")]

    rows: list[dict] = []
    for line in raw.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "----" in line:
            parts = re.split(r"\s*-{4,}\s*", line)
        else:
            parts = re.split(r"\s+\|\s+|\t+", line)
        if len(parts) < 2:
            parts = [p.strip() for p in line.split(",")]
        if len(parts) < 2:
            m = re.match(r"^([A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,})_(.+)$", line, re.I)
            if m:
                parts = [m.group(1), m.group(2)]
        if len(parts) < 2:
            continue
        row = {"email": parts[0].strip(), "mail_password": parts[1].strip()}
        if len(parts) >= 3:
            row["account_id"] = parts[2].strip()
        if len(parts) >= 4:
            row["refresh_token"] = parts[3].strip()
        if len(parts) >= 5:
            row["access_token"] = parts[4].strip()
        rows.append(_normalise_row(row))
    return rows


def account_from_row(row: dict) -> EmailAccount:
    r = _normalise_row(row)
    return EmailAccount(
        email=r["email"],
        mail_password=r["mail_password"],
        provider=r["provider"],
        imap_host=r["imap_host"],
        imap_port=_int(r["imap_port"]),
        imap_ssl=_bool(r["imap_ssl"]),
        account_id=r["account_id"],
        access_token=r["access_token"],
        refresh_token=r["refresh_token"],
        openai_password=r["openai_password"],
        first=r["first"],
        last=r["last"],
        status=r["status"],
        fail_reason=r["fail_reason"],
        updated_at=r["updated_at"],
    )


class EmailAccountPool:
    def __init__(self, path: str | Path):
        self.path = Path(path)

    def load_rows(self) -> list[dict]:
        if not self.path.exists():
            return []
        with self.path.open("r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            return [_normalise_row(r) for r in reader if (r.get("email") or "").strip()]

    def load_accounts(self) -> list[EmailAccount]:
        return [account_from_row(r) for r in self.load_rows()]

    def write_rows(self, rows: Iterable[dict]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        normalised = [_normalise_row(r) for r in rows]
        columns = list(DEFAULT_COLUMNS)
        for row in normalised:
            for key in row:
                if key not in columns:
                    columns.append(key)
        fd, tmp_name = tempfile.mkstemp(prefix=self.path.name, dir=str(self.path.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=columns)
                writer.writeheader()
                for row in normalised:
                    writer.writerow({k: row.get(k, "") for k in columns})
            os.chmod(tmp_name, 0o600)
            os.replace(tmp_name, self.path)
        finally:
            if os.path.exists(tmp_name):
                try:
                    os.unlink(tmp_name)
                except OSError:
                    pass

    def save_from_text(self, text: str) -> list[EmailAccount]:
        rows = parse_accounts_text(text)
        self.write_rows(rows)
        return [account_from_row(r) for r in rows]

    def reserve_next(self) -> EmailAccount:
        rows = self.load_rows()
        for row in rows:
            if (row.get("status") or "unused").lower() in ("", "unused"):
                row["status"] = "reserved"
                row["fail_reason"] = ""
                row["updated_at"] = str(int(time.time()))
                self.write_rows(rows)
                return account_from_row(row)
        raise RuntimeError(f"邮箱池没有 unused 账号: {self.path}")

    def find(self, email: str) -> EmailAccount | None:
        target = (email or "").strip().lower()
        for row in self.load_rows():
            if row.get("email") == target:
                return account_from_row(row)
        return None

    def mark(self, email: str, status: str, fail_reason: str = "") -> None:
        target = (email or "").strip().lower()
        if not target:
            return
        rows = self.load_rows()
        changed = False
        for row in rows:
            if row.get("email") == target:
                row["status"] = status
                row["fail_reason"] = fail_reason
                row["updated_at"] = str(int(time.time()))
                changed = True
                break
        if changed:
            self.write_rows(rows)
