"""Moderation action helpers with logging."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

import discord

from bot.database.database import Database
from bot.services.logging_service import LoggingService


class ModerationService:
    def __init__(self, db: Database, logging: LoggingService) -> None:
        self.db = db
        self.logging = logging

    async def record_action(
        self,
        guild_id: int,
        user_id: int,
        moderator_id: int,
        action: str,
        reason: Optional[str] = None,
        duration: Optional[int] = None,
    ) -> None:
        await self.db.execute(
            """
            INSERT INTO mod_actions (guild_id, user_id, moderator_id, action, reason, duration, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (guild_id, user_id, moderator_id, action, reason, duration, int(datetime.now(timezone.utc).timestamp())),
        )

    async def log_case(
        self,
        guild: discord.Guild,
        *,
        action: str,
        user: discord.abc.User,
        moderator: discord.Member,
        reason: Optional[str],
        color: int,
        extra_fields: Optional[list[tuple[str, str, bool]]] = None,
    ) -> None:
        fields = [
            ("User", f"{user.mention} (`{user.id}`)", True),
            ("Moderator", f"{moderator.mention} (`{moderator.id}`)", True),
            ("Reason", reason or "No reason provided.", False),
        ]
        if extra_fields:
            fields.extend(extra_fields)
        await self.logging.emit(
            guild,
            "moderation",
            title=f"Moderation · {action}",
            color=color,
            fields=fields,
        )

    async def add_warning(self, guild_id: int, user_id: int, moderator_id: int, reason: str) -> int:
        await self.db.execute(
            "INSERT INTO warnings (guild_id, user_id, moderator_id, reason, created_at) VALUES (?, ?, ?, ?, ?)",
            (guild_id, user_id, moderator_id, reason, int(datetime.now(timezone.utc).timestamp())),
        )
        row = await self.db.fetchone("SELECT last_insert_rowid() AS id")
        return int(row["id"]) if row else 0

    async def list_warnings(self, guild_id: int, user_id: int) -> list:
        return await self.db.fetchall(
            "SELECT * FROM warnings WHERE guild_id = ? AND user_id = ? ORDER BY created_at DESC",
            (guild_id, user_id),
        )

    async def delete_warning(self, guild_id: int, warning_id: int) -> int:
        return await self.db.execute(
            "DELETE FROM warnings WHERE guild_id = ? AND id = ?",
            (guild_id, warning_id),
        )
