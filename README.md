# Discord Security Bot

A modular, database-backed Discord security and management bot for a single
community server. Built with Python 3.11+ and discord.py 2.x.

Includes advanced tickets, moderation, security systems, and a multi-signal
verification and anti-alt engine that never stores user IPs.

---

## Features

### Verification & anti-alt
- Public verification panel with per-guild configuration
- Risk-based routing across 5 verification layers
- 40 detectors across Discord, Behavior, Roblox, Network, and Historical families
- Correlation engine that scores independent signals — not just a checklist
- Roblox account linking via public Roblox APIs (no credentials, no cookies)
- Ban-evasion detection via avatar/name fingerprints
- Account clustering for coordinated alt rings
- Persistent moderator review panels that survive restarts
- Queue command to see who's waiting for review
- Every log passes through a redaction layer before it reaches Discord

### Security
- Anti-Nuke with audit-log-based executor attribution
- Anti-Raid with join-velocity tracking and auto-lockdown
- Anti-Spam with configurable thresholds and actions
- AutoMod for invites, links, caps, repeats, and blacklisted words
- Server Watch for continuous activity monitoring
- Emergency lockdown and unlockdown

### Moderation
- Ban, kick, timeout, warn, purge, slowmode, lock, unlock
- Hierarchy checks (bot and moderator cannot act above their top role)
- Case logging for every action
- Warning history per user

### Tickets
- Admin console with dropdown-driven category setup
- Public panel with per-category routing
- Claim, close, reopen, delete, rename, transcript
- Auto-archive transcripts to a channel and DM to the opener
- Optional rating prompt after close

### Welcome, goodbye, logging
- Welcome and goodbye messages with placeholder variables
- Six independent log categories (moderation, messages, server, members, security, tickets)
- Every log field redacted at the sink

### Infrastructure
- SQLite via aiosqlite — no external DB required
- Central config via `/panel` — no memorizing arguments
- Multi-guild safe (all queries scoped by `guild_id`) though designed for one server
- Central permission system: `@is_guild_admin()` / `@is_moderator()`

---

## Requirements

- Python 3.11 or newer
- A Discord application with a bot user
- Bot intents: **Message Content**, **Server Members**, **Moderation**

---

## Installation

```bash
git clone <your-repo-url>
cd discord-security-bot
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env and set DISCORD_TOKEN (and DEV_GUILD_ID while testing)
python main.py
```

---

## Configuration

### Environment variables

| Variable | Purpose | Default |
|---|---|---|
| `DISCORD_TOKEN` | Bot token (**required**) | — |
| `DEV_GUILD_ID` | Sync commands instantly to this guild (testing) | — |
| `DATABASE_PATH` | SQLite file path | `data/bot.db` |
| `BOT_NAME` | Bot username | `Security Bot` |
| `BOT_STATUS` | online / idle / dnd / invisible | `online` |
| `BOT_ACTIVITY_TYPE` | playing / listening / watching / competing / streaming | `watching` |
| `BOT_ACTIVITY` | Activity text | `your server` |
| `EMBED_COLOR` | Default embed color (hex) | `0x5865F2` |
| `EMBED_FOOTER` | Default embed footer | `Security Bot` |
| `LOG_LEVEL` | DEBUG / INFO / WARNING / ERROR | `INFO` |
| `VERIFY_SESSION_TIMEOUT` | Verification session lifetime (seconds) | `900` |

### First-time setup

1. Invite the bot with the `bot` and `applications.commands` scopes.
2. Run `/panel` in your server.
3. Configure each system from the dropdown.
4. Set staff roles with `/add-staff-role` and admin roles with `/add-admin-role`.

### Verification setup

1. Create two roles: `@Verified` and `@Quarantine`, both below the bot's role.
2. Set the log channel: `/logging-config category:security channel:#log_security`
3. `/verification-role role:@Verified`
4. `/verification-quarantine-role role:@Quarantine`
5. `/verification-panel` in your verify channel.

---

## Commands

Use `/help` for an interactive menu. Command groups:

- **Verification** — `/verify`, `/verification-panel`, `/verify-roblox`, `/verify-status`, `/verify-queue`, `/verify-review`, `/verify-false-positive`, plus config commands
- **Security** — `/security`, `/antinuke`, `/antiraid`, `/antispam`, `/automod`, `/serverwatch`, `/lockdown`
- **Moderation** — `/ban`, `/kick`, `/timeout`, `/warn`, `/purge`, `/lock`, `/unlock`, and more
- **Tickets** — `/ticket-panel`, `/tickets-config`, `/ticket-claim`, `/ticket-close`, `/ticket-transcript`
- **Utility** — `/ping`, `/botinfo`, `/userinfo`, `/roleinfo`, `/avatar`, `/help`
- **Owner** — `/sync`, `/resync-global`

---

## Verification system overview

### Risk scoring

Each detector produces evidence with severity and confidence. The risk engine:

- Groups detectors into signal families (Discord, Behavior, Roblox, Network, Historical, Correlation)
- Collapses duplicate evidence — VPN + Proxy + Datacenter count as one network observation
- Caps each family's contribution so no single signal can dominate
- Adds a correlation bonus when independent families fire together
- Damps low-confidence results before scoring

Result: a 0–100 risk score, a risk level (LOW / GUARDED / ELEVATED / HIGH / CRITICAL),
and a required verification layer (1–5).

### Detectors

- **Discord** (10): account age, join age, username/display changes, avatar reuse, mutual servers, cluster patterns
- **Behavior** (10): join bursts, verification bursts, rejoin patterns, ban evasion fingerprints
- **Roblox** (8): account age, activity level, link history, cluster correlation
- **Network** (8): VPN, proxy, Tor, datacenter, IP reputation — **UNAVAILABLE by default**
- **Historical / Correlation** (4): server history, quarantine history, cross-family correlation, abuse signatures

### Network layer is off by design

Discord does not expose member IP addresses to bots. Obtaining them requires
routing users through a browser OAuth flow — which this bot intentionally does
not do. The 8 network detectors return `UNAVAILABLE` and contribute zero risk.
This is correct behavior, not a bug.

**This bot does not collect, store, or log IP addresses.**

### Redaction

Every log message and moderator panel passes through `RedactionManager` before
display. IPv4, IPv6, bearer tokens, cookies, API keys, and long hex strings are
scrubbed to `[REDACTED_*]` placeholders at the sink.

---

## Database

SQLite via aiosqlite, WAL mode. Migrations run automatically on startup.

Base tables: `guild_config`, `staff_roles`, `trusted_users`, `warnings`,
`mod_actions`, `ticket_panels`, `ticket_categories`, `tickets`, `incidents`,
`watch_events`, `ignore_channels`, `automod_words`, `ticket_ratings`.

Verification tables: `verification_sessions`, `verification_attempts`,
`risk_assessments`, `roblox_links`, `network_events`, `account_history`,
`account_clusters`, `manual_reviews`, `security_events`, `ban_history`,
`abuse_signatures`, `pending_reviews`.

**Back up `data/bot.db` regularly.** It contains every ban record, warning,
and verification assessment.

---

## Permission model

Two centralized checks, used everywhere:

- **`@is_guild_admin()`** — server owner, Administrator, Manage Guild, or a role
  registered with `/add-admin-role`
- **`@is_moderator()`** — above, or Moderate Members, Manage Messages, Kick, Ban,
  or a role registered with `/add-staff-role`

Never duplicated. Never inline.

---

## Development

```
bot/
├── main.py / config.py
├── core/          bot class, checks, embeds, errors, paginator
├── cogs/          feature modules
├── services/      business logic
├── views/         UI components
├── database/      async SQLite + base migrations
└── verification/  40 detectors, engines, sessions, redaction
```

Add a cog: drop a file in `bot/cogs/`, append to `INITIAL_COGS` in `bot/core/bot.py`.

---

## Known limitations

- **Network detection is disabled.** No IP collection. See above.
- **Behavior tracker is in-memory.** Join-burst baselines reset on restart.
- **Roblox public API can rate-limit** under heavy concurrent load.
- **Review panels persist, but session state does not** across a hard restart
  if the session was already in a terminal state.

---

## License

MIT — see `LICENSE`.
