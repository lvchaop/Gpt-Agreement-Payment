from __future__ import annotations

from collections.abc import Generator

from sqlalchemy.orm import Session

from refactor_app.config.settings import get_settings
from refactor_app.infrastructure.db.engine import make_engine, make_session_factory

_engine = make_engine(get_settings())
_session_factory = make_session_factory(_engine)


def get_db_session() -> Generator[Session]:
    with _session_factory() as session:
        yield session
