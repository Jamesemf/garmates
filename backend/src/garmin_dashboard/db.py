"""SQLite engine and session handling."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Engine, create_engine, event, inspect, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


class Base(DeclarativeBase):
    pass


_engine: Engine | None = None
_session_factory: sessionmaker[Session] | None = None


def _sqlite_pragmas(dbapi_connection, _record) -> None:  # noqa: ANN001
    cursor = dbapi_connection.cursor()
    # WAL lets the background sync write while dashboard requests read.
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA busy_timeout=10000")
    cursor.close()


def init_engine(database_url: str) -> Engine:
    """Create the engine and tables. Called once at startup (and by tests)."""
    global _engine, _session_factory
    if _engine is not None:
        _engine.dispose()
    _engine = create_engine(database_url, connect_args={"check_same_thread": False})
    event.listen(_engine, "connect", _sqlite_pragmas)
    _session_factory = sessionmaker(bind=_engine, expire_on_commit=False)

    from . import models  # noqa: F401  (register tables)

    Base.metadata.create_all(_engine)
    _add_missing_columns(_engine)
    return _engine


def _add_missing_columns(engine: Engine) -> None:
    """Minimal forward migration: add new nullable columns to tables created by older versions.

    create_all() only creates missing tables, so a column added to a model later would be
    absent from an existing database. Only nullable columns without server defaults are
    added; anything more involved needs a real migration.
    """
    inspector = inspect(engine)
    with engine.begin() as conn:
        for table in Base.metadata.sorted_tables:
            if not inspector.has_table(table.name):
                continue
            existing = {col["name"] for col in inspector.get_columns(table.name)}
            for column in table.columns:
                if column.name in existing or not column.nullable:
                    continue
                col_type = column.type.compile(dialect=engine.dialect)
                conn.execute(
                    text(f'ALTER TABLE "{table.name}" ADD COLUMN "{column.name}" {col_type}')
                )


def get_engine() -> Engine:
    if _engine is None:
        raise RuntimeError("Database not initialised; call init_engine() first")
    return _engine


@contextmanager
def session_scope() -> Iterator[Session]:
    """Transactional session for scripts and background jobs."""
    if _session_factory is None:
        raise RuntimeError("Database not initialised; call init_engine() first")
    session = _session_factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_db() -> Iterator[Session]:
    """FastAPI dependency."""
    with session_scope() as session:
        yield session
