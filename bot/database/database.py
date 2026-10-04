"""Async SQLite wrapper using aiosqlite. Centralized and safe."""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Iterable, Optional

import aiosqlite

log = logging.getLogger(__name__)


class Database:
    """Thin async wrapper around aiosqlite with a single shared connection.

    All writes serialize through an asyncio.Lock to prevent interleaving,
    and every query is parameterized to avoid SQL injection.
    """

    def __init__(self, path: str) -> None:
        self.path = path
        self._conn: Optional[aiosqlite.Connection] = None
        self._lock = asyncio.Lock()

    async def connect(self) -> None:
        self._conn = await aiosqlite.connect(self.path)
        self._conn.row_factory = aiosqlite.Row
        await self._conn.execute("PRAGMA journal_mode=WAL;")
        await self._conn.execute("PRAGMA foreign_keys=ON;")
        await self._conn.execute("PRAGMA synchronous=NORMAL;")
        await self._conn.commit()

    async def close(self) -> None:
        if self._conn is not None:
            await self._conn.close()
            self._conn = None

    @property
    def conn(self) -> aiosqlite.Connection:
        if self._conn is None:
            raise RuntimeError("Database is not connected")
        return self._conn

    # ---- Reads ----
    async def fetchone(self, sql: str, params: Iterable[Any] = ()) -> Optional[aiosqlite.Row]:
        async with self._lock:
            cur = await self.conn.execute(sql, tuple(params))
            row = await cur.fetchone()
            await cur.close()
            return row

    async def fetchall(self, sql: str, params: Iterable[Any] = ()) -> list[aiosqlite.Row]:
        async with self._lock:
            cur = await self.conn.execute(sql, tuple(params))
            rows = await cur.fetchall()
            await cur.close()
            return list(rows)

    # ---- Writes ----
    async def execute(self, sql: str, params: Iterable[Any] = ()) -> int:
        async with self._lock:
            cur = await self.conn.execute(sql, tuple(params))
            await self.conn.commit()
            rowcount = cur.rowcount
            await cur.close()
            return rowcount

    async def executemany(self, sql: str, params_seq: Iterable[Iterable[Any]]) -> None:
        async with self._lock:
            await self.conn.executemany(sql, [tuple(p) for p in params_seq])
            await self.conn.commit()

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[aiosqlite.Connection]:
        async with self._lock:
            try:
                yield self.conn
                await self.conn.commit()
            except Exception:
                await self.conn.rollback()
                raise

    # ---- Convenience helpers ----
    async def get_guild_config(self, guild_id: int, key: str, default: Any = None) -> Any:
        row = await self.fetchone(
            "SELECT value FROM guild_config WHERE guild_id = ? AND key = ?",
            (guild_id, key),
        )
        return row["value"] if row else default

    async def set_guild_config(self, guild_id: int, key: str, value: Any) -> None:
        await self.execute(
            """
            INSERT INTO guild_config (guild_id, key, value)
            VALUES (?, ?, ?)
            ON CONFLICT(guild_id, key) DO UPDATE SET value = excluded.value
            """,
            (guild_id, key, str(value)),
        )

    async def get_guild_settings(self, guild_id: int) -> dict[str, str]:
        rows = await self.fetchall("SELECT key, value FROM guild_config WHERE guild_id = ?", (guild_id,))
        return {r["key"]: r["value"] for r in rows}
