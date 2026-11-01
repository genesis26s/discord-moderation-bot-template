<div align="center">

# 🛡️ Discord Security & Support Bot

**A modular, database-backed Discord community management bot.**

Built for communities that want a powerful ticket system, robust moderation, and real security features — without unnecessary bloat.

[![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![discord.py](https://img.shields.io/badge/discord.py-2.x-5865F2?logo=discord&logoColor=white)](https://discordpy.readthedocs.io/)
[![SQLite](https://img.shields.io/badge/SQLite-aiosqlite-003B57?logo=sqlite&logoColor=white)](https://aiosqlite.omnilib.dev/)
[![License](https://img.shields.io/badge/License-MIT-22c55e)](./LICENSE)

</div>

---

## 📖 Table of contents

- [What is this](#-what-is-this)
- [Feature highlights](#-feature-highlights)
- [Quick start](#-quick-start)
- [First-time setup](#-first-time-setup)
- [Ticket system](#-ticket-system)
- [Command reference](#-command-reference)
- [Environment variables](#-environment-variables)
- [Database](#-database)
- [Permissions](#-permissions)
- [Privacy & security posture](#-privacy--security-posture)
- [Project layout](#-project-layout)
- [Known limitations](#-known-limitations)

---

## 🎯 What is this

A complete, self-hosted Discord bot designed for a single community server. It combines a highly customizable support ticket system with standard moderation tools and advanced server security features.

| Area | What you get |
|---|---|
| 🎫 **Tickets** | Advanced admin console, ticket ratings, transcripts, emoji support |
| 🔒 **Security** | Anti-nuke, anti-raid, anti-spam, AutoMod, Server Watch |
| 🔨 **Moderation** | Ban, kick, timeout, warn, purge, lock — all with case logging |
| 👋 **Community** | Welcome / goodbye messages, six independent log channels |
| 🧰 **Utility** | Custom embed builder, mass DM, server info, interactive `/help` |

---

## ✨ Feature highlights

<details>
<summary><b>🎫 Advanced Ticket System</b></summary>

- **Admin Dashboard:** Manage categories, view stats, and publish panels via a clean UI.
- **Ticket Ratings:** Users are DM'd a 1-5 star rating prompt when a ticket closes.
- **Staff Leaderboard:** Track staff performance with average ratings and review history.
- **Custom Categories:** Set custom names, welcome messages, channel naming templates, and support roles.
- **Emoji Support:** Assign custom or standard emojis to ticket categories.
- **Transcripts:** Automatically generate and archive text transcripts, and DM a copy to the user.
- **Orphan Cleanup:** If a ticket channel is manually deleted, the bot automatically cleans up the database so the user can open a new ticket.
- **Interactive Controls:** Claim, Close, Reopen, Delete, Add Member, and Transcript buttons inside every ticket.
- **Safety:** Smart handling of bad emojis, 3-second interaction timeouts, and proper deferrals.

</details>

<details>
<summary><b>🔒 Security systems</b></summary>

- 💥 **Anti-Nuke** — Audit-log-based executor attribution, configurable thresholds, trust allowlist.
- 🌊 **Anti-Raid** — Join-velocity tracking, auto-lockdown on trigger.
- 📨 **Anti-Spam** — Configurable thresholds, cooldowns, actions (warn / delete / timeout / kick / ban).
- 🤖 **AutoMod** — Invites, links, caps, repeats, blacklisted words.
- 👁️ **Server Watch** — Continuous activity monitoring with severity levels.
- 🔐 **Emergency lockdown** — One command to lock every text channel.

</details>

<details>
<summary><b>🔨 Moderation</b></summary>

- 🚫 `/ban`, `/unban`, `/kick`, `/softban`
- ⏳ `/timeout`, `/untimeout`
- ⚠️ `/warn`, `/unwarn`, `/warnings`
- 🧹 `/purge`, `/slowmode`, `/lock`, `/unlock`
- ✏️ `/nick`, `/role`, `/role-add`, `/role-remove`
- 📝 Every action written to a case log
- 🪜 Hierarchy checks on bot AND moderator

</details>

<details>
<summary><b>🧰 Utility & Logging</b></summary>

- 📋 Six independent log channels: moderation, messages, server, members, security, tickets.
- 🎨 `/embed` — Interactive builder for custom embeds.
- 📢 `/dm` — Mass DM all human members (with rate-limit safety).
- 👋 Welcome messages with placeholder variables (`{user}`, `{server}`, `{member_count}`).
- 🎛️ `/help` — Interactive, dropdown-based command directory.

</details>

---

## 🚀 Quick start

```bash
# 1. Clone https://github.com/genesis26s/discord-moderation-bot-template
git clone 
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
