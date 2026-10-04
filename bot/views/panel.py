"""Main configuration panel view — dropdowns to configure the entire bot."""
from __future__ import annotations

from typing import Awaitable, Callable, Optional

import discord

from bot.core.checks import get_guild_admin_roles
from bot.services.config_service import ConfigService
from bot.services.security_service import SecurityService


CATEGORIES = [
    ("security", "Security Overview", "Comprehensive security status"),
    ("moderation", "Moderation", "Moderation settings"),
    ("tickets", "Tickets", "Ticket system"),
    ("welcome", "Welcome & Goodbye", "Join/leave messages"),
    ("logging", "Logging", "Log channels"),
    ("antispam", "Anti-Spam", "Message spam protection"),
    ("antiraid", "Anti-Raid", "Mass join protection"),
    ("antinuke", "Anti-Nuke", "Destructive action protection"),
    ("serverwatch", "Server Watch", "Continuous monitoring"),
    ("automod", "AutoMod", "Word / link filtering"),
    ("roles", "Roles", "Role management & staff roles"),
    ("bot", "Bot Settings", "Identity & presence"),
]


def _status_line(enabled: bool) -> str:
    return "🟢 Enabled" if enabled else "🔴 Disabled"


class PanelHomeView(discord.ui.View):
    def __init__(self, *, author_id: int, config: ConfigService, security: SecurityService) -> None:
        super().__init__(timeout=300)
        self.author_id = author_id
        self.config = config
        self.security = security
        options = [discord.SelectOption(label=label, value=key, description=desc) for key, label, desc in CATEGORIES]
        select = discord.ui.Select(placeholder="Select a category to configure…", options=options, custom_id="panel:cat")
        select.callback = self._on_select  # type: ignore[assignment]
        self.add_item(select)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("This panel is not for you.", ephemeral=True)
            return False
        return True

    async def _on_select(self, interaction: discord.Interaction) -> None:
        value = interaction.data["values"][0]  # type: ignore[index]
        await interaction.response.send_message(
            f"Selected **{value}**. Opening category editor…",
            ephemeral=True,
        )


def build_home_embed(bot_name: str, statuses: dict[str, bool], incident_count: int) -> discord.Embed:
    embed = discord.Embed(
        title=f"🛡️ {bot_name} — Control Center",
        description=(
            "Welcome to the central configuration panel.\n"
            "Use the dropdown below to configure any system."
        ),
        color=0x5865F2,
    )
    embed.add_field(
        name="Security Systems",
        value=(
            f"Anti-Nuke: {_status_line(statuses['antinuke'])}\n"
            f"Anti-Raid: {_status_line(statuses['antiraid'])}\n"
            f"Anti-Spam: {_status_line(statuses['antispam'])}\n"
            f"AutoMod: {_status_line(statuses['automod'])}\n"
            f"Server Watch: {_status_line(statuses['serverwatch'])}"
        ),
        inline=False,
    )
    embed.add_field(
        name="Community",
        value=(
            f"Welcome: {_status_line(statuses['welcome'])}\n"
            f"Tickets: {_status_line(statuses['tickets'])}\n"
            f"Lockdown Active: {_status_line(statuses['lockdown'])}"
        ),
        inline=False,
    )
    embed.add_field(name="Recent Threats", value=f"`{incident_count}`", inline=True)
    embed.add_field(name="Security Level", value="`HIGH`", inline=True)
    return embed
