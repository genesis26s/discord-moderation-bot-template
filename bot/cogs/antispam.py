"""Anti-spam system."""
from __future__ import annotations

import time
from collections import defaultdict, deque
from typing import Deque

import discord
from discord import app_commands
from discord.ext import commands

from bot.core.checks import is_guild_admin
from bot.services.config_service import ConfigService
from bot.services.logging_service import LoggingService
from bot.services.moderation_service import ModerationService


class AntiSpam(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.config = ConfigService(bot.db)  # type: ignore[attr-defined]
        logging = LoggingService(bot.db)  # type: ignore[attr-defined]
        self.mod = ModerationService(bot.db, logging)  # type: ignore[attr-defined]
        # user_id -> deque[(monotonic, content_hash)]
        self._history: dict[int, Deque[tuple[float, str]]] = defaultdict(lambda: deque(maxlen=100))
        self._last_punish: dict[int, float] = {}

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot or not message.guild:
            return
        gid = message.guild.id
        if not await self.config.get_bool(gid, "antispam_enabled"):
            return
        if isinstance(message.author, discord.Member) and message.author.guild_permissions.manage_messages:
            return

        key = f"antispam:{message.channel.id}"
        row = await self.bot.db.fetchone(  # type: ignore[attr-defined]
            "SELECT 1 FROM ignore_channels WHERE guild_id = ? AND channel_id = ? AND feature = ?",
            (gid, message.channel.id, "antispam"),
        )
        if row:
            return

        now = time.monotonic()
        window = await self.config.get_int(gid, "antispam_window")
        threshold = await self.config.get_int(gid, "antispam_msgs")
        dup_threshold = await self.config.get_int(gid, "antispam_dupes")

        history = self._history[message.author.id]
        history.append((now, message.content.lower()))

        recent = [(t, c) for (t, c) in history if now - t <= window]

        reason = None
        if len(recent) >= threshold:
            reason = f"Message spam ({len(recent)} in {window}s)"
        elif message.content and dup_threshold > 0:
            same = sum(1 for (_, c) in recent if c == message.content.lower())
            if same >= dup_threshold:
                reason = f"Duplicate messages ({same}x)"
        elif message.mentions and len(set(m.id for m in message.mentions)) >= await self.config.get_int(gid, "antispam_mentions"):
            reason = "Excessive mentions"

        if reason is None:
            return

        # Anti-false-positive cooldown per user
        if now - self._last_punish.get(message.author.id, 0) < 10:
            return
        self._last_punish[message.author.id] = now

        await self._punish(message, reason)

    async def _punish(self, message: discord.Message, reason: str) -> None:
        gid = message.guild.id  # type: ignore[union-attr]
        action = await self.config.get(gid, "antispam_action")
        timeout_secs = await self.config.get_int(gid, "antispam_timeout")

        try:
            await message.delete()
        except discord.HTTPException:
            pass

        member = message.author
        if not isinstance(member, discord.Member):
            return

        try:
            if action == "timeout":
                await member.timeout(discord.utils.utcnow() + __import__("datetime").timedelta(seconds=timeout_secs), reason=f"Anti-spam: {reason}")
            elif action == "kick":
                await member.kick(reason=f"Anti-spam: {reason}")
            elif action == "ban":
                await member.ban(reason=f"Anti-spam: {reason}", delete_message_days=1)
        except discord.Forbidden:
            pass

        await self.mod.record_action(gid, member.id, self.bot.user.id, f"antispam_{action}", reason)  # type: ignore[union-attr]
        await self.mod.logging.emit(
            message.guild,  # type: ignore[arg-type]
            "security",
            title="Anti-Spam Triggered",
            description=reason,
            color=0xED4245,
            fields=[
                ("User", f"{member.mention} (`{member.id}`)", True),
                ("Channel", message.channel.mention, True),
                ("Action", action, True),
            ],
        )

    @app_commands.command(name="antispam", description="Show anti-spam status.")
    @is_guild_admin()
    async def antispam_status(self, interaction: discord.Interaction) -> None:
        gid = interaction.guild_id  # type: ignore[assignment]
        enabled = await self.config.get_bool(gid, "antispam_enabled")
        embed = self.bot.embeds.primary(title="Anti-Spam")  # type: ignore[attr-defined]
        embed.add_field(name="Status", value="🟢 Enabled" if enabled else "🔴 Disabled", inline=True)
        embed.add_field(name="Messages", value=f"`{await self.config.get_int(gid, 'antispam_msgs')}` / `{await self.config.get_int(gid, 'antispam_window')}s`", inline=True)
        embed.add_field(name="Duplicate limit", value=f"`{await self.config.get_int(gid, 'antispam_dupes')}`", inline=True)
        embed.add_field(name="Action", value=f"`{await self.config.get(gid, 'antispam_action')}`", inline=True)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="antispam-config", description="Configure anti-spam interactively.")
    @is_guild_admin()
    async def antispam_config(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_message(
            "Open `/panel` → **Anti-Spam** to configure interactively.",
            ephemeral=True,
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(AntiSpam(bot))
