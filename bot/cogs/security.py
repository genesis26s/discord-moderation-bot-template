"""Security overview + lockdown commands."""
from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from bot.core.checks import is_guild_admin
from bot.services.config_service import ConfigService
from bot.services.logging_service import LoggingService
from bot.services.security_service import SecurityService
from bot.views.common import ConfirmView


class Security(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.config = ConfigService(bot.db)  # type: ignore[attr-defined]
        self.service = SecurityService(bot.db, LoggingService(bot.db))  # type: ignore[attr-defined]

    @app_commands.command(name="security", description="Show the security dashboard.")
    @is_guild_admin()
    async def security(self, interaction: discord.Interaction) -> None:
        gid = interaction.guild_id  # type: ignore[assignment]
        embed = self.bot.embeds.primary(title="🛡️ Security Dashboard")  # type: ignore[attr-defined]

        def state(b: bool) -> str:
            return "🟢 Enabled" if b else "🔴 Disabled"

        embed.add_field(name="Anti-Nuke", value=state(await self.config.get_bool(gid, "antinuke_enabled")), inline=True)
        embed.add_field(name="Anti-Raid", value=state(await self.config.get_bool(gid, "antiraid_enabled")), inline=True)
        embed.add_field(name="Anti-Spam", value=state(await self.config.get_bool(gid, "antispam_enabled")), inline=True)
        embed.add_field(name="AutoMod", value=state(await self.config.get_bool(gid, "automod_enabled")), inline=True)
        embed.add_field(name="Server Watch", value=state(await self.config.get_bool(gid, "serverwatch_enabled")), inline=True)
        embed.add_field(name="Lockdown", value=state(await self.config.get_bool(gid, "lockdown_active")), inline=True)

        incidents = await self.service.recent_incidents(gid, limit=5)
        embed.add_field(name="Recent Threats", value=f"`{len(incidents)}`", inline=True)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="security-config", description="Open the security configuration panel.")
    @is_guild_admin()
    async def security_config(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_message(
            "Open `/panel` → **Security Overview** to configure interactively.",
            ephemeral=True,
        )

    @app_commands.command(name="lockdown", description="Activate emergency lockdown (locks all channels).")
    @is_guild_admin()
    async def lockdown(self, interaction: discord.Interaction) -> None:
        view = ConfirmView(author_id=interaction.user.id, confirm_label="Lock server")
        await interaction.response.send_message("⚠ This will lock **every text channel**. Confirm?", view=view, ephemeral=True)
        await view.wait()
        if not view.result:
            return
        locked = await self.service.lock_channels(interaction.guild, reason=f"Lockdown by {interaction.user}")  # type: ignore[arg-type]
        await self.config.set(interaction.guild_id, "lockdown_active", "true")  # type: ignore[arg-type]
        await interaction.followup.send(f"🔒 Locked `{locked}` channels.", ephemeral=True)

    @app_commands.command(name="unlockdown", description="Lift the emergency lockdown.")
    @is_guild_admin()
    async def unlockdown(self, interaction: discord.Interaction) -> None:
        unlocked = await self.service.unlock_channels(interaction.guild, reason=f"Unlockdown by {interaction.user}")  # type: ignore[arg-type]
        await self.config.set(interaction.guild_id, "lockdown_active", "false")  # type: ignore[arg-type]
        await interaction.response.send_message(f"🔓 Unlocked `{unlocked}` channels.", ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Security(bot))
