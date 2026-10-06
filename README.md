<div align="center">

# 🛡️ Discord Security Bot

**A modular, database-backed Discord security & community-management bot.**

Built for a single community server that wants real moderation, real
tickets, and real alt detection — without collecting user IPs.

[![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![discord.py](https://img.shields.io/badge/discord.py-2.x-5865F2?logo=discord&logoColor=white)](https://discordpy.readthedocs.io/)
[![SQLite](https://img.shields.io/badge/SQLite-aiosqlite-003B57?logo=sqlite&logoColor=white)](https://aiosqlite.omnilib.dev/)
[![Detectors](https://img.shields.io/badge/Detectors-45-22c55e)](#-verification-system)
[![License](https://img.shields.io/badge/License-MIT-22c55e)](./LICENSE)

</div>

---

## 📖 Table of contents

- [What is this](#-what-is-this)
- [Feature highlights](#-feature-highlights)
- [Quick start](#-quick-start)
- [First-time setup](#-first-time-setup)
- [Verification system](#-verification-system)
- [Why this beats generic verifiers](#-why-this-beats-generic-verifiers)
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
| 🛡️ **Verification** | **45-detector** alt & raid detection engine, 5 risk layers |
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
- 🔍 **45 detectors** across Discord, Behavior, Roblox, Network, Historical, and Correlation families
- 🧠 Correlation engine — independent signals score together, duplicates collapse
- ⭐ **Trust signals** — verified badges and account prestige reduce risk score
- 🎮 Roblox account linking via public Roblox APIs (no credentials, no cookies)
- 👥 Ban-evasion detection via avatar and name fingerprints
- 🕸️ Account clustering for coordinated alt rings
- 🔤 Username similarity detection (`genesis1` / `genesis2` / `g_enesis`)
- ⏱️ Verification latency behavioral signal (bots click in seconds)
- 🔗 Discord-Roblox account creation delta (coordinated alt creation)
- 🚨 **Raid mode** — auto-tightening thresholds with admin alerts
- 📋 Moderator review panels that survive bot restarts
- 📊 `/verify-queue` work list for pending reviews
- 📈 `/verify-stats` honest activity dashboard
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
git clone https://github.com/genesis26s/discord-moderation-bot-template
cd discord-moderation-bot-template

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
/verify-set-raid-channel      channel:#raid-alerts
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
  ┌───────────────────────────────────────┐
  │  45 detectors run in parallel         │
  │  ├─ Discord       (12)                │
  │  ├─ Behavior      (12)                │
  │  ├─ Roblox         (8)                │
  │  ├─ Network        (8) — UNAVAILABLE  │
  │  ├─ Historical     (4)                │
  │  └─ Correlation    (1)                │
  └───────────────────────────────────────┘
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

### The 45 detectors

<details>
<summary><b>Discord signals (12)</b></summary>

| # | Detector | What it catches |
|---|---|---|
| 1 | `DISCORD_ACCOUNT_AGE` | Fresh Discord account |
| 2 | `DISCORD_ACCOUNT_UNUSUALLY_NEW` | Sub-24h accounts |
| 3 | `SERVER_JOIN_AGE` | Fresh join |
| 4 | `RECENT_USERNAME_CHANGE` | Identity churn |
| 5 | `RECENT_DISPLAY_NAME_CHANGE` | Identity churn |
| 6 | `AVATAR_REUSE` | Same avatar on multiple accounts |
| 7 | `LOW_PROFILE_ACTIVITY` | ⚠️ UNAVAILABLE (Discord API limit) |
| 8 | `MUTUAL_SERVER_PATTERN` | Shared guild density |
| 9 | `KNOWN_BAD_ACCOUNT_CORRELATION` | Matches fingerprints of previously actioned accounts |
| 10 | `ACCOUNT_CLUSTER_PATTERN` | Part of an alt cluster |
| **41** | **`DISCORD_PUBLIC_FLAGS`** | ⭐ **Trust signal** — Early Supporter, Bug Hunter, Partner |
| **42** | **`SNOWFLAKE_PRECISION`** | **Hour-precise account age** |

</details>

<details>
<summary><b>Behavior signals (12)</b></summary>

| # | Detector | What it catches |
|---|---|---|
| 11 | `JOIN_BURST` | Join velocity spike |
| 12 | `VERIFICATION_BURST` | Verification velocity spike |
| 13 | `REPEATED_VERIFICATION_FAILURE` | Repeated failures |
| 14 | `UNUSUAL_VERIFICATION_SPEED` | Suspiciously fast completion |
| 15 | `UNUSUAL_VERIFICATION_DELAY` | Very long delay |
| 16 | `NEW_ACCOUNT_JOIN_WAVE` | Fresh accounts joining together |
| 17 | `POST_JOIN_BEHAVIOR` | Mass mention / mass message |
| 18 | `ROLE_ESCALATION_PATTERN` | Rapid role accumulation |
| 19 | `REJOIN_PATTERN` | Multiple rejoins |
| 20 | `BAN_EVASION_PATTERN` | Fingerprint match on previously banned account |
| **43** | **`USERNAME_PATTERN_CLUSTER`** | **`genesis1` / `genesis2` / `g_enesis` similarity** |
| **44** | **`VERIFICATION_LATENCY_DELTA`** | **Click latency after join** |

</details>

<details>
<summary><b>Roblox signals (8)</b></summary>

| # | Detector | What it catches |
|---|---|---|
| 21 | `ROBLOX_ACCOUNT_AGE` | Fresh Roblox account |
| 22 | `ROBLOX_ACTIVITY_LEVEL` | Zero-friend long-lived account |
| 23 | `ROBLOX_ACCOUNT_REUSE` | Roblox linked to multiple Discord accounts |
| 24 | `ROBLOX_DISCORD_LINK_HISTORY` | Discord linked to multiple Roblox accounts |
| 25 | `ROBLOX_PROFILE_ANOMALY` | Empty profile + new |
| 26 | `ROBLOX_VERIFICATION_FAILURES` | Repeated failures |
| 27 | `ROBLOX_LINK_BURST` | Rapid link attempts |
| 28 | `ROBLOX_CLUSTER_CORRELATION` | Roblox account shared across a cluster |

</details>

<details>
<summary><b>Network signals (8) — UNAVAILABLE by default</b></summary>

| # | Detector | What it needs |
|---|---|---|
| 29 | `VPN_DETECTED` | IP address |
| 30 | `PROXY_DETECTED` | IP address |
| 31 | `DATACENTER_ASN` | IP address |
| 32 | `IP_REPUTATION` | IP address |
| 33 | `TOR_DETECTED` | IP address |
| 34 | `NETWORK_RISK_SCORE` | IP address |
| 35 | `IP_VERIFICATION_VELOCITY` | Pseudonymous IP hash |
| 36 | `INFRASTRUCTURE_CLUSTER` | Pseudonymous IP hash |

**See the [Privacy section](#-privacy--security-posture) for why these are off.**

</details>

<details>
<summary><b>Historical & Correlation signals (5)</b></summary>

| # | Detector | What it catches |
|---|---|---|
| 37 | `PREVIOUS_SERVER_HISTORY` | Repeated leave/join |
| 38 | `PREVIOUS_VERIFICATION_HISTORY` | Prior quarantine |
| 39 | `CROSS_SIGNAL_CORRELATION` | Multiple independent families firing |
| 40 | `KNOWN_ABUSE_PATTERN` | Matches recorded abuse signatures |
| **45** | **`CROSS_ACCOUNT_AGE_DELTA`** | **Discord + Roblox created within hours of each other** |

</details>

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
together — Discord + Roblox + Behavior all firing is far more significant
than any one of them alone.

### Trust signals

New in this version: detectors can produce **negative** scores. When a member
has a verifiable Discord badge — Early Supporter (pre-2018 account), Bug
Hunter, Discord Partner, Certified Moderator, Active Developer — the risk
engine subtracts from their score.

The subtraction is capped at the family level, so a single trust signal can
never fully mask genuine risk signals from other families. It's a tiebreaker,
not a free pass.

### Raid mode

When 3+ CRITICAL assessments happen within 10 minutes, raid mode activates
automatically for 20 minutes:

- Alert posted to `#raid-alerts` with `@here` ping
- New-account thresholds tighten internally
- Extremely fresh accounts auto-quarantine on join

Manual control:

```
/verify-raid-mode action:activate minutes:30
/verify-raid-mode action:status
/verify-raid-mode action:deactivate
```

### Why the Network family is UNAVAILABLE

The **Network** family checks IP-based signals: VPN, proxy, Tor exit nodes,
datacenter ASNs, and IP reputation. **Discord does not give bots member IPs** —
not on join, not through any API, ever.

Getting IPs requires routing users through a browser OAuth flow. This bot
intentionally avoids that, so 8 detectors sit at `UNAVAILABLE` and contribute
**zero risk**.

This is not a missing feature. It's a design choice: no IP collection, no
browser hops, no third-party data sharing.

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

## 🏆 Why this beats generic verifiers

If you've looked at other verification bots, you've seen claims like
**"98% detection rate"**, **"VPN blocking"**, and **"device fingerprinting"**.
Here's an honest comparison.

### How those other bots work

```
  User clicks "Verify" in Discord
        ↓
  Bot DMs a web link
        ↓
  User opens the link in a browser   ← their IP is captured HERE
        ↓
  Web page runs JavaScript            ← device fingerprint collected HERE
        ↓
  Result checked against their global database of bans
        ↓
  Verdict returned to Discord
```

Their detection rate comes from two things:

1. **The OAuth flow** — how they get IPs and device fingerprints
2. **Cross-server aggregation** — bans from hundreds of thousands of servers pooled together

The algorithm isn't magic. The data network is.

### How this bot works

```
  User clicks "Verify" in Discord
        ↓
  45 detectors run on Discord + Roblox data only
        ↓
  Risk engine produces a verdict
        ↓
  Role granted or review requested
```

No browser. No IP. No third party. No data sharing.

### Head-to-head

| Aspect | Generic verifiers | This bot |
|---|---|---|
| **Friction** | Web link → browser → return | Click a button in Discord |
| **Privacy** | Collects IPs, device fingerprints | Collects only Discord + voluntary Roblox data |
| **Third parties** | Feeds your bans to their global DB | Never shares data with anyone |
| **Discord badges** | Not emphasized | Native — Early Supporter is impossible to fake |
| **Hour-precise account age** | Not exposed | Yes |
| **Username similarity clustering** | Not a headline feature | Native |
| **Verification latency behavioral signal** | Not used | Yes |
| **Discord-Roblox creation delta** | Not used | Yes |
| **Trust signal scoring** | Rare | Native (negative scores) |
| **Cross-server correlation** | ✅ Strong | ❌ Can't replicate |
| **VPN / proxy / Tor detection** | ✅ Uses IPs | ❌ Can't without IPs |
| **Cost** | Monthly subscription | Free |

**You don't beat them at their game.** You play a different game where you're
stronger: user friction is zero, data never leaves your server, and you use
signals that only Discord exposes natively (badges, hour-precise timestamps,
username clustering) which other bots ignore because they've built everything
around IP aggregation.

The trade-off is real: you will miss sophisticated attackers who have
5-year-old Discord + Roblox accounts and residential proxies. But that's not
your threat model — your threat model is alt-farming raids, ban evasion, and
coordinated fresh-account waves. Those are covered.

### What you get with `/verify-stats`

An honest dashboard that other verifiers don't offer:

```
  Verification Statistics
  ───────────────────────────────────
  Activity
    Last 24h: 12
    Last 7d: 87

  Risk breakdown (7d)
    🟢 LOW: 71 (81.6%)
    🟡 GUARDED: 11 (12.6%)
    🟠 ELEVATED/HIGH: 3 (3.4%)
    ⛔ CRITICAL: 2 (2.3%)

  Moderator review (7d)
    Quarantined: 4
    Approved: 2
    Rejected: 1
    Marked false positive: 1

  Moderator-confirmed accuracy
    66.7% of reviewed quarantines were approved
    Based on 3 reviews. Not a marketing number —
    a measurement of your server's actual outcomes.

  Top triggered detectors (7d)
    DISCORD_ACCOUNT_AGE: 41
    VERIFICATION_LATENCY_DELTA: 28
    CROSS_ACCOUNT_AGE_DELTA: 12
```

No "98%" — because nobody can prove that. Just what actually happened on
your server.

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
| `/verify-raid-mode <action>` | Activate / deactivate / status raid mode |
| `/verify-set-raid-channel <channel>` | Set the raid alert channel |
| `/verify-stats` | Show verification statistics |
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
- Avatar and username **hashes** (one-way, not reversible to the original URL/text)

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

### Why no IPs

Adding IP detection would mean:

1. Adding a browser OAuth flow (users leave Discord, verify on a website)
2. Storing or processing IP addresses
3. Contracting with an external network intelligence provider

For a single community server, none of that is worth it. The 45-detector
engine, minus the 8 network detectors, catches the attacks that actually
happen: alt-farming raids, ban evasion, coordinated fresh-account waves.

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
│       ├── detectors.py             # 45 detectors
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

### Adding a detector

1. Subclass `Detector` in `bot/verification/detectors.py`
2. Set `id`, `family`, `evidence_type`, `default_weight`
3. Implement `async def evaluate(ctx) -> DResult`
4. Return `self._ok(...)`, `self._unavailable(...)`, `self._unknown(...)`, or `self._error(...)`
5. Append an instance to `ALL_DETECTORS`

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
6. `/verify-stats` — should show non-zero activity
7. `/verify-raid-mode action:status` — should show inactive

---

## ⚠️ Known limitations

Honest list. Every one of these is a deliberate trade-off, not an oversight.

- **Network detection is disabled.** The bot does not collect IPs. The 8
  network detectors return `UNAVAILABLE`. See the Privacy section.
- **Behavior tracker is in-memory.** Join-burst and verification-burst
  baselines reset when the bot restarts. On a stable host this is rare; on a
  free host with frequent restarts, expect some loss of session history.
- **Raid mode state is in-memory.** Resets on restart. The 20-minute expiry
  is short enough that this is rarely visible.
- **Roblox public API can rate-limit.** Under a genuine raid (10+ concurrent
  verifications), Roblox's unauthenticated endpoints may return 429. Detectors
  will return `UNAVAILABLE` for those users, contributing zero risk.
- **Verification sessions in a terminal state don't survive hard restarts.**
  In-flight sessions are restored; completed/rejected ones are not. In
  practice this is invisible to users.
- **No automated test suite.** Testing is manual. This is a trade-off made for
  speed on a single-server deployment.
- **No cross-server correlation.** What one verifier flags on another server
  has no effect here. Your ban list is yours alone.

---

## 📜 License

MIT — see [LICENSE](./LICENSE).

<div align="center">

---

**Built for a community that wanted a bot that actually works.**

45 detectors · Zero IP collection · No third-party data sharing

</div>
