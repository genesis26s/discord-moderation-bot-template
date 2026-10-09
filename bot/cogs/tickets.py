"""Ticket system - admin console, public request panel, full lifecycle."""
from __future__ import annotations

import asyncio
import io
import logging
import time as _time
from datetime import datetime, timezone

import discord
from discord import app_commands
from discord.ext import commands

from bot.core.checks import is_guild_admin, is_moderator
from bot.services.logging_service import LoggingService
from bot.services.ticket_service import TicketService

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------
def _now() -> int:
    return int(datetime.now(timezone.utc).timestamp())


def _as_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _member_is_staff(member) -> bool:
    if not isinstance(member, discord.Member):
        return False
    perms = member.guild_permissions
    if perms.administrator:
        return True
    if perms.manage_messages:
        return True
    if perms.manage_guild:
        return True
    return False


async def _config_get(bot, guild_id, key, default=""):
    row = await bot.db.fetchone(
        "SELECT value FROM guild_config WHERE guild_id = ? AND key = ?",
        (guild_id, key),
    )
    if row is None:
        return default
    return row["value"] if row["value"] is not None else default


async def _config_set(bot, guild_id, key, value):
    await bot.db.set_guild_config(guild_id, key, str(value))


# ---------------------------------------------------------------------------
# Embed builders
# ---------------------------------------------------------------------------
def _panel_embed(row) -> discord.Embed:
    color = _as_int(row["color"], 0x5865F2) if row["color"] else 0x5865F2
    embed = discord.Embed(
        title=(row["title"] or "Support Centre"),
        description=(row["description"] or "Pick a category below to open a request."),
        color=color,
    )
    if row["footer"]:
        embed.set_footer(text=row["footer"])
    if row["banner_url"]:
        embed.set_image(url=row["banner_url"])
    return embed


def _dashboard_embed(bot_name, category_count, stats, archive_channel):
    embed = discord.Embed(
        title="Support Operations Console",
        description=(
            "This is your server's support control room. Use the buttons below to build "
            "and manage ticket categories, customise the public request panel, and decide "
            "where closed tickets get archived."
        ),
        color=0x2B2D31,
    )
    embed.add_field(name="Categories Configured", value=str(category_count), inline=True)
    embed.add_field(name="Archive Channel", value=archive_channel, inline=True)
    embed.add_field(name="Tickets Opened (all time)", value=str(stats["total"]), inline=False)
    embed.add_field(name="Currently Open", value=str(stats["open"]), inline=True)
    embed.add_field(name="Closed", value=str(stats["closed"]), inline=True)
    avg = stats["avg_rating"]
    embed.add_field(name="Average Rating", value=avg, inline=True)
    embed.set_footer(text=bot_name + " | support system")
    return embed


# ---------------------------------------------------------------------------
# Modals
# ---------------------------------------------------------------------------
class CategoryModal(discord.ui.Modal):
    """Create or modify a ticket category."""

    def __init__(self, *, guild_id, panel_id, existing=None, on_saved=None):
        is_edit = existing is not None
        super().__init__(title=("Modify Category" if is_edit else "New Category")[:45])
        self.guild_id = guild_id
        self.panel_id = panel_id
        self.existing = existing
        self.on_saved = on_saved

        name_default = str(existing["name"]) if existing else ""
        msg_default = str(existing["welcome_message"]) if existing and existing["welcome_message"] else (
            "Thanks for reaching out. Someone from the team will be with you shortly."
        )
        tpl_default = str(existing["naming_template"]) if existing and existing["naming_template"] else "ticket-{username}"
        emoji_default = str(existing["emoji"]) if existing and existing["emoji"] else ""
        prio_default = str(existing["button_style"]) if existing and existing["button_style"] else "primary"

        self.name_input = discord.ui.TextInput(
            label="Display name",
            placeholder="e.g. General Support",
            default=name_default,
            max_length=80,
            required=True,
        )
        self.welcome_input = discord.ui.TextInput(
            label="Greeting shown inside the ticket",
            default=msg_default,
            max_length=800,
            style=discord.TextStyle.paragraph,
            required=False,
        )
        self.naming_input = discord.ui.TextInput(
            label="Channel name pattern",
            placeholder="ticket-{username} or {user_id}-case",
            default=tpl_default,
            max_length=80,
            required=False,
        )
        self.emoji_input = discord.ui.TextInput(
            label="Optional emoji prefix",
            default=emoji_default,
            max_length=20,
            required=False,
        )
        self.priority_input = discord.ui.TextInput(
            label="Priority (low / normal / high / urgent)",
            default=prio_default,
            max_length=10,
            required=False,
        )

        self.add_item(self.name_input)
        self.add_item(self.welcome_input)
        self.add_item(self.naming_input)
        self.add_item(self.emoji_input)
        self.add_item(self.priority_input)

    async def on_submit(self, interaction: discord.Interaction):
        name = self.name_input.value.strip()[:80]
        welcome = (self.welcome_input.value or "").strip()[:800]
        naming = (self.naming_input.value or "ticket-{username}").strip() or "ticket-{username}"
        emoji = (self.emoji_input.value or "").strip()[:20]
        priority = (self.priority_input.value or "normal").strip().lower()
        if priority not in ("low", "normal", "high", "urgent"):
            priority = "normal"

        if self.existing:
            await interaction.client.db.execute(
                """UPDATE ticket_categories
                   SET name = ?, welcome_message = ?, naming_template = ?, emoji = ?, button_style = ?
                   WHERE id = ? AND guild_id = ?""",
                (name, welcome, naming, emoji, priority,
                 _as_int(self.existing["id"]), self.guild_id),
            )
            await interaction.response.send_message("Category updated.", ephemeral=True)
            if self.on_saved:
                await self.on_saved()
            return

        await interaction.client.db.execute(
            """INSERT INTO ticket_categories
               (guild_id, panel_id, name, welcome_message, naming_template, emoji, button_style, max_open_per_user)
               VALUES (?, ?, ?, ?, ?, ?, ?, 1)""",
            (self.guild_id, self.panel_id, name, welcome, naming, emoji, priority),
        )
        row = await interaction.client.db.fetchone("SELECT last_insert_rowid() AS id")
        new_id = _as_int(row["id"] if row else 0)

        picker = ChannelRolePickerView(
            guild_id=self.guild_id,
            panel_id=self.panel_id,
            category_id=new_id,
            author_id=interaction.user.id,
        )
        await interaction.response.send_message(
            "Almost done - choose where the ticket channels live and which role handles them.",
            view=picker,
            ephemeral=True,
        )


class PanelAppearanceModal(discord.ui.Modal):
    """Edit the embed shown on the public request panel."""

    def __init__(self, *, guild_id, panel_id, existing=None, on_saved=None):
        super().__init__(title="Panel Appearance"[:45])
        self.guild_id = guild_id
        self.panel_id = panel_id
        self.on_saved = on_saved

        title_default = str(existing["title"]) if existing and existing["title"] else "Support Centre"
        desc_default = str(existing["description"]) if existing and existing["description"] else (
            "Pick a category below to open a request."
        )
        color_default = "#5865F2"
        if existing and existing["color"]:
            try:
                color_default = "#{:06X}".format(_as_int(existing["color"], 0x5865F2))
            except Exception:
                color_default = "#5865F2"
        footer_default = str(existing["footer"]) if existing and existing["footer"] else ""
        banner_default = str(existing["banner_url"]) if existing and existing["banner_url"] else ""

        self.title_input = discord.ui.TextInput(label="Headline", default=title_default, max_length=200, required=True)
        self.desc_input = discord.ui.TextInput(
            label="Description",
            default=desc_default,
            style=discord.TextStyle.paragraph,
            max_length=1500,
            required=False,
        )
        self.color_input = discord.ui.TextInput(label="Accent colour (hex)", default=color_default, max_length=9, required=False)
        self.footer_input = discord.ui.TextInput(label="Footer text", default=footer_default, max_length=200, required=False)
        self.banner_input = discord.ui.TextInput(label="Banner image URL", default=banner_default, max_length=500, required=False)

        self.add_item(self.title_input)
        self.add_item(self.desc_input)
        self.add_item(self.color_input)
        self.add_item(self.footer_input)
        self.add_item(self.banner_input)

    async def on_submit(self, interaction: discord.Interaction):
        hex_str = (self.color_input.value or "").strip()
        try:
            color = int(hex_str.lstrip("#"), 16)
        except Exception:
            color = 0x5865F2

        await interaction.client.db.execute(
            """UPDATE ticket_panels
               SET title = ?, description = ?, color = ?, footer = ?, banner_url = ?
               WHERE id = ? AND guild_id = ?""",
            (self.title_input.value[:200], self.desc_input.value or "",
             color, self.footer_input.value or "", self.banner_input.value or "",
             self.panel_id, self.guild_id),
        )

        row = await interaction.client.db.fetchone(
            "SELECT * FROM ticket_panels WHERE id = ? AND guild_id = ?",
            (self.panel_id, self.guild_id),
        )
        if row and row["channel_id"] and row["message_id"] and interaction.guild:
            ch = interaction.guild.get_channel(_as_int(row["channel_id"]))
            if isinstance(ch, discord.TextChannel):
                try:
                    msg = await ch.fetch_message(_as_int(row["message_id"]))
                    await msg.edit(embed=_panel_embed(row))
                except (discord.NotFound, discord.HTTPException):
                    pass

        await interaction.response.send_message("Panel appearance updated.", ephemeral=True)
        if self.on_saved:
            await self.on_saved()


class CloseTicketModal(discord.ui.Modal):
    """Collect a close reason and whether to delete the channel."""

    def __init__(self, *, ticket_id, channel_id, opener_id, guild_id):
        super().__init__(title="Close Ticket"[:45])
        self.ticket_id = ticket_id
        self.channel_id = channel_id
        self.opener_id = opener_id
        self.guild_id = guild_id

        self.reason_input = discord.ui.TextInput(
            label="Reason for closing",
            placeholder="Briefly explain why this ticket is being resolved or closed",
            required=False,
            max_length=400,
            style=discord.TextStyle.paragraph,
        )
        self.delete_input = discord.ui.TextInput(
            label="Delete channel after close? (yes / no)",
            default="no",
            max_length=3,
            required=False,
        )
        self.add_item(self.reason_input)
        self.add_item(self.delete_input)

    async def on_submit(self, interaction: discord.Interaction):
        reason = (self.reason_input.value or "").strip()
        delete_flag = (self.delete_input.value or "no").strip().lower().startswith("y")

        # Mark closed in DB
        service = TicketService(interaction.client.db, LoggingService(interaction.client.db))
        await service.set_status(self.channel_id, "closed")

        # Build transcript
        transcript_text = await _build_transcript(interaction.channel)

        # Send to archive channel if configured
        archive_id = await _config_get(interaction.client, self.guild_id, "tickets_transcripts_channel", "")
        archive_sent = False
        if archive_id and archive_id.isdigit() and interaction.guild:
            archive_ch = interaction.guild.get_channel(int(archive_id))
            if isinstance(archive_ch, discord.TextChannel):
                file = discord.File(
                    io.BytesIO(transcript_text.encode("utf-8")),
                    filename="ticket-" + str(self.channel_id) + ".txt",
                )
                opener = interaction.guild.get_member(self.opener_id)
                embed = discord.Embed(
                    title="Archived Ticket Transcript",
                    description=(
                        "Closed by " + interaction.user.mention + "\n"
                        "Opened by " + (opener.mention if opener else "`" + str(self.opener_id) + "`") + "\n"
                        "Reason: " + (reason if reason else "not specified")
                    ),
                    color=0x2B2D31,
                )
                try:
                    await archive_ch.send(embed=embed, file=file)
                    archive_sent = True
                except discord.HTTPException:
                    pass

        # DM the opener a copy + rating prompt
        dm_sent = False
        if interaction.guild:
            opener = interaction.guild.get_member(self.opener_id)
            if opener is not None:
                try:
                    dm_embed = discord.Embed(
                        title="Your ticket has been closed",
                        description=(
                            "Thanks for contacting us in **" + interaction.guild.name + "**.\n"
                            "Reason given: " + (reason if reason else "not specified")
                        ),
                        color=0x5865F2,
                    )
                    dm_file = discord.File(
                        io.BytesIO(transcript_text.encode("utf-8")),
                        filename="ticket-" + str(self.channel_id) + ".txt",
                    )
                    await opener.send(embed=dm_embed, file=dm_file)
                    dm_sent = True
                    rating_view = RatingView(ticket_id=self.ticket_id, guild_id=self.guild_id)
                    rating_embed = discord.Embed(
                        title="How did we do?",
                        description="Rate your support experience from 1 to 5.",
                        color=0x5865F2,
                    )
                    await opener.send(embed=rating_embed, view=rating_view)
                except discord.HTTPException:
                    pass

        # Log the close
        logging_svc = LoggingService(interaction.client.db)
        if interaction.guild:
            await logging_svc.emit(
                interaction.guild, "tickets",
                title="Ticket Closed",
                color=0xED4245,
                fields=[
                    ("Closed by", interaction.user.mention, True),
                    ("Reason", reason or "not specified", False),
                    ("Transcript archived", "yes" if archive_sent else "no", True),
                    ("Opener DM", "yes" if dm_sent else "no", True),
                ],
            )

        # Respond on the channel before deleting (if we're deleting)
        if delete_flag:
            try:
                await interaction.response.send_message("Ticket closed. This channel will be removed in 5 seconds.")
            except discord.HTTPException:
                pass
            await asyncio.sleep(5)
            try:
                await interaction.channel.delete(reason="Ticket closed and deleted")
            except discord.HTTPException:
                pass
            return

        # Otherwise lock the opener's permission and post a closed view
        if interaction.guild:
            opener = interaction.guild.get_member(self.opener_id)
            if opener and isinstance(interaction.channel, discord.TextChannel):
                try:
                    await interaction.channel.set_permissions(opener, send_messages=False)
                except discord.HTTPException:
                    pass

        closed_embed = discord.Embed(
            title="Ticket Closed",
            description=(
                "This ticket has been closed by " + interaction.user.mention + ".\n"
                "Reason: " + (reason if reason else "not specified")
            ),
            color=0xED4245,
        )
        try:
            await interaction.response.send_message(embed=closed_embed, view=TicketClosedView())
        except discord.HTTPException:
            pass


async def _build_transcript(channel) -> str:
    if not isinstance(channel, discord.TextChannel):
        return "(channel unavailable)"
    lines = []
    try:
        async for msg in channel.history(limit=3000, oldest_first=True):
            stamp = msg.created_at.isoformat()
            body = msg.content or ""
            extras = []
            if msg.attachments:
                for att in msg.attachments:
                    extras.append(att.url)
            extra_text = (" [files: " + ", ".join(extras) + "]") if extras else ""
            lines.append("[" + stamp + "] " + str(msg.author) + ": " + body + extra_text)
    except discord.HTTPException:
        return "(failed to fetch messages)"
    return "\n".join(lines) if lines else "(no messages)"


# ---------------------------------------------------------------------------
# Channel + role picker (step two of creating a category)
# ---------------------------------------------------------------------------
class ChannelRolePickerView(discord.ui.View):
    def __init__(self, *, guild_id, panel_id, category_id, author_id):
        super().__init__(timeout=240)
        self.guild_id = guild_id
        self.panel_id = panel_id
        self.category_id = category_id
        self.author_id = author_id
        self.chosen_category = None
        self.chosen_role = None

        cat_select = discord.ui.ChannelSelect(
            placeholder="Where should ticket channels be created?",
            channel_types=[discord.ChannelType.category],
            min_values=1,
            max_values=1,
            row=0,
        )
        cat_select.callback = self._on_cat
        self.add_item(cat_select)

        role_select = discord.ui.RoleSelect(
            placeholder="Which role handles these tickets? (optional)",
            min_values=0,
            max_values=1,
            row=1,
        )
        role_select.callback = self._on_role
        self.add_item(role_select)

        save_btn = discord.ui.Button(label="Save", style=discord.ButtonStyle.success, row=2)
        save_btn.callback = self._on_save
        self.add_item(save_btn)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("This prompt is not for you.", ephemeral=True)
            return False
        return True

    async def _on_cat(self, interaction: discord.Interaction):
        values = (interaction.data or {}).get("values") or []
        if values:
            self.chosen_category = _as_int(values[0])
        await interaction.response.defer()

    async def _on_role(self, interaction: discord.Interaction):
        values = (interaction.data or {}).get("values") or []
        self.chosen_role = _as_int(values[0]) if values else None
        await interaction.response.defer()

    async def _on_save(self, interaction: discord.Interaction):
        await interaction.client.db.execute(
            "UPDATE ticket_categories SET category_id = ?, support_role_id = ? WHERE id = ? AND guild_id = ?",
            (self.chosen_category, self.chosen_role, self.category_id, self.guild_id),
        )
        await _refresh_panel_view(interaction.client, self.guild_id, self.panel_id)
        await interaction.response.edit_message(content="Category saved.", view=None)


# ---------------------------------------------------------------------------
# Category picker used by edit / delete
# ---------------------------------------------------------------------------
class CategoryPickView(discord.ui.View):
    def __init__(self, *, rows, verb, author_id, on_pick):
        super().__init__(timeout=180)
        self.author_id = author_id
        self.on_pick = on_pick
        options = []
        for r in rows[:25]:
            options.append(discord.SelectOption(label=str(r["name"])[:100], value=str(r["id"])))
        select = discord.ui.Select(placeholder="Pick a category to " + verb + "...", options=options)
        select.callback = self._pick
        self.add_item(select)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("This prompt is not for you.", ephemeral=True)
            return False
        return True

    async def _pick(self, interaction: discord.Interaction):
        values = (interaction.data or {}).get("values") or []
        if not values:
            return await interaction.response.send_message("Nothing selected.", ephemeral=True)
        await self.on_pick(interaction, _as_int(values[0]))


# ---------------------------------------------------------------------------
# Transcript archive configuration
# ---------------------------------------------------------------------------
class TranscriptArchiveView(discord.ui.View):
    def __init__(self, *, guild_id, author_id, on_saved=None):
        super().__init__(timeout=240)
        self.guild_id = guild_id
        self.author_id = author_id
        self.on_saved = on_saved

        picker = discord.ui.ChannelSelect(
            placeholder="Pick a channel to archive closed tickets into...",
            channel_types=[discord.ChannelType.text],
            min_values=1,
            max_values=1,
            row=0,
        )
        picker.callback = self._on_pick
        self.add_item(picker)

        disable = discord.ui.Button(label="Disable archiving", style=discord.ButtonStyle.danger, row=1)
        disable.callback = self._on_disable
        self.add_item(disable)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("This prompt is not for you.", ephemeral=True)
            return False
        return True

    async def _on_pick(self, interaction: discord.Interaction):
        values = (interaction.data or {}).get("values") or []
        if not values:
            return await interaction.response.send_message("Nothing selected.", ephemeral=True)
        channel_id = _as_int(values[0])
        await _config_set(interaction.client, self.guild_id, "tickets_transcripts_channel", channel_id)
        await interaction.response.edit_message(
            content="Transcripts will now be archived in <#" + str(channel_id) + ">.",
            view=None,
        )
        if self.on_saved:
            await self.on_saved()

    async def _on_disable(self, interaction: discord.Interaction):
        await _config_set(interaction.client, self.guild_id, "tickets_transcripts_channel", "")
        await interaction.response.edit_message(content="Transcript archiving is now disabled.", view=None)
        if self.on_saved:
            await self.on_saved()


# ---------------------------------------------------------------------------
# Admin console
# ---------------------------------------------------------------------------
class AdminConsoleView(discord.ui.View):
    def __init__(self, *, guild_id, author_id, refresh_cb=None):
        super().__init__(timeout=900)
        self.guild_id = guild_id
        self.author_id = author_id
        self.refresh_cb = refresh_cb

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("This console is not for you.", ephemeral=True)
            return False
        return True

    async def _ensure_panel(self, guild_id):
        row = await self.client_db().fetchone(
            "SELECT * FROM ticket_panels WHERE guild_id = ? ORDER BY id LIMIT 1",
            (guild_id,),
        )
        if row:
            return row
        await self.client_db().execute(
            "INSERT INTO ticket_panels (guild_id, name, title, description) VALUES (?, ?, ?, ?)",
            (guild_id, "default", "Support Centre",
             "Pick a category below to open a request."),
        )
        return await self.client_db().fetchone(
            "SELECT * FROM ticket_panels WHERE guild_id = ? ORDER BY id DESC LIMIT 1",
            (guild_id,),
        )

    @discord.ui.button(label="New Category", style=discord.ButtonStyle.success, row=0)
    async def new_category(self, interaction: discord.Interaction, _b: discord.ui.Button):
        panel = await self._ensure_panel(self.guild_id)
        modal = CategoryModal(guild_id=self.guild_id, panel_id=_as_int(panel["id"]))
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Edit Category", style=discord.ButtonStyle.primary, row=0)
    async def edit_category(self, interaction: discord.Interaction, _b: discord.ui.Button):
        panel = await self._ensure_panel(self.guild_id)
        rows = await self.client_db().fetchall(
            "SELECT * FROM ticket_categories WHERE guild_id = ? AND panel_id = ? ORDER BY id",
            (self.guild_id, _as_int(panel["id"])),
        )
        if not rows:
            return await interaction.response.send_message("No categories yet.", ephemeral=True)

        async def on_pick(inner, category_id):
            cat = await self.client_db().fetchone(
                "SELECT * FROM ticket_categories WHERE id = ? AND guild_id = ?",
                (category_id, self.guild_id),
            )
            if not cat:
                return await inner.response.send_message("Category not found.", ephemeral=True)
            modal = CategoryModal(
                guild_id=self.guild_id,
                panel_id=_as_int(panel["id"]),
                existing=cat,
            )
            await inner.response.send_modal(modal)

        view = CategoryPickView(rows=rows, verb="edit", author_id=interaction.user.id, on_pick=on_pick)
        await interaction.response.send_message("Select a category to edit:", view=view, ephemeral=True)

    @discord.ui.button(label="Delete Category", style=discord.ButtonStyle.danger, row=0)
    async def delete_category(self, interaction: discord.Interaction, _b: discord.ui.Button):
        panel = await self._ensure_panel(self.guild_id)
        rows = await self.client_db().fetchall(
            "SELECT * FROM ticket_categories WHERE guild_id = ? AND panel_id = ? ORDER BY id",
            (self.guild_id, _as_int(panel["id"])),
        )
        if not rows:
            return await interaction.response.send_message("No categories to remove.", ephemeral=True)

        async def on_pick(inner, category_id):
            await self.client_db().execute(
                "DELETE FROM ticket_categories WHERE id = ? AND guild_id = ?",
                (category_id, self.guild_id),
            )
            await _refresh_panel_view(inner.client, self.guild_id, _as_int(panel["id"]))
            await inner.response.send_message("Category removed.", ephemeral=True)

        view = CategoryPickView(rows=rows, verb="remove", author_id=interaction.user.id, on_pick=on_pick)
        await interaction.response.send_message("Select a category to remove:", view=view, ephemeral=True)

    @discord.ui.button(label="Panel Appearance", style=discord.ButtonStyle.secondary, row=1)
    async def appearance(self, interaction: discord.Interaction, _b: discord.ui.Button):
        panel = await self._ensure_panel(self.guild_id)
        modal = PanelAppearanceModal(
            guild_id=self.guild_id,
            panel_id=_as_int(panel["id"]),
            existing=panel,
        )
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Transcript Archive", style=discord.ButtonStyle.secondary, row=1)
    async def transcript_archive(self, interaction: discord.Interaction, _b: discord.ui.Button):
        current = await _config_get(interaction.client, self.guild_id, "tickets_transcripts_channel", "")
        shown = ("<#" + current + ">") if current and current.isdigit() else "not configured"
        embed = discord.Embed(
            title="Transcript Archive",
            description=(
                "Closed tickets produce a text transcript. Choose the channel where "
                "those transcripts should be delivered automatically.\n\n"
                "Current archive channel: " + shown
            ),
            color=0x2B2D31,
        )
        view = TranscriptArchiveView(
            guild_id=self.guild_id,
            author_id=interaction.user.id,
            on_saved=self.refresh_cb,
        )
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @discord.ui.button(label="Category Overview", style=discord.ButtonStyle.secondary, row=1)
    async def overview(self, interaction: discord.Interaction, _b: discord.ui.Button):
        panel = await self._ensure_panel(self.guild_id)
        rows = await self.client_db().fetchall(
            "SELECT * FROM ticket_categories WHERE guild_id = ? AND panel_id = ? ORDER BY id",
            (self.guild_id, _as_int(panel["id"])),
        )
        if not rows:
            return await interaction.response.send_message("No categories configured yet.", ephemeral=True)
        embed = discord.Embed(title="Category Overview", color=0x2B2D31)
        for r in rows:
            cat_ch = None
            role = None
            if interaction.guild:
                if r["category_id"]:
                    cat_ch = interaction.guild.get_channel(_as_int(r["category_id"]))
                if r["support_role_id"]:
                    role = interaction.guild.get_role(_as_int(r["support_role_id"]))
            lines = [
                "Destination: " + (cat_ch.mention if cat_ch else "not set"),
                "Handling role: " + (role.mention if role else "not set"),
                "Channel pattern: " + str(r["naming_template"] or "ticket-{username}"),
                "Priority: " + str(r["button_style"] or "normal"),
            ]
            embed.add_field(name=str(r["name"]), value="\n".join(lines), inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label="Publish Panel", style=discord.ButtonStyle.success, row=2)
    async def publish(self, interaction: discord.Interaction, _b: discord.ui.Button):
        if not isinstance(interaction.channel, discord.TextChannel):
            return await interaction.response.send_message("Post this in a text channel.", ephemeral=True)
        panel = await self._ensure_panel(self.guild_id)
        panel_id = _as_int(panel["id"])
        cats = await self.client_db().fetchall(
            "SELECT * FROM ticket_categories WHERE guild_id = ? AND panel_id = ? ORDER BY id",
            (self.guild_id, panel_id),
        )
        if not cats:
            return await interaction.response.send_message(
                "Add at least one category before publishing.", ephemeral=True,
            )
        embed = _panel_embed(panel)
        view = TicketPanelView(panel_id=panel_id, categories=cats)
        msg = await interaction.channel.send(embed=embed, view=view)
        await self.client_db().execute(
            "UPDATE ticket_panels SET channel_id = ?, message_id = ? WHERE id = ? AND guild_id = ?",
            (interaction.channel.id, msg.id, panel_id, self.guild_id),
        )
        interaction.client.add_view(TicketPanelView(panel_id=panel_id, categories=cats))
        await interaction.response.send_message(
            "Panel published in " + interaction.channel.mention + ".", ephemeral=True,
        )

    # DB access
    bot_ref = None

    def client_db(self):
        return self.bot_ref.db  # type: ignore[union-attr]


# ---------------------------------------------------------------------------
# Public request panel
# ---------------------------------------------------------------------------
class TicketPanelView(discord.ui.View):
    def __init__(self, *, panel_id, categories):
        super().__init__(timeout=None)
        self.panel_id = panel_id
        self.categories = list(categories) if categories else []

        options = []
        for c in self.categories[:25]:
            opt = {
                "label": str(c["name"])[:100],
                "value": str(c["id"]),
            }
            wm = c["welcome_message"] if c["welcome_message"] else ""
            if wm:
                opt["description"] = wm[:100]
            em = c["emoji"] if c["emoji"] else ""
            if em:
                opt["emoji"] = em
            options.append(discord.SelectOption(**opt))

        if options:
            sel = discord.ui.Select(
                placeholder="Select a type of request...",
                options=options,
                custom_id="ticket_panel:" + str(panel_id),
            )
            sel.callback = self._on_select
            self.add_item(sel)
        else:
            placeholder_opts = [discord.SelectOption(label="No categories available", value="_")]
            sel = discord.ui.Select(
                placeholder="No categories available",
                options=placeholder_opts,
                disabled=True,
                custom_id="ticket_panel_empty:" + str(panel_id),
            )
            self.add_item(sel)

    async def _on_select(self, interaction: discord.Interaction):
        values = (interaction.data or {}).get("values") or []
        if not values:
            return await interaction.response.send_message("Nothing selected.", ephemeral=True)
        try:
            category_id = int(values[0])
        except ValueError:
            return await interaction.response.send_message("Invalid selection.", ephemeral=True)

        row = await interaction.client.db.fetchone(
            "SELECT * FROM ticket_categories WHERE id = ?",
            (category_id,),
        )
        if row is None:
            return await interaction.response.send_message("That category has been removed.", ephemeral=True)

        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        user = interaction.user
        if guild is None:
            return await interaction.followup.send("This only works inside a server.", ephemeral=True)

        service = TicketService(interaction.client.db, LoggingService(interaction.client.db))
        # NOTE: pass guild so orphaned records auto-close
        open_count = await service.count_open(guild.id, user.id, guild=guild)
        limit = _as_int(row["max_open_per_user"], 1) or 1
        if open_count >= limit:
            return await interaction.followup.send(
                "You currently have " + str(open_count) + " open ticket(s). Please close one first.",
                ephemeral=True,
            )

        parent_cat = None
        if row["category_id"]:
            ch = guild.get_channel(_as_int(row["category_id"]))
            if isinstance(ch, discord.CategoryChannel):
                parent_cat = ch

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            user: discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                attach_files=True,
                read_message_history=True,
            ),
            guild.me: discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                manage_channels=True,
                read_message_history=True,
            ),
        }
        support_role = guild.get_role(_as_int(row["support_role_id"])) if row["support_role_id"] else None
        if support_role:
            overwrites[support_role] = discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                manage_channels=True,
                read_message_history=True,
            )

        template = row["naming_template"] or "ticket-{username}"
        channel_name = template.replace("{username}", user.name.lower()).replace("{user_id}", str(user.id))[:95]

        try:
            channel = await guild.create_text_channel(
                name=channel_name,
                category=parent_cat,
                overwrites=overwrites,
                topic="Ticket owner: " + str(user) + " (" + str(user.id) + ")",
                reason="Ticket opened by " + str(user),
            )
        except discord.HTTPException as exc:
            return await interaction.followup.send("Could not create ticket channel: " + str(exc), ephemeral=True)

        ticket_id = await service.create_ticket_record(
            guild.id, channel.id, _as_int(row["category_id"]), user.id,
        )

        priority_tag = str(row["button_style"] or "normal").upper()
        embed = discord.Embed(
            title=str(row["name"]) + " - Ticket #" + str(ticket_id),
            description=row["welcome_message"] or ("Hello " + user.mention + ", a team member will be with you shortly."),
            color=0x5865F2,
        )
        embed.add_field(name="Opened by", value=user.mention, inline=True)
        embed.add_field(name="Priority", value=priority_tag, inline=True)
        if support_role:
            embed.add_field(name="Handling role", value=support_role.mention, inline=True)
        embed.set_footer(text="Use the buttons below to manage this ticket.")

        control = TicketControlView()
        await channel.send(
            content=user.mention + ((" " + support_role.mention) if support_role else ""),
            embed=embed,
            view=control,
        )

        logging_svc = LoggingService(interaction.client.db)
        await logging_svc.emit(
            guild, "tickets",
            title="Ticket Opened",
            color=0x57F287,
            fields=[
                ("User", user.mention, True),
                ("Channel", channel.mention, True),
                ("Category", str(row["name"]), True),
                ("Priority", priority_tag, True),
            ],
        )

        await interaction.followup.send("Ticket created: " + channel.mention, ephemeral=True)


# ---------------------------------------------------------------------------
# In-ticket controls (open state)
# ---------------------------------------------------------------------------
class TicketControlView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Claim", style=discord.ButtonStyle.success, custom_id="ticket:claim")
    async def claim(self, interaction: discord.Interaction, _b: discord.ui.Button):
        if not _member_is_staff(interaction.user):
            return await interaction.response.send_message("Only staff can claim tickets.", ephemeral=True)
        service = TicketService(interaction.client.db, LoggingService(interaction.client.db))
        await service.set_claimed(interaction.channel_id, interaction.user.id)
        await interaction.response.send_message("Claimed by " + interaction.user.mention + ".")

    @discord.ui.button(label="Add Member", style=discord.ButtonStyle.secondary, custom_id="ticket:adduser")
    async def add_user(self, interaction: discord.Interaction, _b: discord.ui.Button):
        if not _member_is_staff(interaction.user):
            return await interaction.response.send_message("Only staff can add members.", ephemeral=True)
        picker = UserPickerView(author_id=interaction.user.id)
        await interaction.response.send_message("Choose a member to add:", view=picker, ephemeral=True)

    @discord.ui.button(label="Transcript", style=discord.ButtonStyle.secondary, custom_id="ticket:transcript")
    async def transcript(self, interaction: discord.Interaction, _b: discord.ui.Button):
        if not _member_is_staff(interaction.user):
            return await interaction.response.send_message("Only staff can generate transcripts.", ephemeral=True)
        await interaction.response.defer(ephemeral=True)
        text = await _build_transcript(interaction.channel)
        file = discord.File(
            io.BytesIO(text.encode("utf-8")),
            filename="ticket-" + str(interaction.channel_id) + ".txt",
        )
        await interaction.followup.send("Transcript attached.", file=file, ephemeral=True)

    @discord.ui.button(label="Close", style=discord.ButtonStyle.danger, custom_id="ticket:close")
    async def close(self, interaction: discord.Interaction, _b: discord.ui.Button):
        if not _member_is_staff(interaction.user):
            return await interaction.response.send_message("Only staff can close tickets.", ephemeral=True)

        row = await interaction.client.db.fetchone(
            "SELECT * FROM tickets WHERE channel_id = ?",
            (interaction.channel_id,),
        )
        ticket_id = _as_int(row["id"]) if row else 0
        opener_id = _as_int(row["user_id"]) if row else 0
        guild_id = interaction.guild_id or 0

        modal = CloseTicketModal(
            ticket_id=ticket_id,
            channel_id=interaction.channel_id,
            opener_id=opener_id,
            guild_id=guild_id,
        )
        await interaction.response.send_modal(modal)


class UserPickerView(discord.ui.View):
    def __init__(self, *, author_id):
        super().__init__(timeout=120)
        self.author_id = author_id
        picker = discord.ui.UserSelect(placeholder="Select a member...", min_values=1, max_values=1)
        picker.callback = self._on_pick
        self.add_item(picker)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("This prompt is not for you.", ephemeral=True)
            return False
        return True

    async def _on_pick(self, interaction: discord.Interaction):
        values = (interaction.data or {}).get("values") or []
        if not values:
            return await interaction.response.send_message("Nothing selected.", ephemeral=True)
        member_id = _as_int(values[0])
        if not isinstance(interaction.channel, discord.TextChannel):
            return await interaction.response.send_message("Not a text channel.", ephemeral=True)
        guild = interaction.guild
        if guild is None:
            return
        member = guild.get_member(member_id)
        if member is None:
            return await interaction.response.send_message("Member not found.", ephemeral=True)
        try:
            await interaction.channel.set_permissions(
                member, view_channel=True, send_messages=True, read_message_history=True,
            )
        except discord.HTTPException as exc:
            return await interaction.response.send_message("Failed: " + str(exc), ephemeral=True)
        await interaction.response.send_message("Added " + member.mention + " to this ticket.", ephemeral=True)


# ---------------------------------------------------------------------------
# In-ticket controls (closed state)
# ---------------------------------------------------------------------------
class TicketClosedView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Reopen", style=discord.ButtonStyle.primary, custom_id="ticket:reopen")
    async def reopen(self, interaction: discord.Interaction, _b: discord.ui.Button):
        if not _member_is_staff(interaction.user):
            return await interaction.response.send_message("Only staff can reopen tickets.", ephemeral=True)
        service = TicketService(interaction.client.db, LoggingService(interaction.client.db))
        await service.set_status(interaction.channel_id, "open")

        row = await interaction.client.db.fetchone(
            "SELECT * FROM tickets WHERE channel_id = ?",
            (interaction.channel_id,),
        )
        if row and interaction.guild:
            opener = interaction.guild.get_member(_as_int(row["user_id"]))
            if opener and isinstance(interaction.channel, discord.TextChannel):
                try:
                    await interaction.channel.set_permissions(opener, send_messages=True, view_channel=True)
                except discord.HTTPException:
                    pass

        await interaction.response.send_message("Ticket reopened.", view=TicketControlView())


# ---------------------------------------------------------------------------
# Rating prompt (DM)
# ---------------------------------------------------------------------------
class RatingView(discord.ui.View):
    def __init__(self, *, ticket_id, guild_id):
        super().__init__(timeout=600)
        self.ticket_id = ticket_id
        self.guild_id = guild_id

        select = discord.ui.Select(
            placeholder="Rate 1 to 5...",
            options=[
                discord.SelectOption(label="1 - Poor", value="1"),
                discord.SelectOption(label="2 - Below expectations", value="2"),
                discord.SelectOption(label="3 - Average", value="3"),
                discord.SelectOption(label="4 - Good", value="4"),
                discord.SelectOption(label="5 - Excellent", value="5"),
            ],
        )
        select.callback = self._on_rate
        self.add_item(select)

    async def _on_rate(self, interaction: discord.Interaction):
        values = (interaction.data or {}).get("values") or []
        if not values:
            return await interaction.response.send_message("Nothing selected.", ephemeral=True)
        rating = _as_int(values[0], 3)
        await interaction.client.db.execute(
            """INSERT INTO ticket_ratings
               (guild_id, ticket_id, user_id, rating, comment, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (self.guild_id, self.ticket_id, interaction.user.id, rating, "", _now()),
        )
        embed = discord.Embed(
            title="Thanks for the feedback",
            description="Your rating of " + str(rating) + "/5 has been recorded.",
            color=0x57F287,
        )
        await interaction.response.edit_message(embed=embed, view=None)


# ---------------------------------------------------------------------------
# Refresh helper
# ---------------------------------------------------------------------------
async def _refresh_panel_view(bot, guild_id, panel_id):
    try:
        cats = await bot.db.fetchall(
            "SELECT * FROM ticket_categories WHERE guild_id = ? AND panel_id = ? ORDER BY id",
            (guild_id, panel_id),
        )
        bot.add_view(TicketPanelView(panel_id=panel_id, categories=cats))

        row = await bot.db.fetchone(
            "SELECT channel_id, message_id FROM ticket_panels WHERE id = ? AND guild_id = ?",
            (panel_id, guild_id),
        )
        if not row or not row["channel_id"] or not row["message_id"]:
            return
        guild = bot.get_guild(guild_id)
        if guild is None:
            return
        ch = guild.get_channel(_as_int(row["channel_id"]))
        if not isinstance(ch, discord.TextChannel):
            return
        try:
            msg = await ch.fetch_message(_as_int(row["message_id"]))
            await msg.edit(view=TicketPanelView(panel_id=panel_id, categories=cats))
        except (discord.NotFound, discord.HTTPException):
            pass
    except Exception:
        pass


# ---------------------------------------------------------------------------
# The cog
# ---------------------------------------------------------------------------
class Tickets(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.service = TicketService(bot.db, LoggingService(bot.db))  # type: ignore[attr-defined]

    @commands.Cog.listener()
    async def on_ready(self):
        AdminConsoleView.bot_ref = self.bot  # type: ignore[attr-defined]
        try:
            panels = await self.bot.db.fetchall("SELECT * FROM ticket_panels")  # type: ignore[attr-defined]
        except Exception:
            panels = []
        for p in panels:
            try:
                gid = _as_int(p["guild_id"])
                pid = _as_int(p["id"])
                cats = await self.bot.db.fetchall(  # type: ignore[attr-defined]
                    "SELECT * FROM ticket_categories WHERE guild_id = ? AND panel_id = ? ORDER BY id",
                    (gid, pid),
                )
                self.bot.add_view(TicketPanelView(panel_id=pid, categories=cats))
            except Exception:
                continue
        self.bot.add_view(TicketControlView())
        self.bot.add_view(TicketClosedView())
        await self._sweep_orphaned_tickets()

    async def _sweep_orphaned_tickets(self) -> None:
        """Close DB records for tickets whose channels no longer exist."""
        total = 0
        for guild in self.bot.guilds:
            try:
                rows = await self.bot.db.fetchall(  # type: ignore[attr-defined]
                    "SELECT channel_id FROM tickets WHERE guild_id = ? AND status = 'open'",
                    (guild.id,),
                )
            except Exception:
                continue
            orphans = []
            for r in rows:
                try:
                    cid = int(r["channel_id"])
                except (TypeError, ValueError):
                    continue
                if guild.get_channel(cid) is None:
                    orphans.append(cid)
            if not orphans:
                continue
            now_ts = int(_time.time())
            for cid in orphans:
                try:
                    await self.bot.db.execute(  # type: ignore[attr-defined]
                        "UPDATE tickets SET status = 'closed', closed_at = ? "
                        "WHERE channel_id = ? AND status = 'open'",
                        (now_ts, cid),
                    )
                except Exception:
                    pass
            total += len(orphans)
        if total:
            log.info("Ticket sweep: closed %d orphaned ticket record(s).", total)

    async def _open_console(self, interaction: discord.Interaction):
        if interaction.guild_id is None:
            return await interaction.response.send_message("This command only works inside a server.", ephemeral=True)

        row = await self.bot.db.fetchone(  # type: ignore[attr-defined]
            "SELECT * FROM ticket_panels WHERE guild_id = ? ORDER BY id LIMIT 1",
            (interaction.guild_id,),
        )
        if row is None:
            await self.bot.db.execute(  # type: ignore[attr-defined]
                "INSERT INTO ticket_panels (guild_id, name, title, description) VALUES (?, ?, ?, ?)",
                (interaction.guild_id, "default", "Support Centre",
                 "Pick a category below to open a request."),
            )

        cats = await self.bot.db.fetchall(  # type: ignore[attr-defined]
            "SELECT * FROM ticket_categories WHERE guild_id = ?",
            (interaction.guild_id,),
        )

        total_row = await self.bot.db.fetchone(  # type: ignore[attr-defined]
            "SELECT COUNT(*) AS c FROM tickets WHERE guild_id = ?",
            (interaction.guild_id,),
        )
        open_row = await self.bot.db.fetchone(  # type: ignore[attr-defined]
            "SELECT COUNT(*) AS c FROM tickets WHERE guild_id = ? AND status = 'open'",
            (interaction.guild_id,),
        )
        closed_row = await self.bot.db.fetchone(  # type: ignore[attr-defined]
            "SELECT COUNT(*) AS c FROM tickets WHERE guild_id = ? AND status = 'closed'",
            (interaction.guild_id,),
        )
        avg_row = await self.bot.db.fetchone(  # type: ignore[attr-defined]
            "SELECT AVG(rating) AS a FROM ticket_ratings WHERE guild_id = ?",
            (interaction.guild_id,),
        )
        avg_val = avg_row["a"] if avg_row and avg_row["a"] is not None else None
        avg_text = ("{:.1f} / 5".format(avg_val) if avg_val is not None else "no ratings yet")

        archive_id = await _config_get(self.bot, interaction.guild_id, "tickets_transcripts_channel", "")
        archive_text = ("<#" + archive_id + ">") if archive_id and archive_id.isdigit() else "not configured"

        stats = {
            "total": _as_int(total_row["c"] if total_row else 0),
            "open": _as_int(open_row["c"] if open_row else 0),
            "closed": _as_int(closed_row["c"] if closed_row else 0),
            "avg_rating": avg_text,
        }

        embed = _dashboard_embed(
            self.bot.config.bot_name,  # type: ignore[attr-defined]
            len(cats),
            stats,
            archive_text,
        )

        async def refresh():
            try:
                if interaction.guild_id is None:
                    return
                c = await self.bot.db.fetchall(  # type: ignore[attr-defined]
                    "SELECT * FROM ticket_categories WHERE guild_id = ?",
                    (interaction.guild_id,),
                )
                a = await _config_get(self.bot, interaction.guild_id, "tickets_transcripts_channel", "")
                a_text = ("<#" + a + ">") if a and a.isdigit() else "not configured"
                new_embed = _dashboard_embed(
                    self.bot.config.bot_name, len(c), stats, a_text,  # type: ignore[attr-defined]
                )
                await interaction.edit_original_response(embed=new_embed)
            except Exception:
                pass

        view = AdminConsoleView(
            guild_id=interaction.guild_id,
            author_id=interaction.user.id,
            refresh_cb=refresh,
        )
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @app_commands.command(name="ticket-panel", description="Open the support operations console.")
    @is_guild_admin()
    async def ticket_panel(self, interaction: discord.Interaction):
        await self._open_console(interaction)

    @app_commands.command(name="tickets-config", description="Alias of /ticket-panel.")
    @is_guild_admin()
    async def tickets_config(self, interaction: discord.Interaction):
        await self._open_console(interaction)

    @app_commands.command(name="ticket", description="Short info about the ticket system.")
    async def ticket(self, interaction: discord.Interaction):
        await interaction.response.send_message(
            "Staff can manage the system with `/ticket-panel`. Users open tickets from the public panel.",
            ephemeral=True,
        )

    @app_commands.command(name="ticket-add", description="Add a member to the current ticket.")
    @is_moderator()
    async def ticket_add(self, interaction: discord.Interaction, member: discord.Member):
        if not isinstance(interaction.channel, discord.TextChannel):
            return
        await interaction.channel.set_permissions(
            member, view_channel=True, send_messages=True, read_message_history=True,
        )
        await interaction.response.send_message("Added " + member.mention + ".", ephemeral=True)

    @app_commands.command(name="ticket-remove", description="Remove a member from the current ticket.")
    @is_moderator()
    async def ticket_remove(self, interaction: discord.Interaction, member: discord.Member):
        if not isinstance(interaction.channel, discord.TextChannel):
            return
        await interaction.channel.set_permissions(member, overwrite=None)
        await interaction.response.send_message("Removed " + member.mention + ".", ephemeral=True)

    @app_commands.command(name="ticket-claim", description="Claim the current ticket.")
    @is_moderator()
    async def ticket_claim(self, interaction: discord.Interaction):
        if interaction.channel_id is None:
            return
        await self.service.set_claimed(interaction.channel_id, interaction.user.id)
        await interaction.response.send_message("Claimed by " + interaction.user.mention + ".")

    @app_commands.command(name="ticket-close", description="Close the current ticket.")
    @is_moderator()
    async def ticket_close(self, interaction: discord.Interaction):
        row = await self.bot.db.fetchone(  # type: ignore[attr-defined]
            "SELECT * FROM tickets WHERE channel_id = ?",
            (interaction.channel_id,),
        )
        ticket_id = _as_int(row["id"]) if row else 0
        opener_id = _as_int(row["user_id"]) if row else 0
        modal = CloseTicketModal(
            ticket_id=ticket_id,
            channel_id=interaction.channel_id,
            opener_id=opener_id,
            guild_id=interaction.guild_id or 0,
        )
        await interaction.response.send_modal(modal)

    @app_commands.command(name="ticket-reopen", description="Reopen the current ticket.")
    @is_moderator()
    async def ticket_reopen(self, interaction: discord.Interaction):
        if interaction.channel_id is None:
            return
        await self.service.set_status(interaction.channel_id, "open")
        await interaction.response.send_message("Ticket reopened.")

    @app_commands.command(name="ticket-delete", description="Delete the current ticket channel.")
    @is_moderator()
    async def ticket_delete(self, interaction: discord.Interaction):
        if not isinstance(interaction.channel, discord.TextChannel):
            return
        await self.service.delete_ticket(interaction.channel.id)
        await interaction.response.send_message("Removing channel...")
        try:
            await interaction.channel.delete(reason="Ticket deleted by " + str(interaction.user))
        except discord.HTTPException:
            pass

    @app_commands.command(name="ticket-rename", description="Rename the current ticket channel.")
    @is_moderator()
    async def ticket_rename(self, interaction: discord.Interaction, name: str):
        if isinstance(interaction.channel, discord.TextChannel):
            await interaction.channel.edit(name=name[:95])
            await interaction.response.send_message("Renamed to " + name + ".", ephemeral=True)

    @app_commands.command(name="ticket-transcript", description="Generate a transcript of this ticket.")
    @is_moderator()
    async def ticket_transcript(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        text = await _build_transcript(interaction.channel)
        file = discord.File(
            io.BytesIO(text.encode("utf-8")),
            filename="ticket-" + str(interaction.channel_id) + ".txt",
        )
        await interaction.followup.send("Transcript:", file=file, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Tickets(bot))
