# Discord Security Bot Template

A production-ready, modular, database-backed Discord security & management bot built with **Python 3.11+** and **discord.py 2.x**. Clone, rebrand, and configure for any community.

## Features

- 🛡️ **Security** — Anti-Nuke, Anti-Raid, Anti-Spam, AutoMod, Server Watch
- 🎫 **Advanced Tickets** — Panels, categories, transcripts, claiming, ratings-ready
- 👋 **Welcome/Goodbye** with placeholders
- 🔨 **Moderation** — Ban, kick, timeout, warn, purge, lock/unlock, and more
- 📋 **Comprehensive Logging** — 6 independent log categories
- 🚨 **Emergency Lockdown**
- 🎛️ **Interactive /panel** — one command, dropdown-driven configuration
- 💾 **SQLite (aiosqlite)** — persists across restarts, multi-guild safe
- 🔐 **Centralized permission system**

## Requirements

- Python 3.11+
- A Discord application with bot user (`Message Content`, `Server Members`, and `Moderation` intents enabled)

## Installation

```bash
git clone <your-repo-url>
cd discord-security-bot
python -m venv .venv
source .venv/bin/activate    # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env and set DISCORD_TOKEN
```

## Running

```bash
python main.py
```

Commands sync on startup. In a test server, register commands to a guild for instant sync (edit `setup_hook`).

## Environment Variables

| Variable | Purpose | Default |
|---|---|---|
| `DISCORD_TOKEN` | Bot token (**required**) | — |
| `DATABASE_PATH` | SQLite file path | `data/bot.db` |
| `BOT_NAME` | Bot username | `Security Bot` |
| `BOT_STATUS` | online/idle/dnd/invisible | `online` |
| `BOT_ACTIVITY_TYPE` | playing/listening/watching/streaming/competing | `watching` |
| `BOT_ACTIVITY` | Activity text | `your server` |
| `EMBED_COLOR` | Hex color for embeds | `0x5865F2` |
| `EMBED_FOOTER` | Default footer | `Security Bot` |
| `LOG_LEVEL` | Python log level | `INFO` |

## Initial Setup

1. Invite the bot with `bot` + `applications.commands` scopes and `Administrator` (recommended for anti-nuke).
2. Run `/panel` in your server.
3. Configure each system from the dropdowns (or dedicated `/xxx-config` commands).
4. Run `/add-admin-role` and `/add-staff-role` to give your team access.
5. Optionally run `/trust-user` on trusted administrators so anti-nuke never touches them.

## Commands

Use `/help` for an interactive menu. Highlights:

- `/panel` — central control center
- `/security` — dashboard
- `/antinuke`, `/antiraid`, `/antispam`, `/automod`, `/serverwatch` — status
- `/lockdown`, `/unlockdown`
- `/ban`, `/kick`, `/timeout`, `/warn`, `/purge`, `/lock`, `/unlock`, etc.
- `/ticket-panel`, `/ticket-category-add`, `/tickets-config`
- `/welcome-config`, `/logging-config`, `/security-config`

All `*-config` commands either open a dropdown panel directly or point you at the equivalent `/panel` section.

## Database

SQLite, using WAL. All queries parameterized. Migrations run on startup via `bot/database/migrations.py`.

Tables: `guild_config`, `staff_roles`, `trusted_users`, `warnings`, `mod_actions`, `ticket_panels`, `ticket_categories`, `tickets`, `incidents`, `watch_events`, `ignore_channels`, `automod_words`, `ticket_ratings`.

## Permission Model

- **Admin**: server owner, Administrator, Manage Guild, or a role marked `admin` via `/add-admin-role`.
- **Staff/moderator**: admin, Moderate Members, Manage Messages, Kick/Ban, or a `staff` role.

Never duplicated — all checks go through `bot/core/checks.py`.

## Security Systems

- **Anti-Nuke** uses audit logs to attribute actions. Discord's API can lag; we only fire when a threshold is met within a short window.
- **Anti-Raid** tracks join velocity in memory and evaluates account age.
- **Anti-Spam** uses per-user sliding windows with anti-false-positive cooldowns.
- **AutoMod** filters invites, links, caps, repeated chars, blacklisted words.
- **Server Watch** logs and alerts on suspicious activity.

## Documentation of Discord API limits

- Detecting "who deleted X" requires `View Audit Log`. If missing, anti-nuke logs the event but cannot punish.
- Avatar pattern / username similarity detection is not reliably available via the API and is intentionally not faked.
- Vanity URL changes are not exposed by Discord's API for most bots.

## Development

```
bot/
├── main.py / config.py
├── core/          — bot class, checks, embeds, errors, paginator
├── cogs/          — feature modules
├── services/      — business logic
├── views/         — UI components
└── database/      — async sqlite
```

Add a cog by dropping a file in `bot/cogs/` and appending it to `INITIAL_COGS` in `bot/core/bot.py`.

## Testing

```bash
pytest
```

## License

MIT — see `LICENSE`.
