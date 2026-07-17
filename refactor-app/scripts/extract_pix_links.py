#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import csv
import fcntl
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx


DEFAULT_BASE_URL = "https://pix.olimap.top"
FAILED_STATUSES = {"fail", "failed", "failure", "error"}
RUNNING_JOB_STATUSES = {"queued", "running"}
TERMINAL_JOB_STATUSES = {"success", "failed", "cancelled", "interrupted"}


class PixApiError(RuntimeError):
    pass


@dataclass(frozen=True)
class CsvData:
    path: Path
    fieldnames: list[str]
    rows: list[dict[str, str]]
    success_url_field: str
    error_field: str
    encoding: str
    mode: int


@dataclass(frozen=True)
class WorkItem:
    row_index: int
    email: str
    access_token: str
    cdk: str


@dataclass(frozen=True)
class WorkResult:
    item: WorkItem
    success_url: str = ""
    error: str = ""

    @property
    def succeeded(self) -> bool:
        return bool(self.success_url)


def parse_row_range(value: str) -> tuple[int, int]:
    try:
        start_text, end_text = value.split("-", maxsplit=1)
        start = int(start_text)
        end = int(end_text)
    except (TypeError, ValueError) as exc:
        raise argparse.ArgumentTypeError("row range must use START-END") from exc
    if start < 2 or end < start:
        raise argparse.ArgumentTypeError("row range must start at row 2 and end after start")
    return start, end


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Create PIX jobs from a CSV, processing one CDK at a time with bounded "
            "concurrency inside that CDK."
        )
    )
    parser.add_argument(
        "csv_path",
        nargs="?",
        type=Path,
        help="CSV path. Defaults to the newest personal_access_tokens_last_6h_*.csv.",
    )
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--concurrency", type=int, default=10)
    parser.add_argument(
        "--batch-size",
        type=int,
        default=10,
        help="Maximum credential rows submitted with one CDK.",
    )
    parser.add_argument(
        "--max-cdks",
        type=int,
        default=0,
        help="Maximum distinct CDKs to process in CSV order; 0 processes all eligible CDKs.",
    )
    parser.add_argument("--poll-interval", type=float, default=1.5)
    parser.add_argument("--request-timeout", type=float, default=30.0)
    parser.add_argument(
        "--start-interval",
        type=float,
        default=0.0,
        help="Seconds between starting adjacent credential jobs within one CDK batch.",
    )
    parser.add_argument(
        "--retry-rows",
        type=parse_row_range,
        metavar="START-END",
        help="Retry this inclusive CSV row range, including rows currently marked failed.",
    )
    parser.add_argument(
        "--exclude-error-containing",
        action="append",
        default=[],
        metavar="TEXT",
        help="Skip rows whose current error contains this text. May be specified repeatedly.",
    )
    parser.add_argument(
        "--global-pool",
        action="store_true",
        help="Do not group by CDK; run every eligible row in one bounded task pool.",
    )
    parser.add_argument(
        "--job-timeout",
        type=float,
        default=0.0,
        help="Maximum seconds to poll one job; 0 waits for a terminal status without a deadline.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help=(
            "Only validate the CSV and report eligible rows; "
            "do not call the API or write the CSV."
        ),
    )
    args = parser.parse_args()
    if args.concurrency < 1:
        parser.error("--concurrency must be at least 1")
    if args.batch_size < 1:
        parser.error("--batch-size must be at least 1")
    if args.max_cdks < 0:
        parser.error("--max-cdks cannot be negative")
    if args.poll_interval <= 0:
        parser.error("--poll-interval must be greater than 0")
    if args.request_timeout <= 0:
        parser.error("--request-timeout must be greater than 0")
    if args.start_interval < 0:
        parser.error("--start-interval cannot be negative")
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
    lock_path = path.with_name(f".{path.name}.pix.lock")
    lock_handle = lock_path.open("a+", encoding="utf-8")
    os.chmod(lock_path, 0o600)
    try:
        fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        lock_handle.close()
        raise RuntimeError(f"another extractor is already using this CSV: {path}") from None
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


def load_csv(path: Path) -> CsvData:
    input_encoding = detect_csv_encoding(path.read_bytes())
    with path.open("r", encoding=input_encoding, newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = list(reader.fieldnames or [])
        rows = [dict(row) for row in reader]

    required = {"email", "access_token", "cdk"}
    missing = sorted(required - set(fieldnames))
    if missing:
        raise ValueError(f"CSV is missing required columns: {', '.join(missing)}")

    success_url_fields = [name for name in ("success_url", "success url") if name in fieldnames]
    if len(success_url_fields) > 1:
        raise ValueError("CSV contains both success_url and success url; keep only one")
    if success_url_fields:
        success_url_field = success_url_fields[0]
    else:
        success_url_field = "success_url"
        fieldnames.append(success_url_field)
        for row in rows:
            row[success_url_field] = ""

    if "status" not in fieldnames:
        fieldnames.append("status")
        for row in rows:
            row["status"] = ""

    error_fields = [name for name in ("error", "error_message") if name in fieldnames]
    if len(error_fields) > 1:
        raise ValueError("CSV contains both error and error_message; keep only one")
    if error_fields:
        error_field = error_fields[0]
    else:
        error_field = "error"
        fieldnames.append(error_field)
        for row in rows:
            row[error_field] = ""

    return CsvData(
        path=path,
        fieldnames=fieldnames,
        rows=rows,
        success_url_field=success_url_field,
        error_field=error_field,
        encoding="utf-8-sig",
        mode=path.stat().st_mode & 0o777,
    )


def collect_work(
    csv_data: CsvData,
    batch_size: int,
    retry_rows: tuple[int, int] | None,
    excluded_error_texts: list[str],
    global_pool: bool,
) -> list[list[WorkItem]]:
    grouped: dict[str, list[WorkItem]] = {}
    eligible: list[WorkItem] = []
    for row_index, row in enumerate(csv_data.rows):
        csv_row_number = row_index + 2
        is_explicit_retry = retry_rows is not None
        if retry_rows is not None and not (retry_rows[0] <= csv_row_number <= retry_rows[1]):
            continue
        cdk = (row.get("cdk") or "").strip()
        success_url = (row.get(csv_data.success_url_field) or "").strip()
        status = (row.get("status") or "").strip().lower()
        error = row.get(csv_data.error_field) or ""
        if any(text in error for text in excluded_error_texts):
            continue
        if not cdk or success_url or (status in FAILED_STATUSES and not is_explicit_retry):
            continue

        access_token = (row.get("access_token") or "").strip()
        email = (row.get("email") or "").strip()
        item = WorkItem(
            row_index=row_index,
            email=email,
            access_token=access_token,
            cdk=cdk,
        )
        eligible.append(item)
        grouped.setdefault(cdk, []).append(item)

    if global_pool:
        return [eligible] if eligible else []

    batches: list[list[WorkItem]] = []
    for items in grouped.values():
        for start in range(0, len(items), batch_size):
            batches.append(items[start : start + batch_size])
    return batches


def save_csv(csv_data: CsvData) -> None:
    temp_path = csv_data.path.with_name(
        f".{csv_data.path.name}.{os.getpid()}.{time.time_ns()}.tmp"
    )
    try:
        with temp_path.open("w", encoding=csv_data.encoding, newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=csv_data.fieldnames, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(csv_data.rows)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temp_path, csv_data.mode)
        os.replace(temp_path, csv_data.path)
    finally:
        temp_path.unlink(missing_ok=True)


def parse_json_response(response: httpx.Response, operation: str) -> dict[str, Any]:
    try:
        payload = response.json()
    except ValueError as exc:
        message = f"{operation}: HTTP {response.status_code}, response is not JSON"
        raise PixApiError(message) from exc
    if not isinstance(payload, dict):
        raise PixApiError(f"{operation}: HTTP {response.status_code}, response is not an object")
    if response.is_success:
        return payload

    error = payload.get("error")
    if isinstance(error, dict):
        code = str(error.get("code") or "unknown_error")
        message = str(error.get("message") or "")
        detail = f"{code}: {message}" if message else code
    else:
        detail = "unknown_error"
    raise PixApiError(f"{operation}: HTTP {response.status_code}, {detail}")


async def create_job(client: httpx.AsyncClient, item: WorkItem) -> tuple[str, str]:
    response = await client.post(
        "/api/v1/jobs",
        json={"credential": item.access_token, "cdk": item.cdk},
    )
    payload = parse_json_response(response, "create job")
    if response.status_code != 202:
        raise PixApiError(f"create job: expected HTTP 202, got {response.status_code}")

    job_id = str(payload.get("job_id") or "").strip()
    job_token = str(payload.get("job_token") or "").strip()
    if not job_id or not job_token:
        raise PixApiError("create job: response is missing job_id or job_token")
    return job_id, job_token


async def poll_job(
    client: httpx.AsyncClient,
    *,
    job_id: str,
    job_token: str,
    poll_interval: float,
    job_timeout: float,
) -> str:
    started_at = time.monotonic()
    headers = {"Authorization": f"Bearer {job_token}"}
    status_path = f"/api/v1/jobs/{quote(job_id, safe='')}"

    while True:
        if job_timeout and time.monotonic() - started_at >= job_timeout:
            raise PixApiError(f"poll job: no terminal status after {job_timeout:g}s")
        await asyncio.sleep(poll_interval)
        response = await client.get(status_path, headers=headers)
        payload = parse_json_response(response, "poll job")
        job = payload.get("job")
        if not isinstance(job, dict):
            raise PixApiError("poll job: response is missing job")

        status = str(job.get("status") or "").strip().lower()
        if status in RUNNING_JOB_STATUSES:
            continue
        if status not in TERMINAL_JOB_STATUSES:
            raise PixApiError(f"poll job: unsupported status {status or '<blank>'}")
        if status != "success":
            details: list[str] = []
            error = job.get("error")
            if isinstance(error, dict):
                code = str(error.get("code") or "").strip()
                message = str(error.get("message") or "").strip()
                details.extend(value for value in (code, message) if value)
            elif error:
                details.append(str(error).strip())
            for key in ("error_message", "message"):
                value = str(job.get(key) or "").strip()
                if value and value not in details:
                    details.append(value)
            suffix = f": {'; '.join(details)}" if details else ""
            raise PixApiError(f"poll job: terminal status {status}{suffix}")

        result = job.get("result")
        if not isinstance(result, dict):
            raise PixApiError("poll job: successful job has no result")
        link = str(result.get("pix_hosted_instructions_url") or "").strip()
        if not link:
            raise PixApiError(
                "poll job: successful job has no result.pix_hosted_instructions_url"
            )
        return link


def sanitized_error(exc: BaseException, item: WorkItem) -> str:
    message = f"{type(exc).__name__}: {exc}"
    for secret in (item.access_token, item.cdk):
        if secret:
            message = message.replace(secret, "<redacted>")
    return message.replace("\n", " ")[:500]


async def process_item(
    client: httpx.AsyncClient,
    item: WorkItem,
    *,
    semaphore: asyncio.Semaphore,
    poll_interval: float,
    job_timeout: float,
    start_delay: float,
) -> WorkResult:
    if start_delay:
        await asyncio.sleep(start_delay)
    async with semaphore:
        if not item.access_token:
            return WorkResult(item=item, error="CSV access_token is blank")
        try:
            job_id, job_token = await create_job(client, item)
            link = await poll_job(
                client,
                job_id=job_id,
                job_token=job_token,
                poll_interval=poll_interval,
                job_timeout=job_timeout,
            )
            return WorkResult(item=item, success_url=link)
        except (httpx.HTTPError, PixApiError) as exc:
            return WorkResult(item=item, error=sanitized_error(exc, item))


async def run(args: argparse.Namespace, csv_data: CsvData) -> int:
    groups = collect_work(
        csv_data,
        args.batch_size,
        args.retry_rows,
        args.exclude_error_containing,
        args.global_pool,
    )
    if args.max_cdks:
        groups = groups[: args.max_cdks]
    total = sum(len(items) for items in groups)
    mode = "global pool" if args.global_pool else "CDK groups"
    print(f"CSV: {csv_data.path}")
    print(f"Eligible rows: {total}")
    print(f"Execution mode: {mode}")
    print(f"Batches: {len(groups)}")
    if not args.global_pool:
        print(f"Rows per CDK: {args.batch_size}")
        print("Cross-CDK concurrency: 1")
    print(f"Max concurrency: {args.concurrency}")
    print(f"Start interval: {args.start_interval:g}s")
    if args.dry_run or not total:
        return 0

    completed = 0
    succeeded = 0
    failed = 0
    timeout = httpx.Timeout(args.request_timeout)
    async with httpx.AsyncClient(
        base_url=args.base_url.rstrip("/"),
        timeout=timeout,
        follow_redirects=False,
        trust_env=False,
    ) as client:
        for group_number, items in enumerate(groups, start=1):
            label = "Global pool" if args.global_pool else "CDK group"
            print(f"{label} {group_number}/{len(groups)}: {len(items)} row(s)")
            semaphore = asyncio.Semaphore(args.concurrency)
            tasks = [
                asyncio.create_task(
                    process_item(
                        client,
                        item,
                        semaphore=semaphore,
                        poll_interval=args.poll_interval,
                        job_timeout=args.job_timeout,
                        start_delay=item_number * args.start_interval,
                    )
                )
                for item_number, item in enumerate(items)
            ]
            for task in asyncio.as_completed(tasks):
                result = await task
                row = csv_data.rows[result.item.row_index]
                completed += 1
                if result.succeeded:
                    row["status"] = "success"
                    row[csv_data.success_url_field] = result.success_url
                    row[csv_data.error_field] = ""
                    succeeded += 1
                    outcome = "success"
                else:
                    row["status"] = "fail"
                    row[csv_data.error_field] = result.error
                    failed += 1
                    outcome = f"fail ({result.error})"
                save_csv(csv_data)
                print(
                    f"[{completed}/{total}] row={result.item.row_index + 2} "
                    f"email={result.item.email or '<blank>'} {outcome}"
                )

    print(f"Finished: success={succeeded}, fail={failed}, processed={completed}")
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
