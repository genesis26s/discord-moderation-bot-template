"""Info & help commands."""
from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands


HELP_SECTIONS = {
    "Verification": [
        "/verification-panel - Post the public verification panel",
        "/verify - Start verification (same as the button)",
        "/verify-roblox - Link your Roblox account",
        "/verify-roblox-status - Show your linked Roblox account",
        "/verify-unlink - Unlink your Roblox account",
        "/verify-status - Show a member's latest assessment",
        "/verify-queue - List members pending manual review",
        "/verify-review - Open the review panel for a member",
        "/verify-false-positive - Mark an assessment as a false positive",
        "/verification-config - Show verification configuration",
        "/verification-role - Set the role given on success",
        "/verification-quarantine-role - Set the quarantine role",
        "/verify-add-signature - Add an abuse signature",
        "/verify-remove-signature - Remove an abuse signature",
    ],
    "Security": [
        "/security - Security dashboard",
        "/security-config - Configure security systems",
        "/antinuke, /antinuke-config",
        "/antiraid, /antiraid-config",
        "/antispam, /antispam-config",
        "/automod, /automod-config",
        "/automod-word-add, /automod-word-remove",
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
        "/moderation-config",
    ],
    "Tickets": [
        "/ticket - Ticket system info",
        "/tickets-config - Open the admin console",
        "/ticket-panel - Open the admin console",
        "/ticket-add, /ticket-remove",
        "/ticket-claim, /ticket-close, /ticket-reopen",
        "/ticket-delete, /ticket-transcript, /ticket-rename",
    ],
    "Welcome & Logging": [
        "/welcome-config, /welcome-test, /goodbye-test",
        "/logging-config - Route a category to a channel",
        "/logs - Show current log configuration",
        "/audit - Show the last 10 audit log entries",
    ],
    "Roles": [
        "/roles-config - Show configured staff roles",
        "/add-staff-role, /add-admin-role",
        "/remove-staff-role",
        "/trust-user, /untrust-user",
    ],
    "Server & Utility": [
        "/panel - Central control center",
        "/server, /serverinfo, /membercount",
        "/roles, /channels, /config",
        "/avatar, /userinfo, /servericon",
        "/ping, /botinfo, /invite, /uptime",
        "/permissions, /roleinfo",
    ],
    "Owner": [
        "/sync - Owner only: re-sync commands to this server",
        "/resync-global - Owner only: clear and re-sync globally",
    ],
}


class HelpSelect(discord.ui.Select):
    def __init__(self) -> None:
        options = []
        for name in HELP_SECTIONS.keys():
            options.append(discord.SelectOption(label=name, value=name))
        super().__init__(placeholder="Choose a category...", options=options)

    async def callback(self, interaction: discord.Interaction) -> None:
        section = self.values[0]
        lines = HELP_SECTIONS.get(section, [])
        body = "\n".join("- " + line for line in lines) if lines else "No commands in this section."
        embed = interaction.client.embeds.primary(  # type: ignore[attr-defined]
            title="Help - " + section,
            description=body,
        )
        await interaction.response.edit_message(embed=embed, view=self.view)


class HelpView(discord.ui.View):
    def __init__(self) -> None:
        super().__init__(timeout=180)
        self.add_select = HelpSelect()
        self.add_item(self.add_select)


class Information(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(name="help", description="Interactive help menu.")
    async def help(self, interaction: discord.Interaction) -> None:
        embed = self.bot.embeds.primary(  # type: ignore[attr-defined]
            title="Help",
            description=(
                "Select a category from the dropdown to see its commands.\n\n"
                "New here? Start with `/panel` to configure the bot, or "
                "`/verification-panel` to set up verification."
            ),
        )
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
        embed.add_field(name="Owner", value="<@" + str(g.owner_id) + ">", inline=True)
        embed.add_field(name="Members", value=str(g.member_count), inline=True)
        embed.add_field(name="Channels", value=str(len(g.channels)), inline=True)
        embed.add_field(name="Roles", value=str(len(g.roles)), inline=True)
        embed.add_field(name="Created", value="<t:" + str(int(g.created_at.timestamp())) + ":R>", inline=True)
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
        await interaction.response.send_message(
            "Total: **" + str(g.member_count) + "** | Humans: `" + str(humans) + "` | Bots: `" + str(bots) + "`"
        )

    @app_commands.command(name="roles", description="List guild roles.")
    async def roles(self, interaction: discord.Interaction) -> None:
        g = interaction.guild
        if g is None:
            return
        names = [("<@&" + str(r.id) + ">") for r in reversed(g.roles) if not r.is_default()]
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
            "SELECT key, value FROM guild_config WHERE guild_id = ?",
            (interaction.guild_id,),
        )
        if not rows:
            return await interaction.response.send_message(
                "No configuration yet. Run `/panel`.", ephemeral=True
            )
        embed = self.bot.embeds.primary(title="Guild Configuration")  # type: ignore[attr-defined]
        for r in rows[:24]:
            value = r["value"] or "-"
            embed.add_field(name=str(r["key"]), value=value[:60], inline=True)
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Information(bot))
