"""Logging cog — emits events, and configures log channels."""
from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from bot.core.checks import is_guild_admin
from bot.services.config_service import ConfigService
from bot.services.logging_service import LoggingService


class Logging(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.config = ConfigService(bot.db)  # type: ignore[attr-defined]
        self.service = LoggingService(bot.db)  # type: ignore[attr-defined]

    # ---- Message events ----
    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message) -> None:
        if not message.guild or message.author.bot:
            return
        await self.service.emit(
            message.guild, "messages", title="Message Deleted", color=0xED4245,
            fields=[("Author", f"{message.author.mention}", True), ("Channel", message.channel.mention, True),
                    ("Content", (message.content or "—")[:1000], False)],
        )

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message) -> None:
        if not after.guild or after.author.bot or before.content == after.content:
            return
        await self.service.emit(
            after.guild, "messages", title="Message Edited", color=0xFEE75C,
            fields=[("Author", f"{after.author.mention}", True), ("Channel", after.channel.mention, True),
                    ("Before", (before.content or "—")[:500], False), ("After", (after.content or "—")[:500], False)],
        )

    # ---- Member events ----
    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        await self.service.emit(
            member.guild, "members", title="Member Joined", color=0x57F287,
            fields=[("User", f"{member.mention} (`{member.id}`)", True),
                    ("Account Created", f"<t:{int(member.created_at.timestamp())}:R>", True)],
        )

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member) -> None:
        await self.service.emit(
            member.guild, "members", title="Member Left", color=0xED4245,
            fields=[("User", f"{member} (`{member.id}`)", True)],
        )

    # ---- Server events ----
    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel: discord.abc.GuildChannel) -> None:
        await self.service.emit(channel.guild, "server", title="Channel Created", color=0x57F287,
                                fields=[("Channel", channel.mention, True), ("Type", str(channel.type), True)])

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel) -> None:
        await self.service.emit(channel.guild, "server", title="Channel Deleted", color=0xED4245,
                                fields=[("Name", channel.name, True)])

    @commands.Cog.listener()
    async def on_guild_role_create(self, role: discord.Role) -> None:
        await self.service.emit(role.guild, "server", title="Role Created", color=0x57F287,
                                fields=[("Role", role.name, True)])

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role: discord.Role) -> None:
        await self.service.emit(role.guild, "server", title="Role Deleted", color=0xED4245,
                                fields=[("Role", role.name, True)])

    # ---- Commands ----
    @app_commands.command(name="logging-config", description="Configure log channels.")
    @app_commands.describe(category="Which category", channel="Channel to log to")
    @app_commands.choices(category=[
        app_commands.Choice(name="moderation", value="log_mod"),
        app_commands.Choice(name="messages", value="log_messages"),
        app_commands.Choice(name="server", value="log_server"),
        app_commands.Choice(name="members", value="log_members"),
        app_commands.Choice(name="security", value="log_security"),
        app_commands.Choice(name="tickets", value="log_tickets"),
    ])
    @is_guild_admin()
    async def logging_config(self, interaction: discord.Interaction, category: app_commands.Choice[str], channel: discord.TextChannel) -> None:
        await self.config.set(interaction.guild_id, category.value, channel.id)  # type: ignore[arg-type]
        await interaction.response.send_message(f"✅ {category.name} logs → {channel.mention}", ephemeral=True)

    @app_commands.command(name="logs", description="Show current logging configuration.")
    @is_guild_admin()
    async def logs(self, interaction: discord.Interaction) -> None:
        gid = interaction.guild_id  # type: ignore[assignment]
        embed = self.bot.embeds.primary(title="Logging Configuration")  # type: ignore[attr-defined]
        for label, key in [("Moderation", "log_mod"), ("Messages", "log_messages"), ("Server", "log_server"),
                           ("Members", "log_members"), ("Security", "log_security"), ("Tickets", "log_tickets")]:
            value = await self.config.get(gid, key)
            channel = interaction.guild.get_channel(int(value)) if value.isdigit() else None  # type: ignore[union-attr]
            embed.add_field(name=label, value=channel.mention if channel else "—", inline=True)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="audit", description="Show the last 10 audit log entries.")
    @is_guild_admin()
    async def audit(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        entries = []
        try:
            async for entry in interaction.guild.audit_logs(limit=10):  # type: ignore[union-attr]
                entries.append(f"**{entry.action.name}** — {entry.user} → `{entry.target}` (<t:{int(entry.created_at.timestamp())}:R>)")
        except discord.Forbidden:
            return await interaction.followup.send("I lack the `View Audit Log` permission.", ephemeral=True)
        await interaction.followup.send("\n".join(entries) or "No entries.", ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Logging(bot))
