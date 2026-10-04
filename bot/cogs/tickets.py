"""Advanced ticket system."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from bot.core.checks import is_guild_admin, is_moderator
from bot.services.config_service import ConfigService
from bot.services.logging_service import LoggingService
from bot.services.ticket_service import TicketService


class TicketPanelView(discord.ui.View):
    """A persistent view is registered on `on_ready` — see register_persistent_views."""

    def __init__(self, panel_id: int, categories: list) -> None:
        super().__init__(timeout=None)
        options = []
        for c in categories[:25]:
            options.append(discord.SelectOption(
                label=c["name"][:100],
                value=str(c["id"]),
                description=(c["welcome_message"] or "")[:100] or None,
            ))
        if options:
            select = discord.ui.Select(placeholder="Choose a ticket category…", options=options, custom_id=f"ticket_open:{panel_id}")
            select.callback = self._open_ticket  # type: ignore[assignment]
            self.add_item(select)

    async def _open_ticket(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        category_id = int(interaction.data["values"][0])  # type: ignore[index]
        row = await interaction.client.db.fetchone(  # type: ignore[attr-defined]
            "SELECT * FROM ticket_categories WHERE id = ?", (category_id,)
        )
        if row is None:
            return await interaction.followup.send("That category no longer exists.", ephemeral=True)

        guild = interaction.guild
        user = interaction.user
        assert guild is not None

        # Ticket limit
        service = TicketService(interaction.client.db, LoggingService(interaction.client.db))  # type: ignore[attr-defined]
        count = await service.count_open(guild.id, user.id)
        limit = int(row["max_open_per_user"] or 1)
        if count >= limit:
            return await interaction.followup.send(f"You already have {count}/{limit} open tickets.", ephemeral=True)

        parent_category = guild.get_channel(row["category_id"]) if row["category_id"] else None
        if parent_category is not None and not isinstance(parent_category, discord.CategoryChannel):
            parent_category = None

        # Build overwrites
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            user: discord.PermissionOverwrite(view_channel=True, send_messages=True, attach_files=True, read_message_history=True),
            guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_channels=True),
        }
        support_role = guild.get_role(row["support_role_id"]) if row["support_role_id"] else None
        if support_role:
            overwrites[support_role] = discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_channels=True)

        template = row["naming_template"] or "ticket-{username}"
        name = template.replace("{username}", user.name.lower()).replace("{user_id}", str(user.id))[:95]

        try:
            channel = await guild.create_text_channel(name=name, category=parent_category, overwrites=overwrites, reason=f"Ticket by {user}")
        except discord.HTTPException as exc:
            return await interaction.followup.send(f"Failed to create ticket: {exc}", ephemeral=True)

        await service.create_ticket_record(guild.id, channel.id, row["category_id"], user.id)

        embed = interaction.client.embeds.primary(  # type: ignore[attr-defined]
            title=f"{row['name']} — Ticket",
            description=row["welcome_message"] or f"Hello {user.mention}, staff will be with you shortly.",
        )
        view = TicketControlView(ticket_user_id=user.id)
        await channel.send(content=f"{user.mention}" + (f" {support_role.mention}" if support_role else ""), embed=embed, view=view)

        await interaction.followup.send(f"✅ Ticket created: {channel.mention}", ephemeral=True)

        await LoggingService(interaction.client.db).emit(  # type: ignore[attr-defined]
            guild, "tickets", title="Ticket Opened",
            fields=[("User", user.mention, True), ("Channel", channel.mention, True), ("Category", row["name"], True)],
        )


class TicketControlView(discord.ui.View):
    def __init__(self, ticket_user_id: int) -> None:
        super().__init__(timeout=None)
        self.ticket_user_id = ticket_user_id

    @discord.ui.button(label="Claim", style=discord.ButtonStyle.success, custom_id="ticket:claim")
    async def claim(self, interaction: discord.Interaction, _btn: discord.ui.Button) -> None:
        if not isinstance(interaction.user, discord.Member) or not interaction.user.guild_permissions.manage_messages:
            return await interaction.response.send_message("Only staff can claim tickets.", ephemeral=True)
        service = TicketService(interaction.client.db, LoggingService(interaction.client.db))  # type: ignore[attr-defined]
        await service.set_claimed(interaction.channel_id, interaction.user.id)  # type: ignore[arg-type]
        await interaction.response.send_message(f"✅ Claimed by {interaction.user.mention}.")

    @discord.ui.button(label="Close", style=discord.ButtonStyle.danger, custom_id="ticket:close")
    async def close(self, interaction: discord.Interaction, _btn: discord.ui.Button) -> None:
        channel = interaction.channel
        if not isinstance(channel, discord.TextChannel):
            return
        service = TicketService(interaction.client.db, LoggingService(interaction.client.db))  # type: ignore[attr-defined]
        await service.set_status(channel.id, "closed")
        await interaction.response.send_message("🔒 Closing in 5 seconds…")
        import asyncio
        await asyncio.sleep(5)
        await LoggingService(interaction.client.db).emit(  # type: ignore[attr-defined]
            channel.guild, "tickets", title="Ticket Closed",
            fields=[("Channel", channel.name, True), ("By", interaction.user.mention, True)],
        )
        try:
            await channel.delete(reason="Ticket closed")
        except discord.HTTPException:
            pass


class Tickets(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.config = ConfigService(bot.db)  # type: ignore[attr-defined]
        self.service = TicketService(bot.db, LoggingService(bot.db))  # type: ignore[attr-defined]

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        # Register persistent views for every configured panel.
        # We iterate guilds, fetch their panels, and add views.
        for guild in self.bot.guilds:
            try:
                panels = await self.bot.db.fetchall(  # type: ignore[attr-defined]
                    "SELECT * FROM ticket_panels WHERE guild_id = ?", (guild.id,)
                )
            except Exception:
                continue
            for panel in panels:
                cats = await self.bot.db.fetchall(  # type: ignore[attr-defined]
                    "SELECT * FROM ticket_categories WHERE guild_id = ? AND panel_id = ?",
                    (guild.id, panel["id"]),
                )
                self.bot.add_view(TicketPanelView(panel["id"], cats))
                self.bot.add_view(TicketControlView(ticket_user_id=0))

    @app_commands.command(name="ticket", description="Open a ticket panel.")
    @is_guild_admin()
    async def ticket(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_message("Use `/ticket-panel` to send a panel or `/tickets-config` to configure.", ephemeral=True)

    @app_commands.command(name="tickets-config", description="Configure the ticket system.")
    @is_guild_admin()
    async def tickets_config(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_message(
            "Open `/panel` → **Tickets** to configure interactively.\n"
            "Create a panel with `/ticket-panel`, then add categories via `/ticket-category-add`.",
            ephemeral=True,
        )

    @app_commands.command(name="ticket-panel", description="Create a ticket panel in this channel.")
    @app_commands.describe(name="Panel name")
    @is_guild_admin()
    async def ticket_panel(self, interaction: discord.Interaction, name: str, title: Optional[str] = None, description: Optional[str] = None) -> None:
        if not isinstance(interaction.channel, discord.TextChannel):
            return await interaction.response.send_message("Use in a text channel.", ephemeral=True)
        embed = self.bot.embeds.primary(title=title or name, description=description or "Choose a category below to open a ticket.")  # type: ignore[attr-defined]
        msg = await interaction.channel.send(embed=embed)
        await self.bot.db.execute(  # type: ignore[attr-defined]
            "INSERT INTO ticket_panels (guild_id, name, channel_id, message_id, title, description) VALUES (?, ?, ?, ?, ?, ?)",
            (interaction.guild_id, name, interaction.channel.id, msg.id, title or name, description or ""),
        )
        row = await self.bot.db.fetchone("SELECT last_insert_rowid() AS id")  # type: ignore[attr-defined]
        panel_id = int(row["id"]) if row else 0
        self.bot.add_view(TicketPanelView(panel_id, []))
        await interaction.response.send_message(f"✅ Panel `{name}` created (id `{panel_id}`).", ephemeral=True)

    @app_commands.command(name="ticket-category-add", description="Add a category to a ticket panel.")
    @is_guild_admin()
    async def category_add(
        self,
        interaction: discord.Interaction,
        panel_id: int,
        name: str,
        category: discord.CategoryChannel,
        support_role: Optional[discord.Role] = None,
        welcome_message: Optional[str] = None,
        naming_template: Optional[str] = None,
    ) -> None:
        await self.bot.db.execute(  # type: ignore[attr-defined]
            """
            INSERT INTO ticket_categories
              (guild_id, panel_id, name, category_id, support_role_id, welcome_message, naming_template)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (interaction.guild_id, panel_id, name, category.id, support_role.id if support_role else None,
             welcome_message, naming_template or "ticket-{username}"),
        )
        # Refresh persistent view for this panel
        cats = await self.bot.db.fetchall(  # type: ignore[attr-defined]
            "SELECT * FROM ticket_categories WHERE guild_id = ? AND panel_id = ?",
            (interaction.guild_id, panel_id),
        )
        self.bot.add_view(TicketPanelView(panel_id, cats))
        await interaction.response.send_message(f"✅ Category `{name}` added to panel `{panel_id}`.", ephemeral=True)

    @app_commands.command(name="ticket-add", description="Add a user to the current ticket.")
    @is_moderator()
    async def ticket_add(self, interaction: discord.Interaction, member: discord.Member) -> None:
        if not isinstance(interaction.channel, discord.TextChannel):
            return
        await interaction.channel.set_permissions(member, view_channel=True, send_messages=True)
        await interaction.response.send_message(f"✅ Added {member.mention}.")

    @app_commands.command(name="ticket-remove", description="Remove a user from the current ticket.")
    @is_moderator()
    async def ticket_remove(self, interaction: discord.Interaction, member: discord.Member) -> None:
        if not isinstance(interaction.channel, discord.TextChannel):
            return
        await interaction.channel.set_permissions(member, overwrite=None)
        await interaction.response.send_message(f"✅ Removed {member.mention}.")

    @app_commands.command(name="ticket-claim", description="Claim the current ticket.")
    @is_moderator()
    async def ticket_claim(self, interaction: discord.Interaction) -> None:
        if interaction.channel_id is None:
            return
        await self.service.set_claimed(interaction.channel_id, interaction.user.id)
        await interaction.response.send_message(f"✅ Claimed by {interaction.user.mention}.")

    @app_commands.command(name="ticket-close", description="Close the current ticket.")
    @is_moderator()
    async def ticket_close(self, interaction: discord.Interaction, reason: Optional[str] = None) -> None:
        if interaction.channel_id is None:
            return
        await self.service.set_status(interaction.channel_id, "closed")
        await interaction.response.send_message(f"🔒 Ticket closed. Reason: {reason or '—'}")

    @app_commands.command(name="ticket-reopen", description="Reopen the current ticket.")
    @is_moderator()
    async def ticket_reopen(self, interaction: discord.Interaction) -> None:
        if interaction.channel_id is None:
            return
        await self.service.set_status(interaction.channel_id, "open")
        await interaction.response.send_message("🔓 Ticket reopened.")

    @app_commands.command(name="ticket-delete", description="Delete the current ticket channel.")
    @is_moderator()
    async def ticket_delete(self, interaction: discord.Interaction) -> None:
        if isinstance(interaction.channel, discord.TextChannel):
            await self.service.delete_ticket(interaction.channel.id)
            await interaction.response.send_message("🗑 Deleting…")
            try:
                await interaction.channel.delete(reason=f"Ticket deleted by {interaction.user}")
            except discord.HTTPException:
                pass

    @app_commands.command(name="ticket-rename", description="Rename the current ticket channel.")
    @is_moderator()
    async def ticket_rename(self, interaction: discord.Interaction, name: str) -> None:
        if isinstance(interaction.channel, discord.TextChannel):
            await interaction.channel.edit(name=name[:95])
            await interaction.response.send_message(f"✏ Renamed to `{name}`.")

    @app_commands.command(name="ticket-transcript", description="Generate a transcript of the current ticket.")
    @is_moderator()
    async def ticket_transcript(self, interaction: discord.Interaction) -> None:
        if not isinstance(interaction.channel, discord.TextChannel):
            return
        await interaction.response.defer(ephemeral=True)
        lines = []
        async for msg in interaction.channel.history(limit=1000, oldest_first=True):
            lines.append(f"[{msg.created_at.isoformat()}] {msg.author}: {msg.content}")
        transcript = "\n".join(lines) or "(no messages)"
        import io
        file = discord.File(io.BytesIO(transcript.encode("utf-8")), filename=f"transcript-{interaction.channel.id}.txt")
        await interaction.followup.send("📄 Transcript:", file=file, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Tickets(bot))
