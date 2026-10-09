"""Ticket lifecycle service."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

import discord

from bot.database.database import Database
from bot.services.logging_service import LoggingService


class TicketService:
    def __init__(self, db: Database, logging_svc: LoggingService) -> None:
        self.db = db
        self.logging = logging_svc

    async def create_ticket_record(
        self,
        guild_id: int,
        channel_id: int,
        category_id: Optional[int],
        user_id: int,
    ) -> int:
        await self.db.execute(
            """
            INSERT INTO tickets (guild_id, channel_id, category_id, user_id, status, created_at)
            VALUES (?, ?, ?, ?, 'open', ?)
            """,
            (guild_id, channel_id, category_id, user_id,
             int(datetime.now(timezone.utc).timestamp())),
        )
        row = await self.db.fetchone("SELECT last_insert_rowid() AS id")
        return int(row["id"]) if row else 0

    async def get_ticket_by_channel(self, channel_id: int):
        return await self.db.fetchone("SELECT * FROM tickets WHERE channel_id = ?", (channel_id,))

    async def set_claimed(self, channel_id: int, staff_id: int) -> None:
        await self.db.execute(
            "UPDATE tickets SET claimed_by = ? WHERE channel_id = ?",
            (staff_id, channel_id),
        )

    async def set_status(self, channel_id: int, status: str) -> None:
        closed_at = int(datetime.now(timezone.utc).timestamp()) if status == "closed" else None
        await self.db.execute(
            "UPDATE tickets SET status = ?, closed_at = ? WHERE channel_id = ?",
            (status, closed_at, channel_id),
        )

    async def delete_ticket(self, channel_id: int) -> None:
        await self.db.execute("DELETE FROM tickets WHERE channel_id = ?", (channel_id,))

    async def count_open(self, guild_id: int, user_id: int, guild=None) -> int:
        """Count open tickets for a user.

        If `guild` is provided, orphaned records (whose channels no longer exist)
        are auto-closed so they never block the user from opening a new ticket.
        """
        rows = await self.db.fetchall(
            "SELECT channel_id FROM tickets WHERE guild_id = ? AND user_id = ? AND status = 'open'",
            (guild_id, user_id),
        )
        if not rows:
            return 0
        if guild is None:
            return len(rows)

        live = 0
        orphans: list[int] = []
        for r in rows:
            try:
                cid = int(r["channel_id"])
            except (TypeError, ValueError):
                continue
            if guild.get_channel(cid) is None:
                orphans.append(cid)
            else:
                live += 1

        # Auto-close orphaned records
        now_ts = int(datetime.now(timezone.utc).timestamp())
        for cid in orphans:
            try:
                await self.db.execute(
                    "UPDATE tickets SET status = 'closed', closed_at = ? "
                    "WHERE channel_id = ? AND status = 'open'",
                    (now_ts, cid),
                )
            except Exception:
                pass

        return live

    async def list_panels(self, guild_id: int):
        return await self.db.fetchall(
            "SELECT * FROM ticket_panels WHERE guild_id = ?",
            (guild_id,),
        )
