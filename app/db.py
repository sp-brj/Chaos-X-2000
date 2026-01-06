from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker


def _database_url() -> str | None:
    # Railway often provides DATABASE_URL; sometimes DATABASE_PRIVATE_URL.
    return os.environ.get("DATABASE_URL") or os.environ.get("DATABASE_PRIVATE_URL")


def get_engine() -> Engine | None:
    url = _database_url()
    if not url:
        return None
    # Railway typically sets DATABASE_URL like: postgresql://...
    # SQLAlchemy defaults "postgresql://" to psycopg2, but we use psycopg v3.
    url_obj = make_url(url)
    if url_obj.drivername in ("postgresql", "postgres"):
        url_obj = url_obj.set(drivername="postgresql+psycopg")
    return create_engine(url_obj, pool_pre_ping=True)


def get_sessionmaker(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


@contextmanager
def session_scope(SessionLocal: sessionmaker[Session]) -> Iterator[Session]:
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

