"""Staff/admin role management."""
from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from bot.core.checks import is_guild_admin


class Roles(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(name="roles-config", description="Configure staff and admin roles.")
    @is_guild_admin()
    async def roles_config(self, interaction: discord.Interaction) -> None:
        rows = await self.bot.db.fetchall(  # type: ignore[attr-defined]
            "SELECT role_id, kind FROM staff_roles WHERE guild_id = ?", (interaction.guild_id,)
        )
        embed = self.bot.embeds.primary(title="Configured Staff Roles")  # type: ignore[attr-defined]
        if not rows:
            embed.description = "No roles configured. Use `/add-staff-role` and `/add-admin-role`."
        else:
            for r in rows:
                embed.add_field(name=f"<@&{r['role_id']}>", value=r["kind"], inline=True)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="add-staff-role", description="Grant a role access to staff commands.")
    @is_guild_admin()
    async def add_staff_role(self, interaction: discord.Interaction, role: discord.Role) -> None:
        await self.bot.db.execute(  # type: ignore[attr-defined]
            "INSERT OR IGNORE INTO staff_roles (guild_id, role_id, kind) VALUES (?, ?, 'staff')",
            (interaction.guild_id, role.id),
        )
        await interaction.response.send_message(f"✅ {role.mention} → staff.", ephemeral=True)

    @app_commands.command(name="add-admin-role", description="Grant a role access to the admin panel.")
    @is_guild_admin()
    async def add_admin_role(self, interaction: discord.Interaction, role: discord.Role) -> None:
        await self.bot.db.execute(  # type: ignore[attr-defined]
            "INSERT OR IGNORE INTO staff_roles (guild_id, role_id, kind) VALUES (?, ?, 'admin')",
            (interaction.guild_id, role.id),
        )
        await interaction.response.send_message(f"✅ {role.mention} → admin.", ephemeral=True)

    @app_commands.command(name="remove-staff-role", description="Remove a staff/admin role.")
    @is_guild_admin()
    async def remove_staff_role(self, interaction: discord.Interaction, role: discord.Role) -> None:
        await self.bot.db.execute(  # type: ignore[attr-defined]
            "DELETE FROM staff_roles WHERE guild_id = ? AND role_id = ?",
            (interaction.guild_id, role.id),
        )
        await interaction.response.send_message(f"✅ Removed {role.mention}.", ephemeral=True)

    @app_commands.command(name="trust-user", description="Add a user to the anti-nuke trusted list.")
    @is_guild_admin()
    async def trust_user(self, interaction: discord.Interaction, member: discord.Member) -> None:
        await self.bot.db.execute(  # type: ignore[attr-defined]
            "INSERT OR IGNORE INTO trusted_users (guild_id, user_id) VALUES (?, ?)",
            (interaction.guild_id, member.id),
        )
        await interaction.response.send_message(f"✅ Trusted {member.mention}.", ephemeral=True)

    @app_commands.command(name="untrust-user", description="Remove a user from the trusted list.")
    @is_guild_admin()
    async def untrust_user(self, interaction: discord.Interaction, member: discord.Member) -> None:
        await self.bot.db.execute(  # type: ignore[attr-defined]
            "DELETE FROM trusted_users WHERE guild_id = ? AND user_id = ?",
            (interaction.guild_id, member.id),
        )
        await interaction.response.send_message(f"✅ Untrusted {member.mention}.", ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Roles(bot))
