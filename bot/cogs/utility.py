"""Utility commands."""
from __future__ import annotations

import platform
import time

import discord
from discord import app_commands
from discord.ext import commands

from bot.core.paginator import Paginator
from bot.core.utilities import chunk, humanize_timedelta


class Utility(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self._start = time.monotonic()

    @app_commands.command(name="ping", description="Check bot latency.")
    async def ping(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_message(f"🏓 Pong! `{round(self.bot.latency * 1000)}ms`")

    @app_commands.command(name="uptime", description="Show bot uptime.")
    async def uptime(self, interaction: discord.Interaction) -> None:
        import datetime as _dt
        delta = _dt.timedelta(seconds=int(time.monotonic() - self._start))
        await interaction.response.send_message(f"⏱ Uptime: `{humanize_timedelta(delta)}`")

    @app_commands.command(name="botinfo", description="Show bot information.")
    async def botinfo(self, interaction: discord.Interaction) -> None:
        embed = self.bot.embeds.primary(title=self.bot.config.bot_name, description=self.bot.config.bot_description)  # type: ignore[attr-defined]
        embed.add_field(name="Guilds", value=str(len(self.bot.guilds)), inline=True)
        embed.add_field(name="Users", value=str(sum(g.member_count or 0 for g in self.bot.guilds)), inline=True)
        embed.add_field(name="Python", value=platform.python_version(), inline=True)
        embed.add_field(name="discord.py", value=discord.__version__, inline=True)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="invite", description="Get the bot invite URL.")
    async def invite(self, interaction: discord.Interaction) -> None:
        url = discord.utils.oauth_url(self.bot.user.id, permissions=discord.Permissions(administrator=True))  # type: ignore[union-attr]
        await interaction.response.send_message(f"🔗 [Invite the bot]({url})", ephemeral=True)

    @app_commands.command(name="avatar", description="Show a user's avatar.")
    async def avatar(self, interaction: discord.Interaction, member: discord.Member | None = None) -> None:
        member = member or interaction.user  # type: ignore[assignment]
        embed = self.bot.embeds.primary(title=f"{member}'s avatar")  # type: ignore[attr-defined]
        embed.set_image(url=member.display_avatar.url)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="userinfo", description="Show info about a member.")
    async def userinfo(self, interaction: discord.Interaction, member: discord.Member | None = None) -> None:
        member = member or interaction.user  # type: ignore[assignment]
        embed = self.bot.embeds.primary(title=str(member))  # type: ignore[attr-defined]
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(name="ID", value=str(member.id), inline=True)
        embed.add_field(name="Joined", value=f"<t:{int(member.joined_at.timestamp())}:R>" if member.joined_at else "—", inline=True)
        embed.add_field(name="Created", value=f"<t:{int(member.created_at.timestamp())}:R>", inline=True)
        embed.add_field(name="Top Role", value=member.top_role.mention, inline=True)
        embed.add_field(name="Roles", value=f"`{len(member.roles) - 1}`", inline=True)
        embed.add_field(name="Bot", value=str(member.bot), inline=True)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="servericon", description="Show the server icon.")
    async def servericon(self, interaction: discord.Interaction) -> None:
        if not interaction.guild or not interaction.guild.icon:
            return await interaction.response.send_message("No icon.", ephemeral=True)
        embed = self.bot.embeds.primary(title=interaction.guild.name)  # type: ignore[attr-defined]
        embed.set_image(url=interaction.guild.icon.url)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="permissions", description="Show your permissions in this guild.")
    async def permissions(self, interaction: discord.Interaction) -> None:
        if not isinstance(interaction.user, discord.Member):
            return
        perms = [name for name, value in interaction.user.guild_permissions if value]
        chunks = chunk(perms, 10)
        pages = []
        for i, ch in enumerate(chunks, start=1):
            embed = self.bot.embeds.primary(title=f"Your permissions ({i}/{len(chunks)})", description="\n".join(f"• {p}" for p in ch))  # type: ignore[attr-defined]
            pages.append(embed)
        if len(pages) == 1:
            await interaction.response.send_message(embed=pages[0], ephemeral=True)
        else:
            await interaction.response.send_message(embed=pages[0], view=Paginator(pages, author_id=interaction.user.id), ephemeral=True)

    @app_commands.command(name="roleinfo", description="Show info about a role.")
    async def roleinfo(self, interaction: discord.Interaction, role: discord.Role) -> None:
        embed = self.bot.embeds.primary(title=role.name)  # type: ignore[attr-defined]
        embed.add_field(name="ID", value=str(role.id), inline=True)
        embed.add_field(name="Members", value=str(len(role.members)), inline=True)
        embed.add_field(name="Color", value=str(role.color), inline=True)
        embed.add_field(name="Hoisted", value=str(role.hoist), inline=True)
        embed.add_field(name="Mentionable", value=str(role.mentionable), inline=True)
        embed.add_field(name="Position", value=str(role.position), inline=True)
        await interaction.response.send_message(embed=embed)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Utility(bot))
