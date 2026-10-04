"""Guild configuration helpers. Every setting goes through here."""
from __future__ import annotations

from typing import Any, Optional

import discord

from bot.database.database import Database

DEFAULTS: dict[str, Any] = {
    # Welcome
    "welcome_enabled": "false",
    "welcome_channel": "",
    "welcome_message": "Welcome {user} to **{server}**! You are member #{member_count}.",
    "welcome_embed": "true",
    "goodbye_enabled": "false",
    "goodbye_channel": "",
    "goodbye_message": "Goodbye {username}.",
    # Logging
    "log_mod": "",
    "log_messages": "",
    "log_server": "",
    "log_members": "",
    "log_security": "",
    "log_tickets": "",
    # Anti-spam
    "antispam_enabled": "false",
    "antispam_msgs": "5",
    "antispam_window": "5",
    "antispam_dupes": "3",
    "antispam_mentions": "6",
    "antispam_action": "timeout",
    "antispam_timeout": "300",
    # Anti-raid
    "antiraid_enabled": "false",
    "antiraid_joins": "10",
    "antiraid_window": "15",
    "antiraid_min_age_days": "7",
    "antiraid_action": "lockdown",
    "antiraid_alert_channel": "",
    # Anti-nuke
    "antinuke_enabled": "false",
    "antinuke_channel_delete": "3",
    "antinuke_role_delete": "3",
    "antinuke_ban_count": "5",
    "antinuke_kick_count": "5",
    "antinuke_webhook": "3",
    "antinuke_action": "ban",
    "antinuke_alert_channel": "",
    # AutoMod
    "automod_enabled": "false",
    "automod_invites": "true",
    "automod_links": "false",
    "automod_caps": "70",
    "automod_repeat": "8",
    "automod_action": "delete",
    # Server watch
    "serverwatch_enabled": "false",
    "serverwatch_channel": "",
    # Moderation
    "mod_dm_users": "true",
    "mod_default_timeout": "600",
    # Tickets
    "tickets_enabled": "false",
    "tickets_transcripts_channel": "",
    "tickets_ratings_enabled": "false",
    # Lockdown state
    "lockdown_active": "false",
}


class ConfigService:
    def __init__(self, db: Database) -> None:
        self.db = db

    async def get(self, guild_id: int, key: str) -> str:
        row = await self.db.fetchone(
            "SELECT value FROM guild_config WHERE guild_id = ? AND key = ?",
            (guild_id, key),
        )
        if row is not None:
            return row["value"]
        return str(DEFAULTS.get(key, ""))

    async def get_bool(self, guild_id: int, key: str) -> bool:
        return (await self.get(guild_id, key)).lower() == "true"

    async def get_int(self, guild_id: int, key: str) -> int:
        try:
            return int(await self.get(guild_id, key))
        except (TypeError, ValueError):
            return int(DEFAULTS.get(key, 0))

    async def set(self, guild_id: int, key: str, value: Any) -> None:
        await self.db.set_guild_config(guild_id, key, str(value))

    async def all(self, guild_id: int) -> dict[str, str]:
        stored = await self.db.get_guild_settings(guild_id)
        merged = dict(DEFAULTS)
        merged.update(stored)
        return merged

    # ---- Channel resolution helpers ----
    async def resolve_channel(self, guild: discord.Guild, key: str) -> Optional[discord.abc.GuildChannel]:
        raw = await self.get(guild.id, key)
        if not raw:
            return None
        try:
            cid = int(raw)
        except ValueError:
            return None
        return guild.get_channel(cid)

    async def resolve_role(self, guild: discord.Guild, key: str) -> Optional[discord.Role]:
        raw = await self.get(guild.id, key)
        if not raw:
            return None
        try:
            rid = int(raw)
        except ValueError:
            return None
        return guild.get_role(rid)
