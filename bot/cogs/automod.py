"""Configurable AutoMod."""
from __future__ import annotations

import re

import discord
from discord import app_commands
from discord.ext import commands

from bot.core.checks import is_guild_admin
from bot.services.config_service import ConfigService
from bot.services.logging_service import LoggingService

INVITE_RE = re.compile(r"(?:discord\.gg|discord(?:app)?\.com/invite)/[a-zA-Z0-9-]+", re.IGNORECASE)
URL_RE = re.compile(r"https?://\S+")
REPEAT_RE = re.compile(r"(.)\1{7,}")  # 8+ repeats


class AutoMod(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.config = ConfigService(bot.db)  # type: ignore[attr-defined]
        self.logging = LoggingService(bot.db)  # type: ignore[attr-defined]

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot or not message.guild:
            return
        gid = message.guild.id
        if not await self.config.get_bool(gid, "automod_enabled"):
            return
        if isinstance(message.author, discord.Member) and message.author.guild_permissions.manage_messages:
            return

        content = message.content or ""
        reason: str | None = None

        if await self.config.get_bool(gid, "automod_invites") and INVITE_RE.search(content):
            reason = "Discord invite link"
        elif await self.config.get_bool(gid, "automod_links") and URL_RE.search(content):
            reason = "Link posted"
        elif await self.config.get_int(gid, "automod_caps") > 0:
            letters = [c for c in content if c.isalpha()]
            if len(letters) >= 12:
                upper = sum(1 for c in letters if c.isupper())
                if (upper / len(letters)) * 100 >= await self.config.get_int(gid, "automod_caps"):
                    reason = "Excessive caps"

        if reason is None:
            repeat_threshold = await self.config.get_int(gid, "automod_repeat")
            if repeat_threshold > 0 and REPEAT_RE.search(content):
                reason = "Repeated characters"

        if reason is None:
            rows = await self.bot.db.fetchall(  # type: ignore[attr-defined]
                "SELECT word FROM automod_words WHERE guild_id = ?",
                (gid,),
            )
            lowered = content.lower()
            for r in rows:
                if r["word"] in lowered:
                    reason = "Blacklisted word"
                    break

        if reason is None:
            return

        await self._punish(message, reason)

    async def _punish(self, message: discord.Message, reason: str) -> None:
        action = await self.config.get(message.guild.id, "automod_action")  # type: ignore[union-attr]
        try:
            await message.delete()
        except discord.HTTPException:
            pass
        member = message.author
        if isinstance(member, discord.Member):
            try:
                if action == "timeout":
                    await member.timeout(discord.utils.utcnow() + __import__("datetime").timedelta(minutes=10), reason=f"AutoMod: {reason}")
                elif action == "kick":
                    await member.kick(reason=f"AutoMod: {reason}")
                elif action == "ban":
                    await member.ban(reason=f"AutoMod: {reason}", delete_message_days=1)
            except discord.Forbidden:
                pass
        await self.logging.emit(
            message.guild,  # type: ignore[arg-type]
            "security",
            title="AutoMod Triggered",
            description=reason,
            color=0xFEE75C,
            fields=[("User", f"{message.author.mention}", True), ("Channel", message.channel.mention, True), ("Action", action, True)],
        )

    @app_commands.command(name="automod", description="Show AutoMod status.")
    @is_guild_admin()
    async def automod_status(self, interaction: discord.Interaction) -> None:
        gid = interaction.guild_id  # type: ignore[assignment]
        embed = self.bot.embeds.primary(title="AutoMod")  # type: ignore[attr-defined]
        embed.add_field(name="Status", value="🟢 Enabled" if await self.config.get_bool(gid, "automod_enabled") else "🔴 Disabled", inline=True)
        embed.add_field(name="Invites blocked", value=str(await self.config.get_bool(gid, "automod_invites")), inline=True)
        embed.add_field(name="Links blocked", value=str(await self.config.get_bool(gid, "automod_links")), inline=True)
        embed.add_field(name="Caps threshold", value=f"{await self.config.get_int(gid, 'automod_caps')}%", inline=True)
        embed.add_field(name="Action", value=f"`{await self.config.get(gid, 'automod_action')}`", inline=True)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="automod-config", description="Configure AutoMod interactively.")
    @is_guild_admin()
    async def automod_config(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_message(
            "Open `/panel` → **AutoMod** to configure interactively. Use `/automod-word-add` and `/automod-word-remove` for words.",
            ephemeral=True,
        )

    @app_commands.command(name="automod-word-add", description="Add a blacklisted word.")
    @is_guild_admin()
    async def word_add(self, interaction: discord.Interaction, word: str) -> None:
        await self.bot.db.execute(  # type: ignore[attr-defined]
            "INSERT OR IGNORE INTO automod_words (guild_id, word) VALUES (?, ?)",
            (interaction.guild_id, word.lower()),
        )
        await interaction.response.send_message(f"✅ Added `{word}`.", ephemeral=True)

    @app_commands.command(name="automod-word-remove", description="Remove a blacklisted word.")
    @is_guild_admin()
    async def word_remove(self, interaction: discord.Interaction, word: str) -> None:
        await self.bot.db.execute(  # type: ignore[attr-defined]
            "DELETE FROM automod_words WHERE guild_id = ? AND word = ?",
            (interaction.guild_id, word.lower()),
        )
        await interaction.response.send_message(f"✅ Removed `{word}`.", ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(AutoMod(bot))
