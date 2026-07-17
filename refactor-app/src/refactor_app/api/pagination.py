from __future__ import annotations

from typing import Any, Iterable

from sqlalchemy import func, select
from sqlalchemy.orm import Session
from sqlalchemy.sql import Select


DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 200


def page_values(page: int, page_size: int) -> tuple[int, int]:
    return max(1, int(page or 1)), min(MAX_PAGE_SIZE, max(1, int(page_size or DEFAULT_PAGE_SIZE)))


def total_for(session: Session, stmt: Select[Any]) -> int:
    count_stmt = select(func.count()).select_from(stmt.order_by(None).subquery())
    return int(session.scalar(count_stmt) or 0)


def page_payload(
    *,
    items: Iterable[dict[str, Any]],
    page: int,
    page_size: int,
    total: int,
    sort: str,
) -> dict[str, Any]:
    return {
        "items": list(items),
        "page": page,
        "page_size": page_size,
        "total": total,
        "sort": sort,
    }
