"""Anti-nuke system — monitors destructive actions via audit logs."""
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
from bot.services.security_service import SecurityService


class AntiNuke(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.config = ConfigService(bot.db)  # type: ignore[attr-defined]
        self.security = SecurityService(bot.db, LoggingService(bot.db))  # type: ignore[attr-defined]
        # executor_id -> { action -> deque[monotonic] }
        self._events: dict[int, dict[str, Deque[float]]] = defaultdict(lambda: defaultdict(lambda: deque(maxlen=50)))
        self._last_punish: dict[int, float] = {}

    async def _is_trusted(self, guild: discord.Guild, user_id: int) -> bool:
        if user_id == self.bot.user.id:  # type: ignore[union-attr]
            return True
        if user_id == guild.owner_id:
            return True
        row = await self.bot.db.fetchone(  # type: ignore[attr-defined]
            "SELECT 1 FROM trusted_users WHERE guild_id = ? AND user_id = ?",
            (guild.id, user_id),
        )
        if row:
            return True
        member = guild.get_member(user_id)
        if member is None:
            return False
        rows = await self.bot.db.fetchall(  # type: ignore[attr-defined]
            "SELECT role_id FROM staff_roles WHERE guild_id = ? AND kind = 'admin'",
            (guild.id,),
        )
        admin_role_ids = {r["role_id"] for r in rows}
        return any(role.id in admin_role_ids for role in member.roles)

    async def _executor_from_audit(self, guild: discord.Guild, action: discord.AuditLogAction) -> tuple[discord.abc.User | None, object | None]:
        try:
            async for entry in guild.audit_logs(limit=5, action=action):
                if (discord.utils.utcnow() - entry.created_at).total_seconds() < 8:
                    return entry.user, entry.target
        except (discord.Forbidden, discord.HTTPException):
            return None, None
        return None, None

    async def _check(self, guild: discord.Guild, action: str, executor: discord.abc.User | None, threshold: int, window: int, details: str, severity: str = "HIGH") -> None:
        if executor is None:
            return
        if await self._is_trusted(guild, executor.id):
            return
        now = time.monotonic()
        q = self._events[executor.id][action]
        q.append(now)
        cutoff = now - window
        while q and q[0] < cutoff:
            q.popleft()
        if len(q) < threshold:
            return
        if now - self._last_punish.get(executor.id, 0) < 30:
            return
        self._last_punish[executor.id] = now
        await self._punish(guild, executor, action, details, severity)

    async def _punish(self, guild: discord.Guild, executor: discord.abc.User, action: str, details: str, severity: str) -> None:
        await self.security.record_incident(
            guild.id,
            type_="antinuke",
            severity=severity,
            executor_id=executor.id,
            details=f"{action}: {details}",
        )

        action_setting = await self.config.get(guild.id, "antinuke_action")
        member = guild.get_member(executor.id)
        if member is None:
            return

        try:
            if action_setting == "ban":
                await member.ban(reason=f"Anti-Nuke: {details}")
            elif action_setting == "kick":
                await member.kick(reason=f"Anti-Nuke: {details}")
            elif action_setting == "strip":
                for role in member.roles:
                    if role.is_default() or role.managed:
                        continue
                    if role >= guild.me.top_role:  # type: ignore[union-attr]
                        continue
                    try:
                        await member.remove_roles(role, reason="Anti-Nuke: strip")
                    except discord.HTTPException:
                        continue
        except discord.Forbidden:
            pass

        alert_id = await self.config.get(guild.id, "antinuke_alert_channel")
        channel = guild.get_channel(int(alert_id)) if alert_id.isdigit() else None
        if channel:
            embed = self.bot.embeds.error(title="🚨 Anti-Nuke Triggered", description=details)  # type: ignore[attr-defined]
            embed.add_field(name="Executor", value=f"{executor} (`{executor.id}`)", inline=True)
            embed.add_field(name="Action", value=f"`{action_setting}`", inline=True)
            try:
                await channel.send(embed=embed)
            except discord.HTTPException:
                pass

    # ---- Audit log listeners ----
    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel) -> None:
        gid = channel.guild.id
        if not await self.config.get_bool(gid, "antinuke_enabled"):
            return
        executor, _ = await self._executor_from_audit(channel.guild, discord.AuditLogAction.channel_delete)
        threshold = await self.config.get_int(gid, "antinuke_channel_delete")
        await self._check(channel.guild, "channel_delete", executor, threshold, 10, f"{threshold}+ channels deleted within 10s")

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role: discord.Role) -> None:
        gid = role.guild.id
        if not await self.config.get_bool(gid, "antinuke_enabled"):
            return
        executor, _ = await self._executor_from_audit(role.guild, discord.AuditLogAction.role_delete)
        threshold = await self.config.get_int(gid, "antinuke_role_delete")
        await self._check(role.guild, "role_delete", executor, threshold, 15, f"{threshold}+ roles deleted within 15s")

    @commands.Cog.listener()
    async def on_member_ban(self, guild: discord.Guild, user: discord.User) -> None:
        gid = guild.id
        if not await self.config.get_bool(gid, "antinuke_enabled"):
            return
        executor, _ = await self._executor_from_audit(guild, discord.AuditLogAction.ban)
        threshold = await self.config.get_int(gid, "antinuke_ban_count")
        await self._check(guild, "ban", executor, threshold, 15, f"{threshold}+ bans within 15s")

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member) -> None:
        gid = member.guild.id
        if not await self.config.get_bool(gid, "antinuke_enabled"):
            return
        executor, target = await self._executor_from_audit(member.guild, discord.AuditLogAction.kick)
        if target is None or getattr(target, "id", None) != member.id:
            return
        threshold = await self.config.get_int(gid, "antinuke_kick_count")
        await self._check(member.guild, "kick", executor, threshold, 15, f"{threshold}+ kicks within 15s")

    @commands.Cog.listener()
    async def on_audit_log_entry_create(self, entry: discord.AuditLogEntry) -> None:
        gid = entry.guild.id
        if not await self.config.get_bool(gid, "antinuke_enabled"):
            return
        if entry.action == discord.AuditLogAction.webhook_create:
            threshold = await self.config.get_int(gid, "antinuke_webhook")
            await self._check(entry.guild, "webhook_create", entry.user, threshold, 15, f"{threshold}+ webhooks created within 15s")

    # ---- Commands ----
    @app_commands.command(name="antinuke", description="Show anti-nuke status.")
    @is_guild_admin()
    async def antinuke_status(self, interaction: discord.Interaction) -> None:
        gid = interaction.guild_id  # type: ignore[assignment]
        embed = self.bot.embeds.primary(title="Anti-Nuke")  # type: ignore[attr-defined]
        embed.add_field(name="Status", value="🟢 Enabled" if await self.config.get_bool(gid, "antinuke_enabled") else "🔴 Disabled", inline=True)
        embed.add_field(name="Action", value=f"`{await self.config.get(gid, 'antinuke_action')}`", inline=True)
        embed.add_field(name="Channel delete", value=f"`{await self.config.get_int(gid, 'antinuke_channel_delete')}` / 10s", inline=True)
        embed.add_field(name="Role delete", value=f"`{await self.config.get_int(gid, 'antinuke_role_delete')}` / 15s", inline=True)
        embed.add_field(name="Ban spike", value=f"`{await self.config.get_int(gid, 'antinuke_ban_count')}` / 15s", inline=True)
        embed.add_field(name="Kick spike", value=f"`{await self.config.get_int(gid, 'antinuke_kick_count')}` / 15s", inline=True)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="antinuke-config", description="Configure anti-nuke interactively.")
    @is_guild_admin()
    async def antinuke_config(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_message(
            "Open `/panel` → **Anti-Nuke** to configure interactively.",
            ephemeral=True,
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(AntiNuke(bot))
