from contextlib import asynccontextmanager
from typing import AsyncGenerator
import psycopg
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool
from app.config import DATABASE_URL

pool: AsyncConnectionPool | None = None

async def init_db():
    global pool
    if pool is None:
        pool = AsyncConnectionPool(
            DATABASE_URL,
            min_size=1,
            max_size=20,
            open=False,
            kwargs={"autocommit": False, "row_factory": dict_row}
        )
        await pool.open()

    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute("""
                CREATE TABLE IF NOT EXISTS slots (
                    id TEXT PRIMARY KEY,
                    provider TEXT NOT NULL,
                    start TIMESTAMPTZ NOT NULL,
                    "end" TIMESTAMPTZ NOT NULL
                );

                CREATE TABLE IF NOT EXISTS bookings (
                    id TEXT PRIMARY KEY,
                    slot_id TEXT NOT NULL REFERENCES slots(id),
                    name TEXT NOT NULL,
                    email TEXT NOT NULL,
                    status TEXT NOT NULL CHECK(status IN ('confirmed', 'cancelled')),
                    created_at TIMESTAMPTZ NOT NULL
                );

                CREATE UNIQUE INDEX IF NOT EXISTS idx_confirmed_slot ON bookings (slot_id) WHERE status = 'confirmed';
                CREATE INDEX IF NOT EXISTS idx_bookings_email ON bookings (LOWER(email));
                CREATE INDEX IF NOT EXISTS idx_bookings_created ON bookings (created_at, id);

                CREATE TABLE IF NOT EXISTS idempotency_records (
                    key TEXT PRIMARY KEY,
                    body_hash TEXT NOT NULL,
                    status_code INTEGER NOT NULL,
                    response_body TEXT NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL
                );

                CREATE TABLE IF NOT EXISTS email_attempts (
                    id BIGSERIAL PRIMARY KEY,
                    email TEXT NOT NULL,
                    timestamp BIGINT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_email_attempts ON email_attempts (email, timestamp);
            """)
        await conn.commit()

async def close_db():
    global pool
    if pool is not None:
        await pool.close()
        pool = None

@asynccontextmanager
async def get_connection() -> AsyncGenerator[psycopg.AsyncConnection, None]:
    global pool
    if pool is None:
        await init_db()
    assert pool is not None
    async with pool.connection() as conn:
        yield conn
