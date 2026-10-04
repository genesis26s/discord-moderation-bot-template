"""The bot itself. Loads cogs, DB, and applies branding."""
from __future__ import annotations

import logging
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from bot.config import Config
from bot.core import errors
from bot.core.embeds import EmbedFactory
from bot.database.database import Database
from bot.database.migrations import run_migrations

log = logging.getLogger(__name__)

INITIAL_COGS = [
    "bot.cogs.panel",
    "bot.cogs.tickets",
    "bot.cogs.welcome",
    "bot.cogs.moderation",
    "bot.cogs.automod",
    "bot.cogs.antispam",
    "bot.cogs.antiraid",
    "bot.cogs.antinuke",
    "bot.cogs.logging",
    "bot.cogs.server_watch",
    "bot.cogs.roles",
    "bot.cogs.utility",
    "bot.cogs.information",
    "bot.cogs.security",
]


def _activity_from_config(config: Config) -> Optional[discord.Activity]:
    text = config.bot_activity
    kind = config.bot_activity_type.lower()
    mapping = {
        "playing": discord.ActivityType.playing,
        "listening": discord.ActivityType.listening,
        "watching": discord.ActivityType.watching,
        "competing": discord.ActivityType.competing,
        "streaming": discord.ActivityType.streaming,
    }
    if kind == "streaming":
        return discord.Streaming(name=text, url="https://twitch.tv/securitybot")
    if kind in mapping:
        return discord.Activity(type=mapping[kind], name=text)
    return discord.Activity(type=discord.ActivityType.watching, name=text)


class SecurityBot(commands.Bot):
    def __init__(self, config: Config) -> None:
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        intents.guilds = True
        intents.moderation = True
        intents.guild_messages = True
        intents.guild_reactions = False

        super().__init__(
            command_prefix=commands.when_mentioned,
            intents=intents,
            help_command=None,
            allowed_mentions=discord.AllowedMentions(everyone=False, roles=False, users=True),
        )
        self.config = config
        self.db = Database(config.database_path)
        self.embeds = EmbedFactory(config)

    # ---- Lifecycle ----
    async def setup_hook(self) -> None:
        await self.db.connect()
        await run_migrations(self.db)

        for ext in INITIAL_COGS:
            try:
                await self.load_extension(ext)
                log.info("Loaded extension: %s", ext)
            except Exception as exc:
                log.exception("Failed to load %s: %s", ext, exc)

        # Sync commands globally. Guild sync is faster during dev.
        try:
            synced = await self.tree.sync()
            log.info("Synced %d slash commands.", len(synced))
        except Exception:
            log.exception("Failed to sync commands")

    async def on_ready(self) -> None:
        await self._apply_presence()
        try:
            await self.user.edit(username=self.config.bot_name)  # type: ignore[union-attr]
        except discord.HTTPException:
            # Rate limited / name change unavailable — ignore.
            pass
        log.info("Logged in as %s (%s)", self.user, self.user.id if self.user else "?")  # type: ignore[union-attr]
        log.info("Ready — serving %d guild(s).", len(self.guilds))

    async def _apply_presence(self) -> None:
        status_map = {
            "online": discord.Status.online,
            "idle": discord.Status.idle,
            "dnd": discord.Status.dnd,
            "invisible": discord.Status.invisible,
        }
        status = status_map.get(self.config.bot_status, discord.Status.online)
        activity = _activity_from_config(self.config)
        await self.change_presence(status=status, activity=activity)

    async def close(self) -> None:
        await self.db.close()
        await super().close()

    async def on_app_command_completion(self, interaction: discord.Interaction, command: app_commands.Command) -> None:
        log.debug("Command %s used by %s in %s", command.qualified_name, interaction.user, interaction.guild_id)

    async def on_error(self, event_method: str, /, *args, **kwargs) -> None:
        log.exception("Unhandled error in event %s", event_method)
