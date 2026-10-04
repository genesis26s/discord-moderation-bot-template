"""Anti-raid system."""
from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone

import discord
from discord import app_commands
from discord.ext import commands

from bot.core.checks import is_guild_admin
from bot.services.config_service import ConfigService
from bot.services.logging_service import LoggingService
from bot.services.raid_service import RaidService
from bot.services.security_service import SecurityService


class AntiRaid(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.config = ConfigService(bot.db)  # type: ignore[attr-defined]
        self.security = SecurityService(bot.db, LoggingService(bot.db))  # type: ignore[attr-defined]
        self.raids = RaidService()
        self._alerted_at: dict[int, float] = {}

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        gid = member.guild.id
        if not await self.config.get_bool(gid, "antiraid_enabled"):
            return

        self.raids.record_join(gid)
        window = await self.config.get_int(gid, "antiraid_window")
        threshold = await self.config.get_int(gid, "antiraid_joins")
        count = self.raids.joins_in_window(gid, window)

        # Alert channel
        alert_channel_id = await self.config.get(gid, "antiraid_alert_channel")
        channel = member.guild.get_channel(int(alert_channel_id)) if alert_channel_id.isdigit() else None

        if count >= threshold:
            now = time.monotonic()
            if now - self._alerted_at.get(gid, 0) < 60:
                return
            self._alerted_at[gid] = now
            await self._trigger(member.guild, channel, count, window)

        # Account age check
        min_days = await self.config.get_int(gid, "antiraid_min_age_days")
        if min_days > 0:
            age = datetime.now(timezone.utc) - member.created_at
            if age < timedelta(days=min_days):
                action = await self.config.get(gid, "antiraid_action")
                if action in ("kick", "ban") and channel:
                    try:
                        await channel.send(f"⚠ Suspicious young account joined: {member.mention} (age `{age.days}d`).")
                    except discord.HTTPException:
                        pass

    async def _trigger(self, guild: discord.Guild, channel, count: int, window: int) -> None:
        action = await self.config.get(guild.id, "antiraid_action")
        details = f"{count} joins within {window}s"

        await self.security.record_incident(
            guild.id,
            type_="antiraid",
            severity="HIGH",
            executor_id=None,
            details=details,
        )

        if action == "lockdown":
            await self.security.lock_channels(guild, reason="Anti-Raid triggered")
            await self.config.set(guild.id, "lockdown_active", "true")

        if channel:
            embed = self.bot.embeds.error(title="🚨 Anti-Raid Triggered", description=details)  # type: ignore[attr-defined]
            embed.add_field(name="Action", value=f"`{action}`", inline=True)
            embed.add_field(name="Guild", value=guild.name, inline=True)
            try:
                await channel.send(embed=embed)
            except discord.HTTPException:
                pass

    @app_commands.command(name="antiraid", description="Show anti-raid status.")
    @is_guild_admin()
    async def antiraid_status(self, interaction: discord.Interaction) -> None:
        gid = interaction.guild_id  # type: ignore[assignment]
        enabled = await self.config.get_bool(gid, "antiraid_enabled")
        embed = self.bot.embeds.primary(title="Anti-Raid")  # type: ignore[attr-defined]
        embed.add_field(name="Status", value="🟢 Enabled" if enabled else "🔴 Disabled", inline=True)
        embed.add_field(name="Threshold", value=f"`{await self.config.get_int(gid, 'antiraid_joins')}` joins / `{await self.config.get_int(gid, 'antiraid_window')}s`", inline=True)
        embed.add_field(name="Action", value=f"`{await self.config.get(gid, 'antiraid_action')}`", inline=True)
        embed.add_field(name="Min account age", value=f"`{await self.config.get_int(gid, 'antiraid_min_age_days')}` days", inline=True)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="antiraid-config", description="Configure anti-raid interactively.")
    @is_guild_admin()
    async def antiraid_config(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_message(
            "Open `/panel` → **Anti-Raid** to configure interactively.",
            ephemeral=True,
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(AntiRaid(bot))
