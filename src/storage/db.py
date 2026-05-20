"""SQLite engine + session helpers.

The engine is lazily constructed against ``config.DB_URL`` on first use.
Tests can swap to an isolated temp DB via ``use_engine_for_url`` /
``reset_engine``.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator, Optional

from sqlalchemy.engine import Engine
from sqlmodel import Session, SQLModel, create_engine

# Importing this module pulls in our table classes so SQLModel.metadata
# knows about them before create_all runs.
import src.storage.models  # noqa: F401
from src.config import DB_URL


_engine: Optional[Engine] = None
_initialised: bool = False


def get_engine() -> Engine:
    """Return the cached engine, building it from ``config.DB_URL`` if needed."""
    global _engine
    if _engine is None:
        _engine = create_engine(DB_URL, echo=False)
    return _engine


def init_db() -> None:
    """Create tables if they don't exist (idempotent)."""
    global _initialised
    if _initialised:
        return
    SQLModel.metadata.create_all(get_engine())
    _initialised = True


def use_engine_for_url(url: str) -> None:
    """Replace the cached engine with a fresh one for ``url``. For tests."""
    global _engine, _initialised
    if _engine is not None:
        _engine.dispose()
    _engine = create_engine(url, echo=False)
    _initialised = False


def reset_engine() -> None:
    """Dispose and clear the cached engine. For test teardown."""
    global _engine, _initialised
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _initialised = False


@contextmanager
def get_session() -> Iterator[Session]:
    """Yield a session, auto-initialising tables on first use."""
    init_db()
    with Session(get_engine()) as session:
        yield session
