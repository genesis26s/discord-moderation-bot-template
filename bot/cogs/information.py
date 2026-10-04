"""Info & help commands."""
from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands


HELP_SECTIONS = {
    "Security": [
        "/security — dashboard",
        "/security-config — configure",
        "/antinuke, /antinuke-config",
        "/antiraid, /antiraid-config",
        "/antispam, /antispam-config",
        "/automod, /automod-config",
        "/serverwatch, /serverwatch-config",
        "/lockdown, /unlockdown",
    ],
    "Moderation": [
        "/ban, /unban, /kick",
        "/timeout, /untimeout",
        "/warn, /unwarn, /warnings",
        "/purge, /slowmode, /lock, /unlock",
        "/softban, /nick, /role",
        "/role-add, /role-remove",
    ],
    "Tickets": [
        "/ticket, /tickets-config",
        "/ticket-panel, /ticket-category-add",
        "/ticket-add, /ticket-remove",
        "/ticket-claim, /ticket-close, /ticket-reopen",
        "/ticket-delete, /ticket-transcript, /ticket-rename",
    ],
    "Welcome & Logging": [
        "/welcome-config, /welcome-test, /goodbye-test",
        "/logging-config, /logs, /audit",
    ],
    "Server & Utility": [
        "/panel — control center",
        "/server, /serverinfo, /membercount",
        "/roles, /channels, /config",
        "/avatar, /userinfo, /servericon",
        "/ping, /botinfo, /invite, /uptime",
        "/permissions, /roleinfo",
    ],
    "Roles": [
        "/roles-config",
        "/add-staff-role, /add-admin-role",
        "/remove-staff-role",
        "/trust-user, /untrust-user",
    ],
}


class HelpSelect(discord.ui.Select):
    def __init__(self) -> None:
        options = [discord.SelectOption(label=k, value=k) for k in HELP_SECTIONS.keys()]
        super().__init__(placeholder="Choose a category…", options=options)

    async def callback(self, interaction: discord.Interaction) -> None:
        section = self.values[0]
        lines = "\n".join(f"• {line}" for line in HELP_SECTIONS[section])
        embed = interaction.client.embeds.primary(title=f"Help · {section}", description=lines)  # type: ignore[attr-defined]
        await interaction.response.edit_message(embed=embed, view=self.view)


class HelpView(discord.ui.View):
    def __init__(self) -> None:
        super().__init__(timeout=180)
        self.add_item(HelpSelect())


class Information(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(name="help", description="Interactive help menu.")
    async def help(self, interaction: discord.Interaction) -> None:
        embed = self.bot.embeds.primary(title="Help", description="Select a category from the dropdown.")  # type: ignore[attr-defined]
        await interaction.response.send_message(embed=embed, view=HelpView(), ephemeral=True)

    @app_commands.command(name="server", description="Show server summary.")
    async def server(self, interaction: discord.Interaction) -> None:
        g = interaction.guild
        if g is None:
            return
        embed = self.bot.embeds.primary(title=g.name)  # type: ignore[attr-defined]
        if g.icon:
            embed.set_thumbnail(url=g.icon.url)
        embed.add_field(name="ID", value=str(g.id), inline=True)
        embed.add_field(name="Owner", value=f"<@{g.owner_id}>", inline=True)
        embed.add_field(name="Members", value=str(g.member_count), inline=True)
        embed.add_field(name="Channels", value=str(len(g.channels)), inline=True)
        embed.add_field(name="Roles", value=str(len(g.roles)), inline=True)
        embed.add_field(name="Created", value=f"<t:{int(g.created_at.timestamp())}:R>", inline=True)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="serverinfo", description="Alias for /server.")
    async def serverinfo(self, interaction: discord.Interaction) -> None:
        await self.server.callback(self, interaction)  # type: ignore[attr-defined]

    @app_commands.command(name="membercount", description="Show the guild member count.")
    async def membercount(self, interaction: discord.Interaction) -> None:
        g = interaction.guild
        if g is None:
            return
        humans = sum(1 for m in g.members if not m.bot)
        bots = (g.member_count or 0) - humans
        await interaction.response.send_message(f"👥 **{g.member_count}** total · `{humans}` humans · `{bots}` bots")

    @app_commands.command(name="roles", description="List guild roles.")
    async def roles(self, interaction: discord.Interaction) -> None:
        g = interaction.guild
        if g is None:
            return
        names = [f"<@&{r.id}>" for r in reversed(g.roles) if not r.is_default()]
        await interaction.response.send_message("\n".join(names[:60]) or "No roles.", ephemeral=True)

    @app_commands.command(name="channels", description="List guild channels.")
    async def channels(self, interaction: discord.Interaction) -> None:
        g = interaction.guild
        if g is None:
            return
        names = [c.mention for c in g.text_channels]
        await interaction.response.send_message("\n".join(names[:60]) or "No channels.", ephemeral=True)

    @app_commands.command(name="config", description="Show current guild configuration summary.")
    async def config(self, interaction: discord.Interaction) -> None:
        rows = await self.bot.db.fetchall(  # type: ignore[attr-defined]
            "SELECT key, value FROM guild_config WHERE guild_id = ?", (interaction.guild_id,),
        )
        if not rows:
            return await interaction.response.send_message("No configuration yet. Run `/panel`.", ephemeral=True)
        embed = self.bot.embeds.primary(title="Guild Configuration")  # type: ignore[attr-defined]
        for r in rows[:24]:
            embed.add_field(name=r["key"], value=(r["value"] or "—")[:60], inline=True)
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Information(bot))
