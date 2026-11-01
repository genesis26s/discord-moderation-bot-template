
<div align="center">

# 🛡️ Discord Security & Support Bot

**A modular, fully self-hosted Discord management suite.**

Built for communities that need a powerful ticketing system, robust moderation, and advanced server security — without collecting unnecessary user data or relying on third-party web panels.

[![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![discord.py](https://img.shields.io/badge/discord.py-2.x-5865F2?logo=discord&logoColor=white)](https://discordpy.readthedocs.io/)
[![SQLite](https://img.shields.io/badge/SQLite-aiosqlite-003B57?logo=sqlite&logoColor=white)](https://aiosqlite.omnilib.dev/)
[![License](https://img.shields.io/badge/License-MIT-22c55e)](./LICENSE)

</div>

---

## 📖 Table of contents

- [What is this](#-what-is-this)
- [Complete Feature Breakdown](#-complete-feature-breakdown)
  - [🎫 Advanced Ticket System](#-advanced-ticket-system)
  - [🔒 Security & Anti-Abuse](#-security--anti-abuse)
  - [🔨 Moderation Suite](#-moderation-suite)
  - [👋 Community & Logging](#-community--logging)
  - [🧰 Utility & Admin Tools](#-utility--admin-tools)
- [Quick Start](#-quick-start)
- [First-Time Setup](#-first-time-setup)
- [Command Reference](#-command-reference)
- [Environment Variables](#-environment-variables)
- [Database & Storage](#-database--storage)
- [Permission Model](#-permission-model)
- [Privacy Posture](#-privacy-posture)

---

## 🎯 What is this

A complete, self-hosted Discord bot designed for a single community server. It combines a highly customizable support ticket system with standard moderation tools and advanced server security features. 

**It does not rely on external dashboards, web panels, or third-party databases.** Everything is managed natively inside Discord via slash commands, dropdown menus, and interactive buttons.

---

## ✨ Complete Feature Breakdown

### 🎫 Advanced Ticket System

The ticket system is the most feature-rich part of this bot. It is designed to replace clunky ticket bots with a seamless, highly customized experience for both staff and users.

*   **Admin Console (`/ticket-panel`):** A central hub for staff. From here, you can create categories, edit the public panel's appearance, configure transcript archiving, and view ticket statistics.
*   **Public Request Panel:** A clean embed with a dropdown menu. Users select a category (e.g., "General Support", "Report a User", "Appeal") and a private channel is instantly created for them.
*   **Custom Categories:** Every ticket type can have its own:
    *   Display name and description.
    *   Custom emoji (standard or custom server emojis).
    *   Channel naming template (e.g., `ticket-{username}`).
    *   Greeting message (the embed they see when they open the ticket).
    *   Specific support role (so specific teams handle specific tickets).
*   **Staff Controls:** Inside every ticket, there are four buttons:
    *   **Claim:** Assigns the ticket to the staff member.
    *   **Add Member:** Opens a user picker to add another user to the ticket.
    *   **Transcript:** Generates a `.txt` file of the conversation on the spot.
    *   **Close:** Opens a modal asking for a close reason and whether to delete the channel.
*   **Auto-Archiving:** When a ticket is closed, the bot automatically generates a transcript and sends it to a private archive channel (configurable in the console). It also DMs a copy to the user who opened the ticket.
*   **Ticket Ratings:** When a ticket is closed, the user is DM'd a 1-5 star rating prompt. Ratings are tracked per staff member who handled the ticket.
    *   `/ticket-ratings` shows a Top 10 leaderboard of your staff.
    *   `/ticket-ratings member:@User` shows a specific staff member's average rating and recent comments.
    *   `/ticket-ratings-history` shows the last 25 reviews across the whole server.
*   **Orphan Cleanup:** If a staff member manually deletes a ticket channel via Discord (instead of using the Close button), the bot sweeps the database on startup and closes the orphaned record so the user isn't blocked from opening a new ticket.
*   **Emoji Safety:** If an admin assigns an emoji to a category that Discord rejects (e.g., a broken custom emoji), the bot silently strips the emoji during publishing rather than throwing a `400 Bad Request` error.
*   **Timeout Protection:** All buttons (especially "Publish Panel") use discord.py `deferrals` to ensure the bot never times out ("This interaction failed") during heavy database operations.

### 🔒 Security & Anti-Abuse

Built to protect your server from standard Discord threats without requiring you to configure complex webhooks.

*   **Anti-Nuke:** Monitors the Discord Audit Logs for destructive actions (mass channel deletions, mass role deletions, mass bans/kicks, webhook creation).
    *   If a user exceeds the configured threshold (e.g., deletes 3 channels in 10 seconds), the bot can strip their roles, kick, or ban them.
    *   Includes a `/trust-user` command so administrators are never falsely flagged.
*   **Anti-Raid:** Monitors join velocity. If 10 accounts join within 15 seconds, the bot triggers a lockdown.
    *   Can be configured to auto-lockdown the server, or simply alert staff in a security channel.
    *   Tracks account age to detect waves of fresh accounts.
*   **Anti-Spam:** A per-user message tracker. Detects rapid message bursts, duplicate spam (sending the same message 3+ times), and excessive mentions. Actions can be set to delete, timeout, kick, or ban.
*   **AutoMod:** An automated word and link filter. Detects Discord invites, external URLs, excessive caps, and blacklisted words. Includes a whitelist for specific roles.
*   **Server Watch:** A passive monitoring system that logs significant server events (like mass joins or sudden channel deletions) to a dedicated security channel, categorized by severity levels.
*   **Emergency Lockdown:** A `/lockdown` command that locks *every* text channel in the server simultaneously. Essential for active raid scenarios. `/unlockdown` restores normal permissions.

### 🔨 Moderation Suite

Standard moderation tools with built-in safety nets.

*   **Actions:** `/ban`, `/kick`, `/softban`, `/timeout`, `/warn`.
*   **Hierarchy Protection:** The bot will refuse to moderate a user if the user's highest role is above the bot's highest role, or above the moderator's highest role.
*   **Case Logging:** Every moderation action is logged to a specific channel with the moderator's name, the reason, and the duration (if applicable).
*   **Warning System:** Warnings are stored in the database. You can view a user's history with `/warnings` and delete specific warnings with `/unwarn`.
*   **Channel Management:** `/purge` (bulk delete up to 100 messages), `/slowmode`, `/lock`, and `/unlock`.

### 👋 Community & Logging

Keep your community informed and your staff accountable.

*   **Welcome & Goodbye:** Highly customizable messages using placeholder variables.
    *   Variables include: `{user}`, `{username}`, `{server}`, `{member_count}`.
    *   Can be sent as a plain text message or a rich embed.
    *   Includes a `/welcome-test` command to preview how it looks.
*   **Advanced Logging:** Six independent log categories, each routing to its own channel:
    *   **Moderation:** Bans, kicks, warnings.
    *   **Messages:** Message edits and deletions.
    *   **Server:** Channel created/deleted, role created/deleted.
    *   **Members:** Joins and leaves.
    *   **Security:** Anti-nuke, anti-raid, and AutoMod triggers.
    *   **Tickets:** Ticket open/close events.

### 🧰 Utility & Admin Tools

Quality-of-life commands for server management.

*   **`/embed`:** A modal-based embed builder. Allows you to post an embed with a Title, Description, Color, Image, and Footer. You can also use it to edit previously posted embeds by passing the Message ID.
*   **`/dm`:** A mass-DM tool. It sends a message to every human member in the server with a 1.5-second delay to help prevent Discord rate limits and bans. *Use with extreme caution.*
*   **`/panel`:** A centralized configuration interface for security, welcome messages, and logging.
*   **`/help`:** An interactive, dropdown-based command directory.
*   **`/sync` & `/resync-global`:** Owner-only commands to force Discord to refresh your slash commands immediately without restarting the bot.

---

## 🚀 Quick start

```bash
# 1. Clone
git clone <your-repo-url>
cd discord-security-bot

# 2. Virtualenv
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate

# 3. Install
pip install -r requirements.txt

# 4. Configure
cp .env.example .env
# Open .env and paste your DISCORD_TOKEN

# 5. Run
python main.py
```

Requirements: Python 3.11+ and a Discord application with
Message Content, Server Members, and Moderation intents enabled.

Bot Invite URL

Invite with the bot + applications.commands scopes:

```
https://discord.com/oauth2/authorize?client_id=YOUR_APP_ID&permissions=8&scope=bot+applications.commands
```

(Administrator permission is recommended so the Anti-Nuke system can read Audit Logs).

---

🎬 First-time setup

Once the bot is online in your server, follow these steps in order:

1. Configure log channels

Use /logging-config to tell the bot where to send logs.

```
/logging-config category:security   channel:#log-security
/logging-config category:tickets    channel:#log-tickets
```

2. Register staff roles

Register your staff and admin roles so they can access panels.

```
/add-admin-role role:@Admin
/add-staff-role role:@Moderator
```

3. Set up tickets

Run /ticket-panel to open the support operations console.

1. Click New Category and fill out the modal.
2. Choose the destination category channel and the support role.
3. Click Publish Panel in your #support channel.

4. Configure security and welcome

Run /panel to open the central control center. Use the dropdown menus to enable Anti-Raid, set your Welcome channel, and configure AutoMod.

---

📋 Command reference

<details>
<summary><b>🎫 Tickets</b></summary>Command Description
/ticket-panel Opens the admin console for setup.
/ticket Shows basic ticket info.
/ticket-add Adds a user to the current ticket.
/ticket-remove Removes a user from the current ticket.
/ticket-claim Marks the ticket as claimed by you.
/ticket-close Closes the ticket (asks for reason).
/ticket-reopen Reopens a closed ticket.
/ticket-delete Deletes the ticket channel.
/ticket-rename Renames the ticket channel.
/ticket-transcript Generates a text transcript.
/ticket-ratings Shows the staff rating leaderboard.
/ticket-ratings-history Shows recent reviews.
/ticket-emojis Inspects or clears category emojis.

</details><details>
<summary><b>🔒 Security</b></summary>Command Description
/security Security dashboard.
/antinuke View Anti-Nuke status.
/antiraid View Anti-Raid status.
/antispam View Anti-Spam status.
/automod View AutoMod status.
/serverwatch View Server Watch status.
/lockdown Locks all text channels.
/unlockdown Unlocks all text channels.

</details><details>
<summary><b>🔨 Moderation</b></summary>Command Description
/ban, /unban Ban or unban a user.
/kick Kick a user.
/softban Ban then instantly unban to clear messages.
/timeout, /untimeout Mute a user (up to 28 days).
/warn, /unwarn Add or remove a warning.
/warnings View a user's warnings.
/purge Bulk delete messages.
/slowmode Set channel slowmode.
/lock, /unlock Lock a channel.

</details><details>
<summary><b>🧰 Utility & Info</b></summary>Command Description
/help Interactive help menu.
/panel Central configuration center.
/embed Post or edit a custom embed.
/dm Mass DM all human members.
/server, /userinfo View info.
/roles, /channels List server entities.
/ping, /botinfo Bot status.
/avatar, /servericon View images.

</details>---

⚙️ Environment variables

```env
# ─── Discord ────────────────────────────────────────────────
DISCORD_TOKEN=your_bot_token_here
# Set to your server ID for instant command syncing during development
DEV_GUILD_ID=                  

# ─── Database ───────────────────────────────────────────────
DATABASE_PATH=data/bot.db

# ─── Bot Identity ───────────────────────────────────────────
BOT_NAME=Security Bot
BOT_DESCRIPTION=Advanced Discord security & management
BOT_STATUS=online              # online | idle | dnd | invisible
BOT_ACTIVITY_TYPE=watching     # playing | listening | watching | competing | streaming
BOT_ACTIVITY=your server

# ─── Branding ───────────────────────────────────────────────
EMBED_COLOR=0x5865F2
SUCCESS_COLOR=0x57F287
ERROR_COLOR=0xED4245
WARNING_COLOR=0xFEE75C
EMBED_FOOTER=Security Bot

# ─── Logging ────────────────────────────────────────────────
LOG_LEVEL=INFO                 # DEBUG | INFO | WARNING | ERROR | CRITICAL
```

---

💾 Database & Storage

The bot uses SQLite (via aiosqlite). It creates a bot.db file automatically on the first run.

Tables include:

· guild_config: Stores all settings (welcome messages, log channels, etc.).
· tickets, ticket_panels, ticket_categories, ticket_ratings: The entire ticket system.
· warnings, mod_actions: Moderation history.
· staff_roles, trusted_users: Permission structures.

⚠️ Important: Back up your data/bot.db file regularly. If you lose it, you lose all server configurations, warnings, and ticket histories.

---

🔑 Permission Model

The bot uses two centralized permission checks to keep things secure.

1. @is_guild_admin():
   · Server Owner
   · Administrator permission
   · Manage Guild permission
   · OR has a role registered via /add-admin-role
2. @is_moderator():
   · Any of the above
   · Moderate Members permission
   · Manage Messages permission
   · Kick/Ban permissions
   · OR has a role registered via /add-staff-role

If a user does not meet these criteria, the bot will reject the command.

---

🔐 Privacy Posture

This bot is designed to be 100% self-contained.

· It does not send your server data to any external APIs.
· It does not collect IP addresses, browser fingerprints, or device data.
· Ticket transcripts are stored locally in your server's private archive channel (if configured) and DMed to the user who opened the ticket.

Your data stays on your host.

---

📜 License

MIT — see LICENSE.

<div align="center">Built for communities that want complete control over their server.

</div>
```
