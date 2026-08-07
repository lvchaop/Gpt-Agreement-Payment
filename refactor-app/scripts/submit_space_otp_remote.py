from __future__ import annotations

import argparse
import json
from typing import Any

from refactor_app.application.workflows.space_session_otp_remote import (
    SessionOtpExecutorClient,
    run_remote_space_session_otp_submit,
)
from refactor_app.config.settings import Settings
from refactor_app.infrastructure.db.engine import make_engine, make_session_factory


def parse_args() -> argparse.Namespace:
    settings = Settings()
    parser = argparse.ArgumentParser(
        description=(
            "Submit up to 1000 otp_collected snapshots for one Space through the remote "
            "session OTP executor, then write terminal results back to the existing snapshot table."
        )
    )
    parser.add_argument("space_id", help="Local spaces.id")
    parser.add_argument("--base-url", default=settings.session_otp_executor_base_url)
    parser.add_argument("--api-key", default=settings.session_otp_executor_api_key)
    parser.add_argument("--poll-interval", type=float, default=0.5)
    parser.add_argument("--poll-timeout", type=float, default=900.0)
    parser.add_argument("--request-timeout", type=float, default=60.0)
    parser.add_argument("--barrier-timeout", type=float, default=120.0)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Only count and validate selected snapshots; do not call the executor or update DB.",
    )
    args = parser.parse_args()
    if args.poll_interval <= 0:
        parser.error("--poll-interval must be greater than zero")
    if args.poll_timeout <= 0:
        parser.error("--poll-timeout must be greater than zero")
    if args.request_timeout <= 0:
        parser.error("--request-timeout must be greater than zero")
    if not 1 <= args.barrier_timeout <= 300:
        parser.error("--barrier-timeout must be between 1 and 300 seconds")
    if not args.dry_run and not str(args.base_url or "").strip():
        parser.error("--base-url or INVITE_EXECUTOR_BASE_URL is required")
    if not args.dry_run and not str(args.api_key or "").strip():
        parser.error("--api-key or INVITE_EXECUTOR_API_KEY is required")
    return args


def _print_json(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True), flush=True)


def main() -> int:
    args = parse_args()
    settings = Settings()
    engine = make_engine(settings)
    session_factory = make_session_factory(engine)
    client: SessionOtpExecutorClient | None = None
    try:
        if not args.dry_run:
            client = SessionOtpExecutorClient(
                base_url=args.base_url,
                api_key=args.api_key,
                request_timeout_s=args.request_timeout,
            )
        result = run_remote_space_session_otp_submit(
            session_factory=session_factory,
            space_id=args.space_id,
            client=client,
            dry_run=args.dry_run,
            poll_interval_s=args.poll_interval,
            poll_timeout_s=args.poll_timeout,
            barrier_timeout_s=args.barrier_timeout,
            on_submitted=lambda batch_id, count: _print_json(
                {"event": "submitted", "batch_id": batch_id, "submitted_count": count}
            ),
        )
        _print_json(result)
        if result["status"] in {"dry_run", "no_candidates", "succeeded"}:
            return 0
        return 1
    finally:
        if client is not None:
            client.close()
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
