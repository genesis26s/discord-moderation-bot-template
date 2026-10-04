"""Server Watch — continuous monitoring + threat log."""
from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from bot.core.checks import is_guild_admin
from bot.services.config_service import ConfigService
from bot.services.security_service import SecurityService
from bot.services.logging_service import LoggingService


class ServerWatch(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.config = ConfigService(bot.db)  # type: ignore[attr-defined]
        self.security = SecurityService(bot.db, LoggingService(bot.db))  # type: ignore[attr-defined]

    async def _watch_channel(self, guild: discord.Guild):
        raw = await self.config.get(guild.id, "serverwatch_channel")
        if not raw or not raw.isdigit():
            return None
        return guild.get_channel(int(raw))

    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel: discord.abc.GuildChannel) -> None:
        if not await self.config.get_bool(channel.guild.id, "serverwatch_enabled"):
            return
        await self.security.record_watch_event(
            channel.guild.id, event_type="channel_create", severity="LOW",
            executor_id=None, details=f"Channel created: {channel.name}",
        )

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel) -> None:
        if not await self.config.get_bool(channel.guild.id, "serverwatch_enabled"):
            return
        await self.security.record_watch_event(
            channel.guild.id, event_type="channel_delete", severity="MEDIUM",
            executor_id=None, details=f"Channel deleted: {channel.name}",
        )
        ch = await self._watch_channel(channel.guild)
        if ch:
            try:
                await ch.send(f"⚠️ **Server Watch** — channel deleted: `{channel.name}`")
            except discord.HTTPException:
                pass

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role: discord.Role) -> None:
        if not await self.config.get_bool(role.guild.id, "serverwatch_enabled"):
            return
        await self.security.record_watch_event(
            role.guild.id, event_type="role_delete", severity="MEDIUM",
            executor_id=None, details=f"Role deleted: {role.name}",
        )

    # ---- Commands ----
    @app_commands.command(name="serverwatch", description="Show Server Watch status.")
    @is_guild_admin()
    async def serverwatch(self, interaction: discord.Interaction) -> None:
        gid = interaction.guild_id  # type: ignore[assignment]
        enabled = await self.config.get_bool(gid, "serverwatch_enabled")
        embed = self.bot.embeds.primary(title="Server Watch")  # type: ignore[attr-defined]
        embed.add_field(name="Status", value="🟢 Enabled" if enabled else "🔴 Disabled", inline=True)
        chan = await self._watch_channel(interaction.guild)  # type: ignore[arg-type]
        embed.add_field(name="Alert Channel", value=chan.mention if chan else "—", inline=True)
        recent = await self.security.recent_incidents(gid, limit=5)
        embed.add_field(name="Recent Incidents", value=f"`{len(recent)}`", inline=True)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="serverwatch-config", description="Configure Server Watch.")
    @is_guild_admin()
    async def serverwatch_config(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_message(
            "Open `/panel` → **Server Watch** to configure interactively.",
            ephemeral=True,
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ServerWatch(bot))
