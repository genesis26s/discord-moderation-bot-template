"""Centralized permission checks. Do not duplicate permission logic elsewhere."""
from __future__ import annotations

from typing import Optional

import discord
from discord import app_commands


def _has_any_admin_role(member: discord.Member, admin_roles: list[int]) -> bool:
    if not admin_roles:
        return False
    return any(r.id in admin_roles for r in member.roles)


async def get_guild_admin_roles(bot, guild_id: int) -> list[int]:
    rows = await bot.db.fetchall(
        "SELECT role_id FROM staff_roles WHERE guild_id = ? AND kind = 'admin'",
        (guild_id,),
    )
    return [r["role_id"] for r in rows]


def is_guild_admin():
    """Allow: server owner, Administrator, Manage Guild, or a configured admin role."""

    async def predicate(interaction: discord.Interaction) -> bool:
        if interaction.guild is None:
            raise app_commands.CheckFailure("This command can only be used in a server.")
        member = interaction.user
        if not isinstance(member, discord.Member):
            raise app_commands.CheckFailure("Cannot resolve member.")
        if member.id == interaction.guild.owner_id:
            return True
        perms = member.guild_permissions
        if perms.administrator or perms.manage_guild:
            return True
        admin_roles = await get_guild_admin_roles(interaction.client, interaction.guild.id)
        if _has_any_admin_role(member, admin_roles):
            return True
        raise app_commands.CheckFailure("You do not have permission to use this.")

    return app_commands.check(predicate)


def is_moderator():
    """Allow: guild admin OR Moderate Members / Manage Messages / Kick / Ban."""

    async def predicate(interaction: discord.Interaction) -> bool:
        if interaction.guild is None:
            raise app_commands.CheckFailure("This command can only be used in a server.")
        member = interaction.user
        if not isinstance(member, discord.Member):
            raise app_commands.CheckFailure("Cannot resolve member.")
        if member.id == interaction.guild.owner_id:
            return True
        perms = member.guild_permissions
        if (
            perms.administrator
            or perms.manage_guild
            or perms.moderate_members
            or perms.manage_messages
            or perms.kick_members
            or perms.ban_members
        ):
            return True
        admin_roles = await get_guild_admin_roles(interaction.client, interaction.guild.id)
        if _has_any_admin_role(member, admin_roles):
            return True
        raise app_commands.CheckFailure("You do not have permission to use this.")

    return app_commands.check(predicate)
