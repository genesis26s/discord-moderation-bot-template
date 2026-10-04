"""Global error handling."""
from __future__ import annotations

import logging
import traceback

import discord
from discord import app_commands

log = logging.getLogger(__name__)


class SecurityBotError(Exception):
    """Base error for bot-specific failures."""


class ConfigError(SecurityBotError):
    pass


class NotConfiguredError(SecurityBotError):
    pass


async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError) -> None:
    try:
        from bot.core.embeds import EmbedFactory
        factory: EmbedFactory = interaction.client.embeds  # type: ignore[attr-defined]
    except Exception:
        factory = None

    if isinstance(error, app_commands.CommandOnCooldown):
        msg = f"Slow down — try again in `{error.retry_after:.1f}s`."
    elif isinstance(error, app_commands.CheckFailure):
        msg = str(error) or "You do not have permission to use this."
    elif isinstance(error, app_commands.MissingPermissions):
        perms = ", ".join(error.missing_permissions)
        msg = f"You are missing permissions: `{perms}`"
    elif isinstance(error, app_commands.BotMissingPermissions):
        perms = ", ".join(error.missing_permissions)
        msg = f"I am missing permissions: `{perms}`"
    elif isinstance(error, NotConfiguredError):
        msg = str(error)
    else:
        msg = "An unexpected error occurred. The issue has been logged."
        log.error("Command error in %s:\n%s", getattr(interaction.command, "name", "?"), "".join(traceback.format_exception(type(error), error, error.__traceback__)))

    embed = (factory.error(title="Error", description=msg) if factory else discord.Embed(title="Error", description=msg, color=0xED4245))
    try:
        if interaction.response.is_done():
            await interaction.followup.send(embed=embed, ephemeral=True)
        else:
            await interaction.response.send_message(embed=embed, ephemeral=True)
    except discord.HTTPException:
        pass
