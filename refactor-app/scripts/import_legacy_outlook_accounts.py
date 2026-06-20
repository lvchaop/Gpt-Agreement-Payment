from __future__ import annotations

import argparse
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import create_engine, text

DEFAULT_LEGACY_DB = "../output/webui.db"
DEFAULT_DATABASE_URL = "postgresql+psycopg://postgres:postgres@127.0.0.1:5432/refactor_app"


@dataclass(frozen=True)
class LegacyAccount:
    legacy_id: int
    email: str
    password: str
    phone_number: str
    phone_dial_code: str
    phone_country: str
    legacy_created_at: float


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Import non-invalid legacy registered @outlook.com accounts into the refactor app. "
            "Only email/password/phone fields are copied; "
            "session/token fields are intentionally reset."
        )
    )
    parser.add_argument("--legacy-db", default=DEFAULT_LEGACY_DB)
    parser.add_argument("--database-url", default=DEFAULT_DATABASE_URL)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def load_legacy_accounts(legacy_db: Path) -> list[LegacyAccount]:
    query = """
        SELECT
          r.id,
          lower(trim(r.email)) AS email,
          COALESCE(r.password, '') AS password,
          COALESCE(r.phone_number, '') AS phone_number,
          COALESCE(r.phone_dial_code, '') AS phone_dial_code,
          COALESCE(r.phone_country, '') AS phone_country,
          COALESCE(r.created_at, 0) AS legacy_created_at
        FROM registered_accounts r
        LEFT JOIN oauth_status o ON lower(o.email) = lower(r.email)
        WHERE lower(r.email) LIKE '%@outlook.com'
          AND COALESCE(r.last_check_status, '') != 'invalid'
          AND COALESCE(o.status, '') != 'dead'
        ORDER BY r.id ASC
    """
    with sqlite3.connect(f"file:{legacy_db}?mode=ro", uri=True) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(query).fetchall()
    return [
        LegacyAccount(
            legacy_id=int(row["id"]),
            email=str(row["email"]),
            password=str(row["password"]),
            phone_number=str(row["phone_number"]),
            phone_dial_code=str(row["phone_dial_code"]),
            phone_country=str(row["phone_country"]),
            legacy_created_at=float(row["legacy_created_at"] or 0),
        )
        for row in rows
    ]


def legacy_timestamp_to_datetime(value: float) -> datetime:
    if value <= 0:
        return datetime.now(UTC)
    return datetime.fromtimestamp(value, tz=UTC)


def import_accounts(
    accounts: list[LegacyAccount], database_url: str, dry_run: bool
) -> dict[str, int]:
    if dry_run:
        return {"selected": len(accounts), "inserted": 0, "updated": 0}

    engine = create_engine(database_url, pool_pre_ping=True)
    inserted = 0
    updated = 0
    now = datetime.now(UTC)

    with engine.begin() as conn:
        for account in accounts:
            existing = conn.execute(
                text("SELECT id FROM user_accounts WHERE lower(email) = lower(:email) LIMIT 1"),
                {"email": account.email},
            ).scalar_one_or_none()
            account_id = str(existing or f"legacy-registered-account-{account.legacy_id}")
            created_at = legacy_timestamp_to_datetime(account.legacy_created_at)

            if existing:
                updated += 1
                conn.execute(
                    text(
                        """
                        UPDATE user_accounts
                        SET
                          email = :email,
                          phone_number = :phone_number,
                          phone_dial_code = :phone_dial_code,
                          phone_country = :phone_country,
                          account_status = 'active',
                          updated_at = :updated_at
                        WHERE id = :id
                        """
                    ),
                    {
                        "id": account_id,
                        "email": account.email,
                        "phone_number": account.phone_number,
                        "phone_dial_code": account.phone_dial_code,
                        "phone_country": account.phone_country,
                        "updated_at": now,
                    },
                )
            else:
                inserted += 1
                conn.execute(
                    text(
                        """
                        INSERT INTO user_accounts (
                          id,
                          email,
                          phone_number,
                          phone_dial_code,
                          phone_country,
                          openai_user_id,
                          account_status,
                          created_at,
                          updated_at
                        )
                        VALUES (
                          :id,
                          :email,
                          :phone_number,
                          :phone_dial_code,
                          :phone_country,
                          '',
                          'active',
                          :created_at,
                          :updated_at
                        )
                        """
                    ),
                    {
                        "id": account_id,
                        "email": account.email,
                        "phone_number": account.phone_number,
                        "phone_dial_code": account.phone_dial_code,
                        "phone_country": account.phone_country,
                        "created_at": created_at,
                        "updated_at": now,
                    },
                )

            conn.execute(
                text(
                    """
                    INSERT INTO user_account_auth (
                      user_account_id,
                      password,
                      session_token,
                      access_token,
                      refresh_token,
                      cookie_header,
                      auth_cookie_header,
                      device_id,
                      csrf_token,
                      token_type,
                      scope,
                      refresh_token_status,
                      session_status,
                      created_at,
                      updated_at
                    )
                    VALUES (
                      :user_account_id,
                      :password,
                      '',
                      '',
                      '',
                      '',
                      '',
                      '',
                      '',
                      '',
                      '',
                      'missing',
                      'unknown',
                      :created_at,
                      :updated_at
                    )
                    ON CONFLICT (user_account_id) DO UPDATE
                    SET
                      password = EXCLUDED.password,
                      session_token = '',
                      access_token = '',
                      refresh_token = '',
                      cookie_header = '',
                      auth_cookie_header = '',
                      device_id = '',
                      csrf_token = '',
                      token_type = '',
                      scope = '',
                      refresh_token_status = 'missing',
                      session_status = 'unknown',
                      last_refresh_at = NULL,
                      last_session_refresh_at = NULL,
                      last_auth_error_code = '',
                      last_auth_error_message = '',
                      updated_at = EXCLUDED.updated_at
                    """
                ),
                {
                    "user_account_id": account_id,
                    "password": account.password,
                    "created_at": created_at,
                    "updated_at": now,
                },
            )

    return {"selected": len(accounts), "inserted": inserted, "updated": updated}


def main() -> None:
    args = parse_args()
    legacy_db = Path(args.legacy_db).resolve()
    if not legacy_db.exists():
        raise SystemExit(f"legacy db not found: {legacy_db}")

    accounts = load_legacy_accounts(legacy_db)
    result = import_accounts(accounts, args.database_url, args.dry_run)
    print(
        "legacy_outlook_import "
        f"selected={result['selected']} inserted={result['inserted']} updated={result['updated']} "
        f"dry_run={args.dry_run}"
    )


if __name__ == "__main__":
    main()
