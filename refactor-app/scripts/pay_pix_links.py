#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import csv
import fcntl
import os
import sys
import tempfile
import time
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Awaitable, Callable
from urllib.parse import quote

import httpx


DEFAULT_BASE_URL = "https://pix.iceaix.com"
STRIPE_LINK_PREFIX = "https://payments.stripe.com/qr/instructions/"
RUNNING_STATUSES = {"queued", "processing"}
TERMINAL_STATUSES = {"succeeded", "failed", "rejected_amount"}
RESUMABLE_STATUSES = RUNNING_STATUSES | {"poll_error", "poll_timeout"}


class PaymentApiError(RuntimeError):
    def __init__(self, code: str, message: str, *, http_status: int = 0) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.http_status = http_status


@dataclass(frozen=True)
class CsvData:
    path: Path
    fieldnames: list[str]
    rows: list[dict[str, str]]
    link_field: str
    encoding: str
    mode: int


@dataclass(frozen=True)
class PayItem:
    row_index: int
    email: str
    link: str
    pay_cdk: str
    job_id: str
    status_token: str
    pay_status: str


@dataclass(frozen=True)
class PayResult:
    item: PayItem
    status: str
    error_code: str = ""
    message: str = ""
    attempts: str = ""
    updated_at: str = ""
    finished_at: str = ""


class StartRateLimiter:
    def __init__(self, interval_s: float) -> None:
        self._interval_s = interval_s
        self._next_start = 0.0
        self._lock = asyncio.Lock()

    async def wait(self) -> None:
        if self._interval_s <= 0:
            return
        async with self._lock:
            now = time.monotonic()
            delay = max(0.0, self._next_start - now)
            if delay:
                await asyncio.sleep(delay)
            self._next_start = time.monotonic() + self._interval_s


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Submit Stripe PIX instruction links and persist payment job results."
    )
    parser.add_argument(
        "csv_path",
        nargs="?",
        type=Path,
        help="CSV path. Defaults to the newest personal_access_tokens_last_6h_*.csv.",
    )
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--concurrency", type=int, default=10)
    parser.add_argument("--start-interval", type=float, default=3.0)
    parser.add_argument("--poll-interval", type=float, default=2.0)
    parser.add_argument("--submit-timeout", type=float, default=90.0)
    parser.add_argument("--query-timeout", type=float, default=30.0)
    parser.add_argument(
        "--job-timeout",
        type=float,
        default=0.0,
        help="Maximum seconds to poll one job; 0 waits without a deadline.",
    )
    parser.add_argument(
        "--retry-terminal",
        action="store_true",
        help="Also resubmit rows whose previous pay_status is failed or rejected_amount.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate and count eligible rows without API calls or CSV writes.",
    )
    args = parser.parse_args()
    if not 1 <= args.concurrency <= 10:
        parser.error("--concurrency must be between 1 and 10")
    if args.start_interval < 0:
        parser.error("--start-interval cannot be negative")
    if not 1.5 <= args.poll_interval <= 3:
        parser.error("--poll-interval must be between 1.5 and 3 seconds")
    if args.submit_timeout < 60:
        parser.error("--submit-timeout must be at least 60 seconds")
    if args.query_timeout <= 0:
        parser.error("--query-timeout must be greater than 0")
    if args.job_timeout < 0:
        parser.error("--job-timeout cannot be negative")
    return args


def resolve_csv_path(value: Path | None) -> Path:
    if value is not None:
        path = value.expanduser().resolve()
        if not path.is_file():
            raise FileNotFoundError(f"CSV does not exist: {path}")
        return path

    app_root = Path(__file__).resolve().parents[1]
    candidates = list(
        (app_root / "runtime" / "exports").glob("personal_access_tokens_last_6h_*.csv")
    )
    if not candidates:
        raise FileNotFoundError(
            "No personal_access_tokens_last_6h_*.csv found under runtime/exports"
        )
    return max(candidates, key=lambda path: path.stat().st_mtime).resolve()


def acquire_csv_lock(path: Path):
    lock_path = path.with_name(f".{path.name}.pay.lock")
    lock_handle = lock_path.open("a+", encoding="utf-8")
    os.chmod(lock_path, 0o600)
    try:
        fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        lock_handle.close()
        raise RuntimeError(f"another payment runner is already using this CSV: {path}") from None
    return lock_handle


def detect_csv_encoding(raw: bytes) -> str:
    if raw.startswith(b"\xef\xbb\xbf"):
        return "utf-8-sig"
    try:
        raw.decode("utf-8")
    except UnicodeDecodeError:
        try:
            raw.decode("gb18030")
        except UnicodeDecodeError as exc:
            raise ValueError("CSV is neither valid UTF-8 nor GB18030") from exc
        return "gb18030"
    return "utf-8"


def ensure_field(fieldnames: list[str], rows: list[dict[str, str]], name: str) -> None:
    if name in fieldnames:
        return
    fieldnames.append(name)
    for row in rows:
        row[name] = ""


def load_csv(path: Path) -> CsvData:
    input_encoding = detect_csv_encoding(path.read_bytes())
    with path.open("r", encoding=input_encoding, newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = list(reader.fieldnames or [])
        rows = [dict(row) for row in reader]

    required = {"email", "pay_cdk"}
    missing = sorted(required - set(fieldnames))
    if missing:
        raise ValueError(f"CSV is missing required columns: {', '.join(missing)}")

    link_fields = [name for name in ("success_url", "success url") if name in fieldnames]
    if len(link_fields) != 1:
        raise ValueError("CSV must contain exactly one of success_url or success url")
    link_field = link_fields[0]

    for name in (
        "pay_status",
        "pay_error_code",
        "pay_message",
        "pay_job_id",
        "pay_status_token",
        "pay_attempts",
        "pay_updated_at",
        "pay_finished_at",
    ):
        ensure_field(fieldnames, rows, name)

    return CsvData(
        path=path,
        fieldnames=fieldnames,
        rows=rows,
        link_field=link_field,
        encoding="utf-8-sig",
        mode=path.stat().st_mode & 0o777,
    )


def save_csv(csv_data: CsvData) -> None:
    temp_name = ""
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding=csv_data.encoding,
            newline="",
            dir=csv_data.path.parent,
            prefix=f".{csv_data.path.name}.",
            suffix=".pay.tmp",
            delete=False,
        ) as handle:
            temp_name = handle.name
            writer = csv.DictWriter(
                handle,
                fieldnames=csv_data.fieldnames,
                extrasaction="ignore",
            )
            writer.writeheader()
            writer.writerows(csv_data.rows)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temp_name, csv_data.mode)
        os.replace(temp_name, csv_data.path)
    finally:
        if temp_name:
            Path(temp_name).unlink(missing_ok=True)


def collect_items(csv_data: CsvData, *, retry_terminal: bool) -> list[PayItem]:
    items: list[PayItem] = []
    for row_index, row in enumerate(csv_data.rows):
        link = (row.get(csv_data.link_field) or "").strip()
        pay_cdk = (row.get("pay_cdk") or "").strip()
        status = (row.get("pay_status") or "").strip().lower()
        job_id = (row.get("pay_job_id") or "").strip()
        status_token = (row.get("pay_status_token") or "").strip()
        if not link or not pay_cdk or not link.startswith(STRIPE_LINK_PREFIX):
            continue
        if status == "succeeded" or status == "submit_unknown":
            continue
        if status in TERMINAL_STATUSES and not retry_terminal:
            continue
        if status in RESUMABLE_STATUSES and (not job_id or not status_token):
            continue
        if status not in {"", "submit_failed"} | RESUMABLE_STATUSES | TERMINAL_STATUSES:
            continue
        items.append(
            PayItem(
                row_index=row_index,
                email=(row.get("email") or "").strip(),
                link=link,
                pay_cdk=pay_cdk,
                job_id=job_id,
                status_token=status_token,
                pay_status=status,
            )
        )
    return items


def parse_response(response: httpx.Response, operation: str) -> dict[str, Any]:
    try:
        payload = response.json()
    except ValueError as exc:
        raise PaymentApiError(
            "invalid_response",
            f"{operation}: HTTP {response.status_code}, response is not JSON",
            http_status=response.status_code,
        ) from exc
    if not isinstance(payload, dict):
        raise PaymentApiError(
            "invalid_response",
            f"{operation}: HTTP {response.status_code}, response is not an object",
            http_status=response.status_code,
        )
    if response.is_success:
        return payload
    code = str(payload.get("code") or f"http_{response.status_code}")
    message = str(payload.get("message") or operation)
    raise PaymentApiError(code, message, http_status=response.status_code)


def sanitize(value: str, item: PayItem, *extra_secrets: str) -> str:
    result = value.replace("\n", " ")
    for secret in (item.pay_cdk, item.link, item.status_token, *extra_secrets):
        if secret:
            result = result.replace(secret, "<redacted>")
    return result[:1000]


async def submit_job(
    client: httpx.AsyncClient,
    item: PayItem,
    *,
    timeout_s: float,
) -> tuple[str, str, str, str]:
    response = await client.post(
        "/api/submit",
        json={"cdk": item.pay_cdk, "link": item.link},
        timeout=timeout_s,
    )
    payload = parse_response(response, "submit")
    if response.status_code != 202:
        raise PaymentApiError(
            "unexpected_status",
            f"submit: expected HTTP 202, got {response.status_code}",
            http_status=response.status_code,
        )
    job_id = str(payload.get("job_id") or "").strip()
    status_token = str(payload.get("status_token") or "").strip()
    status = str(payload.get("status") or "queued").strip().lower()
    message = str(payload.get("message") or "").strip()
    if not job_id or not status_token:
        raise PaymentApiError(
            "invalid_response",
            "submit response is missing job_id or status_token",
            http_status=response.status_code,
        )
    return job_id, status_token, status, message


async def poll_job(
    client: httpx.AsyncClient,
    *,
    item: PayItem,
    job_id: str,
    status_token: str,
    poll_interval_s: float,
    query_timeout_s: float,
    job_timeout_s: float,
) -> dict[str, Any]:
    started_at = time.monotonic()
    path = f"/api/jobs/{quote(job_id, safe='')}"
    while True:
        if job_timeout_s and time.monotonic() - started_at >= job_timeout_s:
            raise PaymentApiError(
                "poll_timeout",
                f"job did not reach a terminal status after {job_timeout_s:g}s",
            )
        await asyncio.sleep(poll_interval_s)
        try:
            response = await client.get(
                path,
                params={"token": status_token},
                headers={"Cache-Control": "no-store"},
                timeout=query_timeout_s,
            )
        except httpx.HTTPError:
            continue
        payload = parse_response(response, "query job")
        job = payload.get("job")
        if not isinstance(job, dict):
            raise PaymentApiError("invalid_response", "query response is missing job")
        status = str(job.get("status") or "").strip().lower()
        if status in RUNNING_STATUSES:
            continue
        if status not in TERMINAL_STATUSES:
            raise PaymentApiError(
                "unsupported_status",
                f"query returned unsupported status {status or '<blank>'}",
            )
        return job


PersistCallback = Callable[[PayItem, dict[str, str]], Awaitable[None]]


async def process_item(
    client: httpx.AsyncClient,
    item: PayItem,
    *,
    semaphore: asyncio.Semaphore,
    start_limiter: StartRateLimiter,
    persist: PersistCallback,
    submit_timeout_s: float,
    poll_interval_s: float,
    query_timeout_s: float,
    job_timeout_s: float,
) -> PayResult:
    async with semaphore:
        job_id = item.job_id
        status_token = item.status_token
        if not job_id or not status_token or item.pay_status not in RESUMABLE_STATUSES:
            await start_limiter.wait()
            try:
                job_id, status_token, status, message = await submit_job(
                    client,
                    item,
                    timeout_s=submit_timeout_s,
                )
            except httpx.TimeoutException as exc:
                message = sanitize(f"{type(exc).__name__}: {exc}", item)
                result = PayResult(
                    item=item,
                    status="submit_unknown",
                    error_code="submit_timeout_unknown",
                    message=message,
                )
                await persist_result(persist, result)
                return result
            except httpx.HTTPError as exc:
                message = sanitize(f"{type(exc).__name__}: {exc}", item)
                result = PayResult(
                    item=item,
                    status="submit_failed",
                    error_code="network_error",
                    message=message,
                )
                await persist_result(persist, result)
                return result
            except PaymentApiError as exc:
                result = PayResult(
                    item=item,
                    status="submit_failed",
                    error_code=exc.code,
                    message=sanitize(exc.message, item),
                )
                await persist_result(persist, result)
                return result

            await persist(
                item,
                {
                    "pay_status": status,
                    "pay_error_code": "",
                    "pay_message": sanitize(message, item, status_token),
                    "pay_job_id": job_id,
                    "pay_status_token": status_token,
                    "pay_attempts": "",
                    "pay_updated_at": "",
                    "pay_finished_at": "",
                },
            )
            print(
                f"submitted row={item.row_index + 2} "
                f"email={item.email or '<blank>'} status={status}"
            )

        try:
            job = await poll_job(
                client,
                item=item,
                job_id=job_id,
                status_token=status_token,
                poll_interval_s=poll_interval_s,
                query_timeout_s=query_timeout_s,
                job_timeout_s=job_timeout_s,
            )
        except PaymentApiError as exc:
            result = PayResult(
                item=item,
                status="poll_timeout" if exc.code == "poll_timeout" else "poll_error",
                error_code=exc.code,
                message=sanitize(exc.message, item, status_token),
            )
            await persist_result(persist, result)
            return result

        result = PayResult(
            item=item,
            status=str(job.get("status") or "").strip().lower(),
            error_code=str(job.get("error_code") or "").strip(),
            message=sanitize(str(job.get("message") or "").strip(), item, status_token),
            attempts=str(job.get("attempts") or ""),
            updated_at=str(job.get("updated_at") or "").strip(),
            finished_at=str(job.get("finished_at") or "").strip(),
        )
        await persist_result(persist, result)
        return result


async def persist_result(persist: PersistCallback, result: PayResult) -> None:
    await persist(
        result.item,
        {
            "pay_status": result.status,
            "pay_error_code": result.error_code,
            "pay_message": result.message,
            "pay_attempts": result.attempts,
            "pay_updated_at": result.updated_at,
            "pay_finished_at": result.finished_at,
        },
    )


async def run(args: argparse.Namespace, csv_data: CsvData) -> int:
    items = collect_items(csv_data, retry_terminal=args.retry_terminal)
    status_counts = Counter(item.pay_status or "<blank>" for item in items)
    print(f"CSV: {csv_data.path}")
    print(f"Eligible rows: {len(items)}")
    print(f"Input pay statuses: {dict(status_counts)}")
    print(f"Max concurrency: {args.concurrency}")
    print(f"Start interval: {args.start_interval:g}s")
    print(f"Poll interval: {args.poll_interval:g}s")
    if args.dry_run or not items:
        return 0

    write_lock = asyncio.Lock()

    async def persist(item: PayItem, values: dict[str, str]) -> None:
        async with write_lock:
            csv_data.rows[item.row_index].update(values)
            save_csv(csv_data)

    semaphore = asyncio.Semaphore(args.concurrency)
    start_limiter = StartRateLimiter(args.start_interval)
    timeout = httpx.Timeout(args.query_timeout)
    results: list[PayResult] = []
    async with httpx.AsyncClient(
        base_url=args.base_url.rstrip("/"),
        timeout=timeout,
        follow_redirects=False,
        trust_env=False,
    ) as client:
        tasks = [
            asyncio.create_task(
                process_item(
                    client,
                    item,
                    semaphore=semaphore,
                    start_limiter=start_limiter,
                    persist=persist,
                    submit_timeout_s=args.submit_timeout,
                    poll_interval_s=args.poll_interval,
                    query_timeout_s=args.query_timeout,
                    job_timeout_s=args.job_timeout,
                )
            )
            for item in items
        ]
        for completed, task in enumerate(asyncio.as_completed(tasks), start=1):
            result = await task
            results.append(result)
            print(
                f"[{completed}/{len(items)}] row={result.item.row_index + 2} "
                f"email={result.item.email or '<blank>'} status={result.status} "
                f"error_code={result.error_code or '<blank>'}"
            )

    counts = Counter(result.status for result in results)
    print(f"Finished: processed={len(results)} statuses={dict(counts)}")
    return 0


def main() -> int:
    args = parse_args()
    try:
        csv_path = resolve_csv_path(args.csv_path)
        lock_handle = acquire_csv_lock(csv_path)
        try:
            csv_data = load_csv(csv_path)
            return asyncio.run(run(args, csv_data))
        finally:
            lock_handle.close()
    except (FileNotFoundError, ValueError, RuntimeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("interrupted", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
