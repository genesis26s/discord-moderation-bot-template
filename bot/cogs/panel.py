"""The /panel command — central configuration entry point."""
from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from bot.core.checks import is_guild_admin
from bot.services.config_service import ConfigService
from bot.services.security_service import SecurityService
from bot.views.panel import PanelHomeView, build_home_embed


class Panel(commands.Cog):
    """Central configuration panel."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.config = ConfigService(bot.db)  # type: ignore[attr-defined]
        self.security = SecurityService(bot.db, None)  # type: ignore[arg-type,attr-defined]

    @app_commands.command(name="panel", description="Open the central configuration panel.")
    @is_guild_admin()
    async def panel(self, interaction: discord.Interaction) -> None:
        assert interaction.guild is not None
        gid = interaction.guild.id

        statuses = {
            "antinuke": await self.config.get_bool(gid, "antinuke_enabled"),
            "antiraid": await self.config.get_bool(gid, "antiraid_enabled"),
            "antispam": await self.config.get_bool(gid, "antispam_enabled"),
            "automod": await self.config.get_bool(gid, "automod_enabled"),
            "serverwatch": await self.config.get_bool(gid, "serverwatch_enabled"),
            "welcome": await self.config.get_bool(gid, "welcome_enabled"),
            "tickets": await self.config.get_bool(gid, "tickets_enabled"),
            "lockdown": await self.config.get_bool(gid, "lockdown_active"),
        }

        incidents = await self.security.recent_incidents(gid, limit=5)
        embed = build_home_embed(self.bot.config.bot_name, statuses, len(incidents))  # type: ignore[attr-defined]
        view = PanelHomeView(author_id=interaction.user.id, config=self.config, security=self.security)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Panel(bot))
