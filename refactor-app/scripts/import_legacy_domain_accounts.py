from __future__ import annotations

import argparse
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import create_engine, text


DEFAULT_LEGACY_DB = "../output/webui.db"
DEFAULT_DATABASE_URL = "postgresql+psycopg://postgres:postgres@127.0.0.1:5432/refactor_app"
DEFAULT_DOMAINS = (
    "boluodadaxyz.xyz",
    "cnnetdata.net",
    "ksjbakf.xyz",
)


@dataclass(frozen=True)
class LegacyDomainAccount:
    legacy_id: int
    email: str
    password: str
    created_at: datetime


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Import valid legacy domain accounts with email and password only."
    )
    parser.add_argument("--legacy-db", default=DEFAULT_LEGACY_DB)
    parser.add_argument("--database-url", default=DEFAULT_DATABASE_URL)
    parser.add_argument("--domain", action="append", dest="domains")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def _legacy_datetime(value: float) -> datetime:
    if value <= 0:
        return datetime.now(UTC)
    return datetime.fromtimestamp(value, tz=UTC)


def load_accounts(legacy_db: Path, domains: tuple[str, ...]) -> list[LegacyDomainAccount]:
    placeholders = ", ".join("?" for _ in domains)
    query = f"""
        SELECT
          r.id,
          trim(r.email) AS email,
          COALESCE(r.password, '') AS password,
          COALESCE(r.created_at, 0) AS created_at
        FROM registered_accounts r
        LEFT JOIN oauth_status o ON lower(trim(o.email)) = lower(trim(r.email))
        WHERE lower(substr(trim(r.email), instr(trim(r.email), '@') + 1))
                IN ({placeholders})
          AND COALESCE(r.last_check_status, '') = 'valid'
          AND COALESCE(o.status, '') != 'dead'
          AND trim(r.email) != ''
          AND COALESCE(r.password, '') != ''
        ORDER BY r.id
    """
    with sqlite3.connect(f"file:{legacy_db}?mode=ro", uri=True) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(query, domains).fetchall()
    return [
        LegacyDomainAccount(
            legacy_id=int(row["id"]),
            email=str(row["email"]),
            password=str(row["password"]),
            created_at=_legacy_datetime(float(row["created_at"] or 0)),
        )
        for row in rows
    ]


def import_accounts(
    accounts: list[LegacyDomainAccount], database_url: str, *, dry_run: bool
) -> dict[str, int]:
    engine = create_engine(database_url, pool_pre_ping=True)
    with engine.begin() as conn:
        existing_rows = conn.execute(
            text(
                """
                SELECT id, lower(trim(email)) AS normalized_email
                FROM user_accounts
                WHERE lower(trim(email)) = ANY(:emails)
                """
            ),
            {"emails": [account.email.lower() for account in accounts]},
        ).mappings()
        existing_by_email = {
            str(row["normalized_email"]): str(row["id"]) for row in existing_rows
        }

        inserted = 0
        updated = 0
        if dry_run:
            return {
                "selected": len(accounts),
                "inserted": len(accounts) - len(existing_by_email),
                "updated": len(existing_by_email),
            }

        now = datetime.now(UTC)
        for account in accounts:
            existing_id = existing_by_email.get(account.email.lower())
            if existing_id:
                conn.execute(
                    text(
                        """
                        UPDATE user_accounts
                        SET password = :password, updated_at = :updated_at
                        WHERE id = :id
                        """
                    ),
                    {
                        "id": existing_id,
                        "password": account.password,
                        "updated_at": now,
                    },
                )
                updated += 1
                continue

            conn.execute(
                text(
                    """
                    INSERT INTO user_accounts (
                      id,
                      email,
                      password,
                      account_status,
                      session_status,
                      created_at,
                      updated_at
                    )
                    VALUES (
                      :id,
                      :email,
                      :password,
                      'active',
                      'unknown',
                      :created_at,
                      :updated_at
                    )
                    """
                ),
                {
                    "id": f"legacy-domain-account-{account.legacy_id}",
                    "email": account.email,
                    "password": account.password,
                    "created_at": account.created_at,
                    "updated_at": now,
                },
            )
            inserted += 1

    return {"selected": len(accounts), "inserted": inserted, "updated": updated}


def main() -> None:
    args = parse_args()
    legacy_db = Path(args.legacy_db).resolve()
    if not legacy_db.exists():
        raise SystemExit(f"legacy db not found: {legacy_db}")

    domains = tuple(
        sorted({str(domain).strip().lower() for domain in (args.domains or DEFAULT_DOMAINS)})
    )
    accounts = load_accounts(legacy_db, domains)
    result = import_accounts(accounts, args.database_url, dry_run=args.dry_run)
    print(
        "legacy_domain_import "
        f"domains={','.join(domains)} selected={result['selected']} "
        f"inserted={result['inserted']} updated={result['updated']} dry_run={args.dry_run}"
    )


if __name__ == "__main__":
    main()
