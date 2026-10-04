"""Centralized logging emitter. All cogs call this to emit logs."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

import discord

from bot.database.database import Database

log = logging.getLogger(__name__)

CATEGORY_KEYS = {
    "moderation": "log_mod",
    "messages": "log_messages",
    "server": "log_server",
    "members": "log_members",
    "security": "log_security",
    "tickets": "log_tickets",
}


class LoggingService:
    def __init__(self, db: Database) -> None:
        self.db = db

    async def _channel(self, guild: discord.Guild, category: str) -> Optional[discord.TextChannel]:
        key = CATEGORY_KEYS.get(category)
        if not key:
            return None
        row = await self.db.fetchone(
            "SELECT value FROM guild_config WHERE guild_id = ? AND key = ?",
            (guild.id, key),
        )
        if not row or not row["value"]:
            return None
        try:
            cid = int(row["value"])
        except ValueError:
            return None
        channel = guild.get_channel(cid)
        return channel if isinstance(channel, discord.TextChannel) else None

    async def emit(
        self,
        guild: discord.Guild,
        category: str,
        *,
        title: str,
        description: Optional[str] = None,
        color: int = 0x5865F2,
        fields: Optional[list[tuple[str, str, bool]]] = None,
    ) -> None:
        channel = await self._channel(guild, category)
        if channel is None:
            return
        embed = discord.Embed(
            title=title,
            description=description,
            color=color,
            timestamp=datetime.now(timezone.utc),
        )
        for name, value, inline in (fields or []):
            embed.add_field(name=name, value=value or "—", inline=inline)
        try:
            await channel.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())
        except discord.HTTPException:
            log.warning("Failed to emit log in %s", channel.id)
