"""Welcome / goodbye system with placeholder rendering."""
from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from bot.core.checks import is_guild_admin
from bot.services.config_service import ConfigService


def render_placeholders(template: str, member: discord.Member) -> str:
    return (
        template.replace("{user}", member.mention)
        .replace("{username}", member.name)
        .replace("{display_name}", member.display_name)
        .replace("{server}", member.guild.name)
        .replace("{member_count}", str(member.guild.member_count))
        .replace("{user_id}", str(member.id))
        .replace("{guild_id}", str(member.guild.id))
    )


class Welcome(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.config = ConfigService(bot.db)  # type: ignore[attr-defined]

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        gid = member.guild.id
        if await self.config.get_bool(gid, "welcome_enabled"):
            channel = await self.config.resolve_channel(member.guild, "welcome_channel")
            if isinstance(channel, discord.TextChannel):
                raw = await self.config.get(gid, "welcome_message")
                text = render_placeholders(raw, member)
                if await self.config.get_bool(gid, "welcome_embed"):
                    embed = self.bot.embeds.success(title=f"Welcome to {member.guild.name}!", description=text)  # type: ignore[attr-defined]
                    embed.set_thumbnail(url=member.display_avatar.url)
                    try:
                        await channel.send(content=member.mention, embed=embed)
                    except discord.HTTPException:
                        pass
                else:
                    try:
                        await channel.send(text)
                    except discord.HTTPException:
                        pass

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member) -> None:
        gid = member.guild.id
        if await self.config.get_bool(gid, "goodbye_enabled"):
            channel = await self.config.resolve_channel(member.guild, "goodbye_channel")
            if isinstance(channel, discord.TextChannel):
                raw = await self.config.get(gid, "goodbye_message")
                text = render_placeholders(raw, member)
                try:
                    await channel.send(text)
                except discord.HTTPException:
                    pass

    @app_commands.command(name="welcome-config", description="Configure the welcome system.")
    @is_guild_admin()
    async def welcome_config(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_message(
            "Open `/panel` → **Welcome & Goodbye** to configure interactively.\n"
            "Use `/welcome-test` to preview.",
            ephemeral=True,
        )

    @app_commands.command(name="welcome-test", description="Preview the welcome message.")
    @is_guild_admin()
    async def welcome_test(self, interaction: discord.Interaction) -> None:
        member = interaction.user
        if not isinstance(member, discord.Member):
            return
        raw = await self.config.get(interaction.guild_id, "welcome_message")  # type: ignore[arg-type]
        embed = self.bot.embeds.success(title=f"Welcome to {interaction.guild.name}!", description=render_placeholders(raw, member))  # type: ignore[attr-defined]
        embed.set_thumbnail(url=member.display_avatar.url)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="goodbye-test", description="Preview the goodbye message.")
    @is_guild_admin()
    async def goodbye_test(self, interaction: discord.Interaction) -> None:
        member = interaction.user
        if not isinstance(member, discord.Member):
            return
        raw = await self.config.get(interaction.guild_id, "goodbye_message")  # type: ignore[arg-type]
        embed = self.bot.embeds.primary(title="Goodbye preview", description=render_placeholders(raw, member))  # type: ignore[attr-defined]
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Welcome(bot))
