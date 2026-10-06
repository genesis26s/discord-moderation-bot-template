"""The bot itself. Loads cogs, DB, and applies branding."""
from __future__ import annotations

import logging
import os
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from bot.config import Config
from bot.core import errors
from bot.core.embeds import EmbedFactory
from bot.database.database import Database
from bot.database.migrations import run_migrations
from bot.verification.db import ensure_schema

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
    "bot.cogs.verification",
    "bot.cogs.owner",
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

        super().__init__(
            command_prefix=commands.when_mentioned,
            intents=intents,
            help_command=None,
            allowed_mentions=discord.AllowedMentions(everyone=False, roles=False, users=True),
        )
        self.config = config
        self.db = Database(config.database_path)
        self.embeds = EmbedFactory(config)

    async def setup_hook(self) -> None:
        # ---- Database + migrations ----
        await self.db.connect()
        await run_migrations(self.db)

        # ---- Verification subsystem schema (idempotent) ----
        try:
            await ensure_schema(self.db)
        except Exception:
            log.exception("Failed to initialise verification schema")

        # ---- Load cogs ----
        for ext in INITIAL_COGS:
            try:
                await self.load_extension(ext)
                log.info("Loaded extension: %s", ext)
            except Exception as exc:
                log.exception("Failed to load %s: %s", ext, exc)

        # ---- Sync slash commands ----
        dev_guild = os.getenv("DEV_GUILD_ID", "").strip()
        try:
            if dev_guild.isdigit():
                guild_obj = discord.Object(id=int(dev_guild))
                self.tree.copy_global_to(guild=guild_obj)
                synced = await self.tree.sync(guild=guild_obj)
                log.info(
                    "Synced %d slash commands to DEV guild %s (instant).",
                    len(synced), dev_guild,
                )
            else:
                synced = await self.tree.sync()
                log.info(
                    "Synced %d slash commands globally (may take up to 1h to appear).",
                    len(synced),
                )
        except Exception:
            log.exception("Failed to sync commands")

        # ---- Global error handler ----
        self.tree.on_error = errors.on_app_command_error

    async def on_ready(self) -> None:
        await self._apply_presence()
        try:
            await self.user.edit(username=self.config.bot_name)
        except discord.HTTPException:
            pass
        log.info("Logged in as %s (%s)", self.user, getattr(self.user, "id", "?"))
        log.info("Ready - serving %d guild(s).", len(self.guilds))

    async def _apply_presence(self) -> None:
        status_map = {
            "online": discord.Status.online,
            "idle": discord.Status.idle,
            "dnd": discord.Status.dnd,
            "invisible": discord.Status.invisible,
        }
        status = status_map.get(self.config.bot_status, discord.Status.online)
        await self.change_presence(status=status, activity=_activity_from_config(self.config))

    async def close(self) -> None:
        # Close verification providers cleanly if the cog wired any
        try:
            cog = self.get_cog("Verification")
            if cog is not None:
                svc = getattr(cog, "service", None)
                if svc is not None:
                    roblox = getattr(svc, "roblox_provider", None)
                    if roblox is not None and hasattr(roblox, "close"):
                        try:
                            await roblox.close()
                        except Exception:
                            pass
        except Exception:
            pass

        await self.db.close()
        await super().close()

    async def on_app_command_completion(
        self, interaction: discord.Interaction, command: app_commands.Command,
    ) -> None:
        log.debug(
            "Command %s used by %s in %s",
            command.qualified_name, interaction.user, interaction.guild_id,
        )

    async def on_error(self, event_method: str, /, *args, **kwargs) -> None:
        log.exception("Unhandled error in event %s", event_method)
