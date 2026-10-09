"""Apply migrations/001_init.sql to Supabase Postgres (sync driver, stdlib-friendly).

Usage:
    python scripts/migrate.py
    SYNC_DATABASE_URL=postgresql://... python scripts/migrate.py
Requires: pip install psycopg[binary]  (or asyncpg) — falls back gracefully.
"""

from __future__ import annotations

import os
import pathlib
import sys

from dotenv import load_dotenv

load_dotenv()

SQL_PATH = pathlib.Path(__file__).resolve().parent.parent / "migrations" / "001_init.sql"


def _db_url() -> str:
    url = (
        os.getenv("SYNC_DATABASE_URL")
        or os.getenv("SUPABASE_DB_URL")
        or os.getenv("DATABASE_URL")
        or ""
    ).strip()
    if not url:
        print("ERROR: set SYNC_DATABASE_URL (or SUPABASE_DB_URL / DATABASE_URL)", file=sys.stderr)
        sys.exit(1)
    # psycopg wants postgresql:// — strip async driver suffix
    url = url.replace("postgresql+asyncpg://", "postgresql://").replace(
        "postgresql+psycopg://", "postgresql://"
    )
    return url


def main() -> None:
    url = _db_url()
    sql = SQL_PATH.read_text(encoding="utf-8")
    print(f"Applying {SQL_PATH.name} ...")
    try:
        import psycopg

        with psycopg.connect(url, autocommit=True) as conn, conn.cursor() as cur:
            cur.execute(sql)
        print("Migration applied (psycopg).")
    except ImportError:
        import asyncio

        import asyncpg

        async def _run() -> None:
            # asyncpg wants postgres:// without +asyncpg
            clean = url.replace("postgresql://", "postgres://", 1)
            conn = await asyncpg.connect(clean)
            try:
                await conn.execute(sql)
            finally:
                await conn.close()

        asyncio.run(_run())
        print("Migration applied (asyncpg).")


if __name__ == "__main__":
    main()
