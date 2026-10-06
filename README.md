<div align="center">

# 🛡️ Discord Security Bot

**A modular, database-backed Discord security & community-management bot.**

Built for a single community server that wants real moderation, real
tickets, and real alt detection — without collecting user IPs.

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
- [Verification system](#-verification-system)
- [Command reference](#-command-reference)
- [Environment variables](#-environment-variables)
- [Database](#-database)
- [Permissions](#-permissions)
- [Privacy & security posture](#-privacy--security-posture)
- [Project layout](#-project-layout)
- [Development](#-development)
- [Known limitations](#-known-limitations)
- [License](#-license)

---

## 🎯 What is this

A Discord bot template you can clone, rename, and drop into a community server.
It ships with everything a serious community needs on day one:

| Area | What you get |
|---|---|
| 🛡️ **Verification** | 40-detector alt & raid detection engine, 5 risk layers |
| 🔒 **Security** | Anti-nuke, anti-raid, anti-spam, AutoMod, Server Watch |
| 🔨 **Moderation** | Ban, kick, timeout, warn, purge, lock — all with case logging |
| 🎫 **Tickets** | Admin console, dropdown panel, transcripts, ratings |
| 👋 **Community** | Welcome / goodbye messages, six log channels |
| ⚙️ **Config** | Everything via `/panel` — no memorizing arguments |

Designed for **one server**. Not a bot marketplace thing. Not multi-tenant
SaaS. Just a solid, self-contained security bot for a community you run.

---

## ✨ Feature highlights

<details>
<summary><b>🛡️ Verification & anti-alt</b></summary>

- 🎛️ Public verification panel with per-guild configuration
- 🎚️ Risk-based routing across 5 verification layers
- 🔍 40 detectors across Discord, Behavior, Roblox, Network, and Historical families
- 🧠 Correlation engine — independent signals score together, duplicates collapse
- 🎮 Roblox account linking via public Roblox APIs (no credentials, no cookies)
- 👥 Ban-evasion detection via avatar and name fingerprints
- 🕸️ Account clustering for coordinated alt rings
- 📋 Moderator review panels that survive bot restarts
- 📊 `/verify-queue` work list for pending reviews
- 🚫 **Zero IP collection, ever**

</details>

<details>
<summary><b>🔒 Security systems</b></summary>

- 💥 **Anti-Nuke** — audit-log-based executor attribution, configurable thresholds, trust allowlist
- 🌊 **Anti-Raid** — join-velocity tracking, auto-lockdown on trigger
- 📨 **Anti-Spam** — configurable thresholds, cooldowns, actions (warn / delete / timeout / kick / ban)
- 🤖 **AutoMod** — invites, links, caps, repeats, blacklisted words
- 👁️ **Server Watch** — continuous activity monitoring with severity levels
- 🔐 **Emergency lockdown** — one command to lock every text channel

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
<summary><b>🎫 Ticket system</b></summary>

- 🎛️ Admin dashboard with dropdown category management
- 📢 Public panel with per-category routing
- 🧑‍💼 Claim, close, reopen, delete, rename, transcript
- 📄 Auto-archive transcripts to a channel + DM to the opener
- ⭐ Optional rating prompt after close

</details>

<details>
<summary><b>👋 Community & logging</b></summary>

- 👋 Welcome messages with placeholder variables (`{user}`, `{server}`, `{member_count}`)
- 🚪 Goodbye messages
- 📋 Six independent log channels: moderation, messages, server, members, security, tickets
- 🎨 Every embed branded from `.env` values

</details>

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

> **Requirements:** Python 3.11+ and a Discord application with
> **Message Content**, **Server Members**, and **Moderation** intents enabled.

### Bot invite URL

Invite with the `bot` + `applications.commands` scopes:

```
https://discord.com/oauth2/authorize?client_id=YOUR_APP_ID&permissions=8&scope=bot+applications.commands
```

`permissions=8` grants Administrator, which the anti-nuke system needs to see
audit logs and enforce role hierarchy. If you'd rather use finer permissions,
the minimum set is:

```
View Audit Log, Manage Roles, Manage Channels, Manage Guild,
Kick Members, Ban Members, Moderate Members, Manage Messages,
Manage Webhooks, Send Messages, Embed Links, Attach Files,
Read Message History, Add Reactions
```

---

## 🎬 First-time setup

Once the bot is online in your server:

### 1. Configure identity and log channels

```
/logging-config category:security   channel:#log-security
/logging-config category:moderation channel:#log-moderation
/logging-config category:members    channel:#log-members
```

### 2. Register staff roles

```
/add-admin-role role:@Admin
/add-staff-role role:@Moderator
```

### 3. Set up verification

Create two roles below the bot's highest role:

- `@Verified` — granted on successful verification
- `@Quarantine` — applied to high-risk members pending review

Then:

```
/verification-role            role:@Verified
/verification-quarantine-role role:@Quarantine
/verification-panel
```

Post `/verification-panel` in your `#verify` channel. That's the public panel
users click to start verification.

### 4. Configure everything else

```
/panel
```

One command. A dropdown-driven control center. Every system is in there.

---

## 🧠 Verification system

The verification pipeline is the most complex part of this bot. Here's the
60-second version.

### The pipeline

```
  Member joins
        │
        ▼
  Verification session created
        │
        ▼
  ┌──────────────────────────────────┐
  │  40 detectors run in parallel    │
  │  ├─ Discord   (10)               │
  │  ├─ Behavior  (10)               │
  │  ├─ Roblox    (8)                │
  │  ├─ Network   (8) — UNAVAILABLE  │
  │  └─ Historical / Correlation (4) │
  └──────────────────────────────────┘
        │
        ▼
  Confidence engine → damps weak evidence
        │
        ▼
  Correlation engine → collapses duplicates, caps families
        │
        ▼
  Risk engine → 0–100 score, level, layer
        │
        ▼
  ┌──────────┬───────────┬────────────┐
  │   LOW    │ GUARDED / │  CRITICAL  │
  │          │ ELEVATED  │            │
  │          │   /HIGH   │            │
  ▼          ▼           ▼
  Layer 1   Layer 2–4   Layer 5
  Verified  Enhanced    Quarantine
  role      verification + review
            required
```

### Risk levels

| Score | Level | Action |
|---|---|---|
| `0–19` | 🟢 **LOW** | Standard verification, role granted |
| `20–39` | 🟡 **GUARDED** | Enhanced verification required |
| `40–59` | 🟠 **ELEVATED** | Correlation review required |
| `60–79` | 🔴 **HIGH** | Restricted verification + moderator eligibility |
| `80–100` | ⛔ **CRITICAL** | Quarantine + manual review |

### Why signals don't just add up

The engine groups detectors into **signal families** and applies a cap per
family. This matters because:

```
  VPN detected      +15
  Proxy detected    +15     ← these three are ONE observation
  Datacenter ASN    +15     ← (all "network is unusual")
  ─────────────────────
  Naïve total:      +45     ← WRONG
  Family-capped:    +25     ← correct
```

Same for account age (Discord age + join age + account-created-recently could
naïvely triple-count). The engine collapses them.

A separate **correlation bonus** fires when *independent* families trigger
together — e.g. Discord + Roblox + Behavior all firing is far more significant
than any one of them alone.

### The network layer is off — by design

> **The bot does not collect, store, or transmit IP addresses.**

Discord does not expose member IPs to bots. The only way to obtain them is
to route users through a browser OAuth flow — which this bot intentionally
does not do.

The 8 network detectors (VPN, proxy, Tor, datacenter, IP reputation, etc.)
return `UNAVAILABLE` and contribute **zero risk**. This is not a bug or a
missing feature. It's the correct, privacy-preserving state.

To enable network detection you'd need to:
1. Write a browser OAuth flow
2. Obtain consent to process IPs
3. Contract with a network intelligence provider

For a single community server, none of that is worth it. The Discord +
Roblox + behavior signals catch the raids that matter.

### Redaction

Every log message and moderator panel passes through `RedactionManager`
before display:

| Type | Becomes |
|---|---|
| `192.168.1.100` | `[REDACTED_IP]` |
| `2001:db8::1` | `[REDACTED_IP]` |
| `Bearer eyJhbGc...` | `Bearer [REDACTED_TOKEN]` |
| `api_key=SECRET` | `[REDACTED_SECRET]` |
| `.ROBLOSECURITY=...` | `[REDACTED_COOKIE]` |

Applied at the logging sink, so it catches accidental leaks from anywhere
in the codebase, not just the verification subsystem.

---

## 📋 Command reference

Use `/help` for the interactive dropdown. Full list by category:

<details>
<summary><b>🛡️ Verification</b></summary>

| Command | Purpose |
|---|---|
| `/verification-panel` | Post the public verify panel |
| `/verify` | Start verification (alias of the panel button) |
| `/verify-roblox` | Link your Roblox account |
| `/verify-roblox-status` | Show your linked Roblox account |
| `/verify-unlink` | Unlink your Roblox account |
| `/verify-status <member>` | Show a member's latest assessment |
| `/verify-queue` | List members pending manual review |
| `/verify-review <member>` | Open the review panel |
| `/verify-false-positive <member>` | Mark an assessment as a false positive |
| `/verify-add-signature` | Add an abuse signature |
| `/verify-remove-signature` | Remove an abuse signature |
| `/verification-config` | Show verification configuration |
| `/verification-role <role>` | Set the verified role |
| `/verification-quarantine-role <role>` | Set the quarantine role |

</details>

<details>
<summary><b>🔒 Security</b></summary>

| Command | Purpose |
|---|---|
| `/security` | Dashboard of all security systems |
| `/security-config` | Configure via panel |
| `/antinuke` | Anti-nuke status |
| `/antiraid` | Anti-raid status |
| `/antispam` | Anti-spam status |
| `/automod` | AutoMod status |
| `/automod-word-add <word>` | Add a blocked word |
| `/automod-word-remove <word>` | Remove a blocked word |
| `/serverwatch` | Server Watch status |
| `/lockdown` | Emergency lock every channel |
| `/unlockdown` | Release lockdown |

</details>

<details>
<summary><b>🔨 Moderation</b></summary>

| Command | Purpose |
|---|---|
| `/ban <member>` | Ban with optional message purge |
| `/unban <user_id>` | Unban by ID |
| `/kick <member>` | Kick |
| `/softban <member>` | Ban + unban to clear messages |
| `/timeout <member> <duration>` | Timeout (e.g. `10m`, `2h`, `1d`) |
| `/untimeout <member>` | Remove timeout |
| `/warn <member> <reason>` | Add warning |
| `/unwarn <warning_id>` | Remove warning |
| `/warnings <member>` | List warnings |
| `/purge <amount>` | Bulk delete recent messages |
| `/slowmode <seconds>` | Set channel slowmode |
| `/lock`, `/unlock` | Channel lock/unlock |
| `/nick <member> [nickname]` | Change nickname |
| `/role`, `/role-add`, `/role-remove` | Manage member roles |

</details>

<details>
<summary><b>🎫 Tickets</b></summary>

| Command | Purpose |
|---|---|
| `/ticket-panel` | Open admin console |
| `/tickets-config` | Same as above |
| `/ticket` | Ticket system info |
| `/ticket-add <member>` | Add user to current ticket |
| `/ticket-remove <member>` | Remove user |
| `/ticket-claim` | Claim ticket |
| `/ticket-close` | Close with reason |
| `/ticket-reopen` | Reopen |
| `/ticket-delete` | Delete channel |
| `/ticket-rename <name>` | Rename channel |
| `/ticket-transcript` | Generate transcript |

</details>

<details>
<summary><b>👋 Community & logging</b></summary>

| Command | Purpose |
|---|---|
| `/welcome-config` | Configure welcome / goodbye |
| `/welcome-test` | Preview welcome message |
| `/goodbye-test` | Preview goodbye message |
| `/logging-config` | Route a category to a channel |
| `/logs` | Show current log routing |
| `/audit` | Show last 10 audit log entries |

</details>

<details>
<summary><b>🎭 Roles</b></summary>

| Command | Purpose |
|---|---|
| `/roles-config` | Show configured staff roles |
| `/add-staff-role <role>` | Grant staff commands access |
| `/add-admin-role <role>` | Grant panel access |
| `/remove-staff-role <role>` | Remove either kind |
| `/trust-user <member>` | Exempt from anti-nuke |
| `/untrust-user <member>` | Un-exempt |

</details>

<details>
<summary><b>🧰 Utility</b></summary>

| Command | Purpose |
|---|---|
| `/panel` | Central config control center |
| `/server`, `/serverinfo` | Server summary |
| `/membercount` | Human vs bot count |
| `/roles`, `/channels` | List guild channels/roles |
| `/config` | Show current guild config |
| `/avatar`, `/userinfo` | Member info |
| `/servericon` | Server icon |
| `/ping`, `/uptime`, `/botinfo` | Bot status |
| `/invite` | Invite URL |
| `/permissions` | Your permissions |
| `/roleinfo <role>` | Role details |

</details>

<details>
<summary><b>🔧 Owner</b></summary>

| Command | Purpose |
|---|---|
| `/sync` | Re-sync commands to this guild |
| `/resync-global` | Clear and re-sync global commands |

Owner-only. Uses Discord's application owner record — not a hardcoded ID.

</details>

---

## ⚙️ Environment variables

Full reference for `.env`:

```env
# ─── Discord ────────────────────────────────────────────────
DISCORD_TOKEN=your_bot_token_here
DEV_GUILD_ID=                  # Set for instant command sync (testing only)

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

# ─── Verification ───────────────────────────────────────────
VERIFY_SESSION_TIMEOUT=900     # Session lifetime in seconds
# Network provider is intentionally unset — see Privacy section
```

> ⚠️ **Never commit `.env`.** It's already in `.gitignore`.

---

## 💾 Database

SQLite via aiosqlite. WAL mode. Migrations run automatically on startup.

### Base tables

```
guild_config        staff_roles          trusted_users
warnings            mod_actions          incidents
watch_events        ignore_channels      automod_words
ticket_panels       ticket_categories    tickets
ticket_ratings
```

### Verification tables

```
verification_sessions     verification_attempts    risk_assessments
roblox_links              network_events           account_history
account_clusters          manual_reviews           security_events
ban_history               abuse_signatures         pending_reviews
```

### Backups

> **Back up `data/bot.db` regularly.**
>
> It holds every ban record, warning, verification assessment, and abuse
> signature. Free hosts occasionally lose files. A weekly download via
> File Manager is enough.

---

## 🔑 Permissions

Two centralized checks used everywhere. Never duplicated.

### `@is_guild_admin()`

Grants access if the user is:

- Server owner, **or**
- Has **Administrator** or **Manage Guild**, **or**
- Has a role registered via `/add-admin-role`

### `@is_moderator()`

Grants access if the user is:

- Any of the above, **or**
- Has **Moderate Members**, **Manage Messages**, **Kick Members**, or **Ban Members**, **or**
- Has a role registered via `/add-staff-role`

Both fail closed: no permission → no access, always.

---

## 🔐 Privacy & security posture

This bot is deliberately conservative about user data.

### What we do collect

- Discord user IDs, usernames, display names
- Discord account creation timestamps
- Guild join / leave history (per-guild)
- Roblox account IDs **only if the user voluntarily links them**
- Verification assessments, risk scores, and moderator decisions

### What we do NOT collect

| ❌ Never collected |
|---|
| IP addresses (v4 or v6) |
| MAC addresses |
| Device identifiers |
| Browser fingerprints |
| Discord tokens |
| Roblox cookies or tokens |
| Passwords |
| Keystrokes |
| Private files |
| Precise location |

### Roblox integration

Uses only **public, unauthenticated** Roblox endpoints:

- `users.roblox.com/v1/users/{id}`
- `friends.roblox.com/v1/users/{id}/friends/count`
- `users.roblox.com/v1/usernames/users`

No Roblox credentials are ever requested, transmitted, or stored.

### Redaction

Every log field passes through `RedactionManager` before reaching Discord.
Patterns include IPv4, IPv6, bearer tokens, basic auth, cookies, API keys,
Discord token shapes, `.ROBLOSECURITY`, long hex strings, and emails.

---

## 🗂️ Project layout

```
discord-security-bot/
├── main.py                          # entry point
├── requirements.txt
├── .env.example
├── .gitignore
├── README.md
├── CHANGELOG.md
├── LICENSE
├── CONTRIBUTING.md
│
├── bot/
│   ├── config.py                    # env loader
│   │
│   ├── core/                        # shared infrastructure
│   │   ├── bot.py                   # SecurityBot class
│   │   ├── checks.py                # permission system
│   │   ├── embeds.py                # branded embed factory
│   │   ├── errors.py                # global error handler
│   │   ├── paginator.py
│   │   └── utilities.py
│   │
│   ├── database/                    # base schema + async wrapper
│   │   ├── database.py
│   │   └── migrations.py
│   │
│   ├── services/                    # business logic
│   │   ├── config_service.py
│   │   ├── logging_service.py
│   │   ├── moderation_service.py
│   │   ├── ticket_service.py
│   │   ├── security_service.py
│   │   └── raid_service.py
│   │
│   ├── views/                       # UI components
│   │   ├── common.py
│   │   └── panel.py
│   │
│   ├── cogs/                        # feature modules
│   │   ├── panel.py
│   │   ├── verification.py
│   │   ├── tickets.py
│   │   ├── moderation.py
│   │   ├── welcome.py
│   │   ├── automod.py
│   │   ├── antispam.py
│   │   ├── antiraid.py
│   │   ├── antinuke.py
│   │   ├── logging.py
│   │   ├── server_watch.py
│   │   ├── security.py
│   │   ├── roles.py
│   │   ├── utility.py
│   │   ├── information.py
│   │   └── owner.py
│   │
│   └── verification/                # verification subsystem
│       ├── service.py               # orchestrator
│       ├── detectors.py             # 40 detectors
│       ├── engines.py               # confidence / correlation / clusters
│       ├── risk.py                  # scoring + 5 layers
│       ├── session.py               # state machine
│       ├── providers.py             # Roblox / Network interfaces
│       ├── db.py                    # verification schema + repo
│       ├── rate_limit.py
│       └── redaction.py
│
└── data/
    └── bot.db                       # created on first run
```

---

## 🛠️ Development

### Adding a cog

1. Create `bot/cogs/your_feature.py`
2. Define a `commands.Cog` subclass
3. Add an `async def setup(bot)` at the bottom
4. Append `"bot.cogs.your_feature"` to `INITIAL_COGS` in `bot/core/bot.py`
5. Restart, then run `/sync` to push it live

### Code conventions

- **Business logic goes in `services/`** — cogs stay thin
- **Permission checks use `@is_guild_admin()` or `@is_moderator()`** — never inline
- **Never log or emit user-controlled strings without passing through `RedactionManager`**
- **Async everywhere** — no blocking calls in event handlers
- **Type hints** on all new function signatures

### Testing locally

There's no automated test suite (deliberate — see Known limitations). Test by
running the bot against a throwaway server and walking through:

1. Post `/verification-panel`, click Start Verification on an alt
2. Verify the log channel gets a "Verification Passed" embed
3. Ban the alt, rejoin with a fresh account using the same avatar
4. `/verify-status @alt` — ban evasion detector should fire
5. `/verify-queue` — should list any quarantined members

---

## ⚠️ Known limitations

Honest list. Every one of these is a deliberate trade-off, not an oversight.

- **Network detection is disabled.** The bot does not collect IPs. The 8
  network detectors return `UNAVAILABLE`. See the Privacy section.
- **Behavior tracker is in-memory.** Join-burst and verification-burst
  baselines reset when the bot restarts. On a stable host this is rare; on a
  free host with frequent restarts, expect some loss of session history.
- **Roblox public API can rate-limit.** Under a genuine raid (10+ concurrent
  verifications), Roblox's unauthenticated endpoints may return 429. Detectors
  will return `UNAVAILABLE` for those users, contributing zero risk.
- **Verification sessions in a terminal state don't survive hard restarts.**
  In-flight sessions are restored; completed/rejected ones are not. In
  practice this is invisible to users.
- **No automated test suite.** Testing is manual. This is a trade-off made for
  speed on a single-server deployment.

---

## 📜 License

MIT — see [LICENSE](./LICENSE).

<div align="center">

---

**Built for a community that wanted a bot that actually works.**

</div>
