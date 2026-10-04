"""Moderation commands."""
from __future__ import annotations

from datetime import timedelta
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from bot.core.checks import is_moderator
from bot.core.utilities import parse_duration, humanize_timedelta
from bot.services.logging_service import LoggingService
from bot.services.moderation_service import ModerationService
from bot.views.common import ConfirmView


class Moderation(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        logging = LoggingService(bot.db)  # type: ignore[attr-defined]
        self.service = ModerationService(bot.db, logging)  # type: ignore[attr-defined]

    def _check_hierarchy(self, interaction: discord.Interaction, target: discord.Member) -> Optional[str]:
        me = interaction.guild.me  # type: ignore[union-attr]
        author = interaction.user
        if not isinstance(author, discord.Member):
            return "Author is not a member."
        if target.id == author.id:
            return "You cannot moderate yourself."
        if target.id == interaction.guild.owner_id:  # type: ignore[union-attr]
            return "You cannot moderate the server owner."
        if me and target.top_role >= me.top_role:
            return "I cannot moderate this user — their role is higher than or equal to mine."
        if author.id != interaction.guild.owner_id and target.top_role >= author.top_role:  # type: ignore[union-attr]
            return "You cannot moderate this user — their role is higher than or equal to yours."
        return None

    # ---- /ban ----
    @app_commands.command(name="ban", description="Ban a member.")
    @app_commands.describe(member="Member to ban", reason="Reason", delete_days="Days of messages to delete (0-7)")
    @is_moderator()
    async def ban(self, interaction: discord.Interaction, member: discord.Member, reason: Optional[str] = None, delete_days: app_commands.Range[int, 0, 7] = 0) -> None:
        err = self._check_hierarchy(interaction, member)
        if err:
            return await interaction.response.send_message(err, ephemeral=True)
        await member.ban(reason=f"{interaction.user}: {reason or 'No reason'}", delete_message_days=delete_days)
        await self.service.record_action(interaction.guild_id, member.id, interaction.user.id, "ban", reason)  # type: ignore[arg-type]
        await self.service.log_case(
            interaction.guild, action="Ban", user=member, moderator=interaction.user, reason=reason, color=0xED4245,  # type: ignore[arg-type]
        )
        await interaction.response.send_message(f"🔨 Banned **{member}**.", ephemeral=True)

    @app_commands.command(name="unban", description="Unban a user by ID.")
    @is_moderator()
    async def unban(self, interaction: discord.Interaction, user_id: str, reason: Optional[str] = None) -> None:
        try:
            user = discord.Object(id=int(user_id))
        except ValueError:
            return await interaction.response.send_message("Invalid user ID.", ephemeral=True)
        try:
            await interaction.guild.unban(user, reason=f"{interaction.user}: {reason or 'No reason'}")  # type: ignore[union-attr]
        except discord.NotFound:
            return await interaction.response.send_message("That user is not banned.", ephemeral=True)
        await interaction.response.send_message(f"✅ Unbanned `{user_id}`.", ephemeral=True)

    @app_commands.command(name="kick", description="Kick a member.")
    @is_moderator()
    async def kick(self, interaction: discord.Interaction, member: discord.Member, reason: Optional[str] = None) -> None:
        err = self._check_hierarchy(interaction, member)
        if err:
            return await interaction.response.send_message(err, ephemeral=True)
        await member.kick(reason=f"{interaction.user}: {reason or 'No reason'}")
        await self.service.record_action(interaction.guild_id, member.id, interaction.user.id, "kick", reason)  # type: ignore[arg-type]
        await self.service.log_case(
            interaction.guild, action="Kick", user=member, moderator=interaction.user, reason=reason, color=0xFEE75C,  # type: ignore[arg-type]
        )
        await interaction.response.send_message(f"👢 Kicked **{member}**.", ephemeral=True)

    @app_commands.command(name="timeout", description="Timeout a member.")
    @is_moderator()
    async def timeout(self, interaction: discord.Interaction, member: discord.Member, duration: str, reason: Optional[str] = None) -> None:
        td = parse_duration(duration)
        if td is None or td > timedelta(days=28):
            return await interaction.response.send_message("Invalid duration. Use e.g. `10m`, `2h`, `1d` (max 28d).", ephemeral=True)
        err = self._check_hierarchy(interaction, member)
        if err:
            return await interaction.response.send_message(err, ephemeral=True)
        try:
            await member.timeout(td, reason=f"{interaction.user}: {reason or 'No reason'}")
        except discord.Forbidden:
            return await interaction.response.send_message("I lack permission to timeout that member.", ephemeral=True)
        await self.service.record_action(interaction.guild_id, member.id, interaction.user.id, "timeout", reason, int(td.total_seconds()))  # type: ignore[arg-type]
        await interaction.response.send_message(f"⏳ Timed out **{member}** for {humanize_timedelta(td)}.", ephemeral=True)

    @app_commands.command(name="untimeout", description="Remove a timeout.")
    @is_moderator()
    async def untimeout(self, interaction: discord.Interaction, member: discord.Member, reason: Optional[str] = None) -> None:
        await member.timeout(None, reason=f"{interaction.user}: {reason or 'No reason'}")
        await interaction.response.send_message(f"✅ Removed timeout for **{member}**.", ephemeral=True)

    @app_commands.command(name="warn", description="Warn a member.")
    @is_moderator()
    async def warn(self, interaction: discord.Interaction, member: discord.Member, reason: str) -> None:
        warn_id = await self.service.add_warning(interaction.guild_id, member.id, interaction.user.id, reason)  # type: ignore[arg-type]
        await self.service.log_case(
            interaction.guild, action="Warn", user=member, moderator=interaction.user, reason=reason, color=0xFEE75C,  # type: ignore[arg-type]
            extra_fields=[("Warning ID", str(warn_id), True)],
        )
        await interaction.response.send_message(f"⚠ Warned **{member}** (ID `{warn_id}`).", ephemeral=True)

    @app_commands.command(name="unwarn", description="Delete a warning by ID.")
    @is_moderator()
    async def unwarn(self, interaction: discord.Interaction, warning_id: int) -> None:
        deleted = await self.service.delete_warning(interaction.guild_id, warning_id)  # type: ignore[arg-type]
        if not deleted:
            return await interaction.response.send_message("No warning with that ID.", ephemeral=True)
        await interaction.response.send_message(f"✅ Removed warning `{warning_id}`.", ephemeral=True)

    @app_commands.command(name="warnings", description="List warnings for a member.")
    @is_moderator()
    async def warnings(self, interaction: discord.Interaction, member: discord.Member) -> None:
        rows = await self.service.list_warnings(interaction.guild_id, member.id)  # type: ignore[arg-type]
        if not rows:
            return await interaction.response.send_message(f"**{member}** has no warnings.", ephemeral=True)
        embed = self.bot.embeds.primary(title=f"Warnings · {member}")  # type: ignore[attr-defined]
        for r in rows[:15]:
            embed.add_field(
                name=f"#{r['id']}",
                value=f"<t:{r['created_at']}:R> by <@{r['moderator_id']}>\n{r['reason'] or '—'}",
                inline=False,
            )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="purge", description="Bulk delete recent messages.")
    @app_commands.describe(amount="Number of messages (1-100)", member="Only delete messages from this user")
    @is_moderator()
    async def purge(self, interaction: discord.Interaction, amount: app_commands.Range[int, 1, 100], member: Optional[discord.Member] = None) -> None:
        if not isinstance(interaction.channel, discord.TextChannel):
            return await interaction.response.send_message("Use in a text channel.", ephemeral=True)
        await interaction.response.defer(ephemeral=True)
        def check(m: discord.Message) -> bool:
            return member is None or m.author.id == member.id
        deleted = await interaction.channel.purge(limit=amount, check=check)
        await interaction.followup.send(f"🧹 Deleted `{len(deleted)}` message(s).", ephemeral=True)

    @app_commands.command(name="slowmode", description="Set channel slowmode.")
    @is_moderator()
    async def slowmode(self, interaction: discord.Interaction, seconds: app_commands.Range[int, 0, 21600]) -> None:
        if not isinstance(interaction.channel, discord.TextChannel):
            return await interaction.response.send_message("Use in a text channel.", ephemeral=True)
        await interaction.channel.edit(slowmode_delay=seconds)
        await interaction.response.send_message(f"🐌 Slowmode set to `{seconds}s`.", ephemeral=True)

    @app_commands.command(name="lock", description="Lock a channel.")
    @is_moderator()
    async def lock(self, interaction: discord.Interaction, channel: Optional[discord.TextChannel] = None) -> None:
        channel = channel or interaction.channel  # type: ignore[assignment]
        if not isinstance(channel, discord.TextChannel):
            return await interaction.response.send_message("Invalid channel.", ephemeral=True)
        ow = channel.overwrites_for(interaction.guild.default_role)  # type: ignore[union-attr]
        ow.send_messages = False
        await channel.set_permissions(interaction.guild.default_role, overwrite=ow)  # type: ignore[union-attr]
        await interaction.response.send_message(f"🔒 Locked {channel.mention}.", ephemeral=True)

    @app_commands.command(name="unlock", description="Unlock a channel.")
    @is_moderator()
    async def unlock(self, interaction: discord.Interaction, channel: Optional[discord.TextChannel] = None) -> None:
        channel = channel or interaction.channel  # type: ignore[assignment]
        if not isinstance(channel, discord.TextChannel):
            return await interaction.response.send_message("Invalid channel.", ephemeral=True)
        ow = channel.overwrites_for(interaction.guild.default_role)  # type: ignore[union-attr]
        ow.send_messages = None
        await channel.set_permissions(interaction.guild.default_role, overwrite=ow)  # type: ignore[union-attr]
        await interaction.response.send_message(f"🔓 Unlocked {channel.mention}.", ephemeral=True)

    @app_commands.command(name="softban", description="Ban then unban to clear messages.")
    @is_moderator()
    async def softban(self, interaction: discord.Interaction, member: discord.Member, reason: Optional[str] = None) -> None:
        err = self._check_hierarchy(interaction, member)
        if err:
            return await interaction.response.send_message(err, ephemeral=True)
        await member.ban(reason=f"Softban: {reason or '—'}", delete_message_days=7)
        await interaction.guild.unban(member, reason="Softban — auto-unban")  # type: ignore[union-attr]
        await interaction.response.send_message(f"🧹 Softbanned **{member}**.", ephemeral=True)

    @app_commands.command(name="nick", description="Change a member's nickname.")
    @is_moderator()
    async def nick(self, interaction: discord.Interaction, member: discord.Member, nickname: Optional[str] = None) -> None:
        await member.edit(nick=nickname, reason=f"By {interaction.user}")
        await interaction.response.send_message(f"✏ Updated nickname for **{member}**.", ephemeral=True)

    @app_commands.command(name="role", description="Add or remove a role from a member.")
    @app_commands.choices(action=[app_commands.Choice(name="add", value="add"), app_commands.Choice(name="remove", value="remove")])
    @is_moderator()
    async def role(self, interaction: discord.Interaction, action: app_commands.Choice[str], member: discord.Member, role: discord.Role) -> None:
        me = interaction.guild.me  # type: ignore[union-attr]
        if role >= me.top_role:  # type: ignore[union-attr]
            return await interaction.response.send_message("I cannot manage that role.", ephemeral=True)
        if action.value == "add":
            await member.add_roles(role, reason=f"By {interaction.user}")
        else:
            await member.remove_roles(role, reason=f"By {interaction.user}")
        await interaction.response.send_message(f"✅ {action.value.title()}ed **{role.name}** for {member.mention}.", ephemeral=True)

    @app_commands.command(name="role-add", description="Add a role to a member.")
    @is_moderator()
    async def role_add(self, interaction: discord.Interaction, member: discord.Member, role: discord.Role) -> None:
        await member.add_roles(role, reason=f"By {interaction.user}")
        await interaction.response.send_message(f"✅ Added **{role.name}** to {member.mention}.", ephemeral=True)

    @app_commands.command(name="role-remove", description="Remove a role from a member.")
    @is_moderator()
    async def role_remove(self, interaction: discord.Interaction, member: discord.Member, role: discord.Role) -> None:
        await member.remove_roles(role, reason=f"By {interaction.user}")
        await interaction.response.send_message(f"✅ Removed **{role.name}** from {member.mention}.", ephemeral=True)

    @app_commands.command(name="moderation-config", description="Open the moderation configuration panel.")
    @is_moderator()
    async def moderation_config(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_message(
            "Open `/panel` → **Moderation** to configure moderation settings interactively.",
            ephemeral=True,
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Moderation(bot))
