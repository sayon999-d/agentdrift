"""Async DB engine + session factory. Falls back to None when no DATABASE_URL is set."""

from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import get_settings

log = logging.getLogger("agentdrift.db")

_engine = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def get_engine():
    global _engine, _session_factory
    settings = get_settings()
    url = settings.async_db_url
    if not url:
        return None
    if _engine is None:
        _engine = create_async_engine(url, pool_pre_ping=True, pool_size=10, max_overflow=20)
        _session_factory = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)
        log.info("DB engine created")
    return _engine


def get_session_factory():
    get_engine()
    return _session_factory


def db_configured() -> bool:
    return bool(get_settings().async_db_url)


async def dispose_engine() -> None:
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _session_factory = None
