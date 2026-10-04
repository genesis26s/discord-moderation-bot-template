"""Interactive configuration panel — schema-driven, all settings editable."""
from __future__ import annotations

from typing import Any, Optional

import discord

from bot.services.config_service import ConfigService
from bot.services.security_service import SecurityService


# ---------------------------------------------------------------------------
# Category list shown on the home panel
# ---------------------------------------------------------------------------
CATEGORIES: list[tuple[str, str, str]] = [
    ("security",     "Security Overview", "View overall security status"),
    ("moderation",   "Moderation",        "Moderation defaults"),
    ("tickets",      "Tickets",           "Ticket system"),
    ("welcome",      "Welcome & Goodbye", "Join / leave messages"),
    ("logging",      "Logging",           "Log channel routing"),
    ("antispam",     "Anti-Spam",         "Message spam protection"),
    ("antiraid",     "Anti-Raid",         "Mass join protection"),
    ("antinuke",     "Anti-Nuke",         "Destructive action protection"),
    ("serverwatch",  "Server Watch",      "Continuous monitoring"),
    ("automod",      "AutoMod",           "Word / link filtering"),
    ("roles",        "Roles",             "Staff & admin roles"),
    ("bot",          "Bot Settings",      "Identity & presence"),
]


# ---------------------------------------------------------------------------
# Schema — every configurable setting in every category
# ---------------------------------------------------------------------------
SCHEMA: dict[str, dict[str, Any]] = {
    "antispam": {
        "title": "Anti-Spam",
        "description": "Protects against message spam, duplicate messages, and mention floods.",
        "settings": [
            {"key": "antispam_enabled",   "label": "Enabled",              "type": "bool"},
            {"key": "antispam_msgs",      "label": "Messages per window",  "type": "int"},
            {"key": "antispam_window",    "label": "Window (seconds)",     "type": "int"},
            {"key": "antispam_dupes",     "label": "Duplicate limit",      "type": "int"},
            {"key": "antispam_mentions",  "label": "Mentions per message", "type": "int"},
            {"key": "antispam_action",    "label": "Action",               "type": "choice",
             "choices": ["warn", "delete", "timeout", "kick", "ban"]},
            {"key": "antispam_timeout",   "label": "Timeout duration (s)", "type": "int"},
        ],
    },
    "antiraid": {
        "title": "Anti-Raid",
        "description": "Protects against mass joins and coordinated raids.",
        "settings": [
            {"key": "antiraid_enabled",       "label": "Enabled",                       "type": "bool"},
            {"key": "antiraid_joins",         "label": "Join threshold",                "type": "int"},
            {"key": "antiraid_window",        "label": "Window (seconds)",              "type": "int"},
            {"key": "antiraid_min_age_days",  "label": "Minimum account age (days)",    "type": "int"},
            {"key": "antiraid_action",        "label": "Action",                        "type": "choice",
             "choices": ["alert", "lockdown", "kick", "ban"]},
            {"key": "antiraid_alert_channel", "label": "Alert channel",                 "type": "channel"},
        ],
    },
    "antinuke": {
        "title": "Anti-Nuke",
        "description": "Protects against destructive admin actions. Uses audit logs to identify the executor.",
        "settings": [
            {"key": "antinuke_enabled",         "label": "Enabled",                     "type": "bool"},
            {"key": "antinuke_channel_delete",  "label": "Channel delete threshold",    "type": "int"},
            {"key": "antinuke_role_delete",     "label": "Role delete threshold",       "type": "int"},
            {"key": "antinuke_ban_count",       "label": "Ban spike threshold",         "type": "int"},
            {"key": "antinuke_kick_count",      "label": "Kick spike threshold",        "type": "int"},
            {"key": "antinuke_webhook",         "label": "Webhook create threshold",    "type": "int"},
            {"key": "antinuke_action",          "label": "Action",                      "type": "choice",
             "choices": ["warn", "strip", "kick", "ban"]},
            {"key": "antinuke_alert_channel",   "label": "Alert channel",               "type": "channel"},
        ],
    },
    "automod": {
        "title": "AutoMod",
        "description": "Automatic content filtering. Blacklisted words are managed via /automod-word-add.",
        "settings": [
            {"key": "automod_enabled",  "label": "Enabled",                 "type": "bool"},
            {"key": "automod_invites",  "label": "Block Discord invites",   "type": "bool"},
            {"key": "automod_links",    "label": "Block all links",         "type": "bool"},
            {"key": "automod_caps",     "label": "Caps threshold (%)",      "type": "int"},
            {"key": "automod_repeat",   "label": "Repeated chars threshold","type": "int"},
            {"key": "automod_action",   "label": "Action",                  "type": "choice",
             "choices": ["delete", "timeout", "kick", "ban"]},
        ],
    },
    "serverwatch": {
        "title": "Server Watch",
        "description": "Continuous monitoring of suspicious server activity.",
        "settings": [
            {"key": "serverwatch_enabled", "label": "Enabled",       "type": "bool"},
            {"key": "serverwatch_channel", "label": "Alert channel", "type": "channel"},
        ],
    },
    "welcome": {
        "title": "Welcome & Goodbye",
        "description": "Configure join and leave messages. Use /welcome-test and /goodbye-test to preview.",
        "settings": [
            {"key": "welcome_enabled",  "label": "Welcome enabled",  "type": "bool"},
            {"key": "welcome_channel",  "label": "Welcome channel",  "type": "channel"},
            {"key": "welcome_message",  "label": "Welcome message",  "type": "str",
             "hint": "Vars: {user} {username} {server} {member_count} {user_id}"},
            {"key": "welcome_embed",    "label": "Send as embed",    "type": "bool"},
            {"key": "goodbye_enabled",  "label": "Goodbye enabled",  "type": "bool"},
            {"key": "goodbye_channel",  "label": "Goodbye channel",  "type": "channel"},
            {"key": "goodbye_message",  "label": "Goodbye message",  "type": "str",
             "hint": "Same variables as welcome"},
        ],
    },
    "logging": {
        "title": "Logging",
        "description": "Route each type of event to a channel. Leave blank to disable a category.",
        "settings": [
            {"key": "log_mod",      "label": "Moderation logs", "type": "channel"},
            {"key": "log_messages", "label": "Message logs",    "type": "channel"},
            {"key": "log_server",   "label": "Server logs",     "type": "channel"},
            {"key": "log_members",  "label": "Member logs",     "type": "channel"},
            {"key": "log_security", "label": "Security logs",   "type": "channel"},
            {"key": "log_tickets",  "label": "Ticket logs",     "type": "channel"},
        ],
    },
    "tickets": {
        "title": "Tickets",
        "description": "Ticket system settings. Create panels with /ticket-panel.",
        "settings": [
            {"key": "tickets_enabled",              "label": "Enabled",                "type": "bool"},
            {"key": "tickets_transcripts_channel",  "label": "Transcript channel",     "type": "channel"},
            {"key": "tickets_ratings_enabled",      "label": "Ratings enabled",        "type": "bool"},
        ],
    },
    "moderation": {
        "title": "Moderation",
        "description": "Moderation defaults.",
        "settings": [
            {"key": "mod_dm_users",        "label": "DM users on action",       "type": "bool"},
            {"key": "mod_default_timeout", "label": "Default timeout (seconds)", "type": "int"},
        ],
    },
    "roles": {
        "title": "Roles",
        "description": "Roles are managed with dedicated commands.",
        "settings": [],
        "hint": "Use `/add-staff-role`, `/add-admin-role`, `/remove-staff-role`, `/trust-user`, `/untrust-user`.",
    },
    "bot": {
        "title": "Bot Settings",
        "description": "Bot identity is configured via `.env` on the host.",
        "settings": [],
        "hint": "Edit BOT_NAME, BOT_STATUS, BOT_ACTIVITY_* in .env, then restart the process.",
    },
    "security": {
        "title": "Security Overview",
        "description": "Configure each security system from its own category.",
        "settings": [],
        "hint": "Pick Anti-Spam, Anti-Raid, Anti-Nuke, AutoMod, or Server Watch from the main dropdown.",
    },
}


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------
def _status_line(enabled: bool) -> str:
    return "🟢 Enabled" if enabled else "🔴 Disabled"


def _fmt_value(value: str, kind: str, guild: discord.Guild | None) -> str:
    if kind == "bool":
        return "🟢 On" if (value or "").lower() == "true" else "🔴 Off"
    if kind == "channel":
        if value and value.isdigit() and guild:
            ch = guild.get_channel(int(value))
            return ch.mention if ch else "⚠️ *deleted channel*"
        return "— not set —"
    if not value:
        return "— not set —"
    return f"`{value}`"


# ---------------------------------------------------------------------------
# Home panel
# ---------------------------------------------------------------------------
def build_home_embed(bot_name: str, statuses: dict[str, bool], incident_count: int) -> discord.Embed:
    embed = discord.Embed(
        title=f"🛡️ {bot_name} — Control Center",
        description="Use the dropdown below to configure any system.",
        color=0x5865F2,
    )
    embed.add_field(
        name="Security Systems",
        value=(
            f"Anti-Nuke: {_status_line(statuses['antinuke'])}\n"
            f"Anti-Raid: {_status_line(statuses['antiraid'])}\n"
            f"Anti-Spam: {_status_line(statuses['antispam'])}\n"
            f"AutoMod: {_status_line(statuses['automod'])}\n"
            f"Server Watch: {_status_line(statuses['serverwatch'])}"
        ),
        inline=False,
    )
    embed.add_field(
        name="Community",
        value=(
            f"Welcome: {_status_line(statuses['welcome'])}\n"
            f"Tickets: {_status_line(statuses['tickets'])}\n"
            f"Lockdown Active: {_status_line(statuses['lockdown'])}"
        ),
        inline=False,
    )
    embed.add_field(name="Recent Threats", value=f"`{incident_count}`", inline=True)
    embed.add_field(name="Security Level", value="`HIGH`", inline=True)
    return embed


# ---------------------------------------------------------------------------
# Category embed builder
# ---------------------------------------------------------------------------
def _build_category_embed(category: str, guild: discord.Guild | None, settings: dict[str, str]) -> discord.Embed:
    schema = SCHEMA[category]
    embed = discord.Embed(
        title=f"⚙️ {schema['title']}",
        description=schema["description"],
        color=0x5865F2,
    )
    if schema["settings"]:
        lines = []
        for s in schema["settings"]:
            raw = settings.get(s["key"], "")
            lines.append(f"**{s['label']}** — {_fmt_value(raw, s['type'], guild)}")
        text = "\n".join(lines)
        # split if too long
        if len(text) > 1024:
            text = text[:1020] + "…"
        embed.add_field(name="Settings", value=text, inline=False)
    if schema.get("hint"):
        embed.add_field(name="Note", value=schema["hint"], inline=False)
    embed.set_footer(text="Select a setting below to edit it.")
    return embed


# ---------------------------------------------------------------------------
# Home view (dropdown + configure button)
# ---------------------------------------------------------------------------
class HomeView(discord.ui.View):
    def __init__(self, *, author_id: int, config: ConfigService, security: SecurityService) -> None:
        super().__init__(timeout=300)
        self.author_id = author_id
        self.config = config
        self.security = security

        options = [
            discord.SelectOption(label=label, value=key, description=desc)
            for key, label, desc in CATEGORIES
        ]
        select: discord.ui.Select = discord.ui.Select(
            placeholder="Select a category to configure…",
            options=options,
            custom_id="panel:home_cat",
            row=0,
        )
        select.callback = self._on_select
        self.add_item(select)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("This panel is not for you.", ephemeral=True)
            return False
        return True

    async def _on_select(self, interaction: discord.Interaction) -> None:
        category = interaction.data["values"][0]  # type: ignore[index]
        gid = interaction.guild_id
        if gid is None or interaction.guild is None:
            return await interaction.response.send_message("Guild only.", ephemeral=True)
        settings = await self.config.all(gid)
        embed = _build_category_embed(category, interaction.guild, settings)
        view = CategoryView(category=category, config=self.config, author_id=interaction.user.id)
        await interaction.response.edit_message(embed=embed, view=view)


# ---------------------------------------------------------------------------
# Category editor
# ---------------------------------------------------------------------------
class CategoryView(discord.ui.View):
    def __init__(self, *, category: str, config: ConfigService, author_id: int) -> None:
        super().__init__(timeout=300)
        self.category = category
        self.config = config
        self.author_id = author_id

        schema = SCHEMA[category]
        options = [
            discord.SelectOption(
                label=s["label"][:100],
                value=s["key"],
                description=(f"Type_id: {s['type']}" + (f"=f · {s['hint']}" if" s.get("hint") else ""))[:100panel],
            )
            for s in schema["settings"][:25]
        ]
        if options:
            select: discord.ui.Select = discord.ui.Select(
                placeholder="Choose a setting to edit…",
                options=options,
                custom:edit:{category}",
                row=0,
            )
            select.callback = self._on_edit
            self.add_item(select)
        else:
            placeholder_select: discord.ui.Select = discord.ui.Select(
                placeholder="No editable settings in this category",
                options=[discord.SelectOption(label="—", value="_none")],
                disabled=True,
                row=0,
            )
            self.add_item(placeholder_select)

        back = discord.ui.Button(label="← Back to panel", style=discord.ButtonStyle.secondary, row=1)
        back.callback = self._on_back
        self.add_item(back)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("Not your session.", ephemeral=True)
            return False
        return True

    async def _on_back(self, interaction: discord.Interaction) -> None:
        # Rebuild home view from the panel cog's status logic
        gid = interaction.guild_id
        if gid is None or interaction.guild is None:
            return await interaction.response.send_message("Guild only.", ephemeral=True)
        statuses = {
            "antinuke":    await self.config.get_bool(gid, "antinuke_enabled"),
            "antiraid":    await self.config.get_bool(gid, "antiraid_enabled"),
            "antispam":    await self.config.get_bool(gid, "antispam_enabled"),
            "automod":     await self.config.get_bool(gid, "automod_enabled"),
            "serverwatch": await self.config.get_bool(gid, "serverwatch_enabled"),
            "welcome":     await self.config.get_bool(gid, "welcome_enabled"),
            "tickets":     await self.config.get_bool(gid, "tickets_enabled"),
            "lockdown":    await self.config.get_bool(gid, "lockdown_active"),
        }
        incident_count = 0  # cheap default — home status refresh
        bot_name = getattr(interaction.client, "config", None)
        bot_name = bot_name.bot_name if bot_name else "Security Bot"
        embed = build_home_embed(bot_name, statuses, incident_count)
        view = HomeView(author_id=interaction.user.id, config=self.config, security=None)  # type: ignore[arg-type]
        await interaction.response.edit_message(embed=embed, view=view)

    async def _on_edit(self, interaction: discord.Interaction) -> None:
        key = interaction.data["values"][0]  # type: ignore[index]
        setting = next((s for s in SCHEMA[self.category]["settings"] if s["key"] == key), None)
        if setting is None:
            return await interaction.response.send_message("Unknown setting.", ephemeral=True)

        gid = interaction.guild_id
        if gid is None or interaction.guild is None:
            return await interaction.response.send_message("Guild only.", ephemeral=True)

        kind = setting["type"]

        # ---- bool: toggle immediately ----
        if kind == "bool":
            current = await self.config.get_bool(gid, key)
            await self.config.set(gid, key, "false" if current else "true")
            settings = await self.config.all(gid)
            embed = _build_category_embed(self.category, interaction.guild, settings)
            await interaction.response.edit_message(embed=embed, view=self)
            return

        # ---- int: modal ----
        if kind == "int":
            current = await self.config.get(gid, key)
            modal = NumberModal(
                category=self.category, key=key,
                label=setting["label"], default=current,
                config=self.config, panel_message=interaction.message,
            )
            await interaction.response.send_modal(modal)
            return

        # ---- str: modal ----
        if kind == "str":
            current = await self.config.get(gid, key)
            modal = TextModal(
                category=self.category, key=key,
                label=setting["label"], default=current,
                hint=setting.get("hint", ""),
                config=self.config, panel_message=interaction.message,
            )
            await interaction.response.send_modal(modal)
            return

        # ---- choice: replace view with choice picker ----
        if kind == "choice":
            view = ChoiceView(
                category=self.category, key=key,
                choices=setting["choices"], config=self.config,
                author_id=interaction.user.id,
            )
            await interaction.response.edit_message(
                embed=discord.Embed(
                    title=f"⚙️ {setting['label']}",
                    description="Select a value:",
                    color=0x5865F2,
                ),
                view=view,
            )
            return

        # ---- channel: replace view with channel picker ----
        if kind == "channel":
            view = ChannelPickerView(
                category=self.category, key=key, config=self.config,
                author_id=interaction.user.id,
            )
            await interaction.response.edit_message(
                embed=discord.Embed(
                    title=f"⚙️ {setting['label']}",
                    description="Select a channel, or use the button below to clear the value.",
                    color=0x5865F2,
                ),
                view=view,
            )
            return


# ---------------------------------------------------------------------------
# Modals
# ---------------------------------------------------------------------------
class NumberModal(discord.ui.Modal):
    def __init__(self, *, category: str, key: str, label: str, default: str,
                 config: ConfigService, panel_message: Optional[discord.Message] = None) -> None:
        super().__init__(title=f"Edit: {label}"[:45])
        self.category = category
        self.key = key
        self.config = config
        self.panel_message = panel_message
        self.value_input: discord.ui.TextInput = discord.ui.TextInput(
            label=label[:45],
            default=default or "0",
            required=True,
            max_length=20,
        )
        self.add_item(self.value_input)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        raw = self.value_input.value.strip()
        try:
            int(raw)
        except ValueError:
            return await interaction.response.send_message("Must be an integer.", ephemeral=True)
        gid = interaction.guild_id
        if gid is None:
            return await interaction.response.send_message("Guild only.", ephemeral=True)
        await self.config.set(gid, self.key, raw)
        await _refresh_panel(interaction, self.category, self.config, self.panel_message)


class TextModal(discord.ui.Modal):
    def __init__(self, *, category: str, key: str, label: str, default: str,
                 hint: str, config: ConfigService, panel_message: Optional[discord.Message] = None) -> None:
        super().__init__(title=f"Edit: {label}"[:45])
        self.category = category
        self.key = key
        self.config = config
        self.panel_message = panel_message
        self.value_input: discord.ui.TextInput = discord.ui.TextInput(
            label=label[:45],
            placeholder=hint[:100] if hint else None,
            default=default or "",
            required=False,
            max_length=1500,
            style=discord.TextStyle.paragraph,
        )
        self.add_item(self.value_input)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        raw = self.value_input.value
        gid = interaction.guild_id
        if gid is None:
            return await interaction.response.send_message("Guild only.", ephemeral=True)
        await self.config.set(gid, self.key, raw)
        await _refresh_panel(interaction, self.category, self.config, self.panel_message)


async def _refresh_panel(interaction: discord.Interaction, category: str, config: ConfigService, panel_message: Optional[discord.Message]) -> None:
    gid = interaction.guild_id
    if gid is None or interaction.guild is None:
        return await interaction.response.send_message("✅ Saved.", ephemeral=True)
    settings = await config.all(gid)
    embed = _build_category_embed(category, interaction.guild, settings)
    view = CategoryView(category=category, config=config, author_id=interaction.user.id)
    if panel_message is not None:
        try:
            await panel_message.edit(embed=embed, view=view)
            return await interaction.response.send_message("✅ Saved.", ephemeral=True)
        except discord.HTTPException:
            pass
    await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


# ---------------------------------------------------------------------------
# Choice picker
# ---------------------------------------------------------------------------
class ChoiceView(discord.ui.View):
    def __init__(self, *, category: str, key: str, choices: list[str],
                 config: ConfigService, author_id: int) -> None:
        super().__init__(timeout=120)
        self.category = category
        self.key = key
        self.config = config
        self.author_id = author_id

        options = [discord.SelectOption(label=c[:100], value=c) for c in choices[:25]]
        select: discord.ui.Select = discord.ui.Select(placeholder="Select a value…", options=options)
        select.callback = self._on_pick
        self.add_item(select)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("Not your session.", ephemeral=True)
            return False
        return True

    async def _on_pick(self, interaction: discord.Interaction) -> None:
        value = interaction.data["values"][0]  # type: ignore[index]
        gid = interaction.guild_id
        if gid is None or interaction.guild is None:
            return await interaction.response.send_message("Guild only.", ephemeral=True)
        await self.config.set(gid, self.key, value)
        settings = await self.config.all(gid)
        embed = _build_category_embed(self.category, interaction.guild, settings)
        view = CategoryView(category=self.category, config=self.config, author_id=interaction.user.id)
        await interaction.response.edit_message(embed=embed, view=view)


# ---------------------------------------------------------------------------
# Channel picker (with clear button)
# ---------------------------------------------------------------------------
class ChannelPickerView(discord.ui.View):
    def __init__(self, *, category: str, key: str, config: ConfigService, author_id: int) -> None:
        super().__init__(timeout=120)
        self.category = category
        self.key = key
        self.config = config
        self.author_id = author_id

        select: discord.ui.ChannelSelect = discord.ui.ChannelSelect(
            placeholder="Select a text channel…",
            channel_types=[discord.ChannelType.text],
            min_values=1,
            max_values=1,
        )
        select.callback = self._on_select
        self.add_item(select)

        clear = discord.ui.Button(label="Clear value", style=discord.ButtonStyle.danger, row=1)
        clear.callback = self._on_clear
        self.add_item(clear)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("Not your session.", ephemeral=True)
            return False
        return True

    async def _on_select(self, interaction: discord.Interaction) -> None:
        channel_id = interaction.data["values"][0]  # type: ignore[index]
        gid = interaction.guild_id
        if gid is None or interaction.guild is None:
            return await interaction.response.send_message("Guild only.", ephemeral=True)
        await self.config.set(gid, self.key, channel_id)
        settings = await self.config.all(gid)
        embed = _build_category_embed(self.category, interaction.guild, settings)
        view = CategoryView(category=self.category, config=self.config, author_id=interaction.user.id)
        await interaction.response.edit_message(embed=embed, view=view)

    async def _on_clear(self, interaction: discord.Interaction) -> None:
        gid = interaction.guild_id
        if gid is None or interaction.guild is None:
            return await interaction.response.send_message("Guild only.", ephemeral=True)
        await self.config.set(gid, self.key, "")
        settings = await self.config.all(gid)
        embed = _build_category_embed(self.category, interaction.guild, settings)
        view = CategoryView(category=self.category, config=self.config, author_id=interaction.user.id)
        await interaction.response.edit_message(embed=embed, view=view)
