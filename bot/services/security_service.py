"""Records security incidents and manages lockdown."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

import discord

from bot.database.database import Database
from bot.services.logging_service import LoggingService


class SecurityService:
    def __init__(self, db: Database, logging: LoggingService) -> None:
        self.db = db
        self.logging = logging

    async def record_incident(
        self,
        guild_id: int,
        *,
        type_: str,
        severity: str,
        executor_id: Optional[int],
        details: str,
    ) -> int:
        await self.db.execute(
            """
            INSERT INTO incidents (guild_id, type, severity, executor_id, details, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (guild_id, type_, severity, executor_id, details, int(datetime.now(timezone.utc).timestamp())),
        )
        row = await self.db.fetchone("SELECT last_insert_rowid() AS id")
        return int(row["id"]) if row else 0

    async def recent_incidents(self, guild_id: int, limit: int = 10):
        return await self.db.fetchall(
            "SELECT * FROM incidents WHERE guild_id = ? ORDER BY created_at DESC LIMIT ?",
            (guild_id, limit),
        )

    async def record_watch_event(
        self,
        guild_id: int,
        *,
        event_type: str,
        severity: str,
        executor_id: Optional[int],
        details: str,
    ) -> None:
        await self.db.execute(
            """
            INSERT INTO watch_events (guild_id, event_type, severity, executor_id, details, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (guild_id, event_type, severity, executor_id, details, int(datetime.now(timezone.utc).timestamp())),
        )

    # ---- Lockdown ----
    async def lock_channels(self, guild: discord.Guild, reason: str) -> int:
        locked = 0
        for channel in guild.text_channels:
            overwrite = channel.overwrites_for(guild.default_role)
            if overwrite.send_messages is False:
                continue
            try:
                overwrite.send_messages = False
                await channel.set_permissions(guild.default_role, overwrite=overwrite, reason=reason)
                locked += 1
            except discord.HTTPException:
                continue
        return locked

    async def unlock_channels(self, guild: discord.Guild, reason: str) -> int:
        unlocked = 0
        for channel in guild.text_channels:
            overwrite = channel.overwrites_for(guild.default_role)
            if overwrite.send_messages is False:
                try:
                    overwrite.send_messages = None
                    await channel.set_permissions(guild.default_role, overwrite=overwrite, reason=reason)
                    unlocked += 1
                except discord.HTTPException:
                    continue
        return unlocked
