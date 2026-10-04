"""Schema definitions. Runs on every startup; uses IF NOT EXISTS."""
from __future__ import annotations

from bot.database.database import Database

MIGRATIONS: list[str] = [
    # ---- Guild key/value config ----
    """
    CREATE TABLE IF NOT EXISTS guild_config (
        guild_id INTEGER NOT NULL,
        key TEXT NOT NULL,
        value TEXT,
        PRIMARY KEY (guild_id, key)
    )
    """,
    # ---- Staff / admin roles ----
    """
    CREATE TABLE IF NOT EXISTS staff_roles (
        guild_id INTEGER NOT NULL,
        role_id INTEGER NOT NULL,
        kind TEXT NOT NULL DEFAULT 'staff',  -- 'staff' | 'admin'
        PRIMARY KEY (guild_id, role_id, kind)
    )
    """,
    # ---- Trusted users (anti-nuke allowlist) ----
    """
    CREATE TABLE IF NOT EXISTS trusted_users (
        guild_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        PRIMARY KEY (guild_id, user_id)
    )
    """,
    # ---- Warnings ----
    """
    CREATE TABLE IF NOT EXISTS warnings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        guild_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        moderator_id INTEGER NOT NULL,
        reason TEXT,
        created_at INTEGER NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_warnings_guild_user ON warnings (guild_id, user_id)",
    # ---- Moderation log ----
    """
    CREATE TABLE IF NOT EXISTS mod_actions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        guild_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        moderator_id INTEGER NOT NULL,
        action TEXT NOT NULL,
        reason TEXT,
        duration INTEGER,
        created_at INTEGER NOT NULL
    )
    """,
    # ---- Ticket panels ----
    """
    CREATE TABLE IF NOT EXISTS ticket_panels (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        guild_id INTEGER NOT NULL,
        name TEXT NOT NULL,
        channel_id INTEGER,
        message_id INTEGER,
        title TEXT,
        description TEXT,
        color INTEGER,
        banner_url TEXT,
        footer TEXT
    )
    """,
    # ---- Ticket categories ----
    """
    CREATE TABLE IF NOT EXISTS ticket_categories (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        guild_id INTEGER NOT NULL,
        panel_id INTEGER,
        name TEXT NOT NULL,
        emoji TEXT,
        category_id INTEGER,          -- discord category channel id
        support_role_id INTEGER,
        naming_template TEXT DEFAULT 'ticket-{username}',
        max_open_per_user INTEGER DEFAULT 1,
        welcome_message TEXT,
        button_style TEXT DEFAULT 'primary',
        FOREIGN KEY (panel_id) REFERENCES ticket_panels(id) ON DELETE CASCADE
    )
    """,
    # ---- Tickets ----
    """
    CREATE TABLE IF NOT EXISTS tickets (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        guild_id INTEGER NOT NULL,
        channel_id INTEGER NOT NULL UNIQUE,
        category_id INTEGER,
        user_id INTEGER NOT NULL,
        claimed_by INTEGER,
        status TEXT NOT NULL DEFAULT 'open',  -- open | closed
        created_at INTEGER NOT NULL,
        closed_at INTEGER
    )
    """,
    # ---- Security incidents ----
    """
    CREATE TABLE IF NOT EXISTS incidents (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        guild_id INTEGER NOT NULL,
        type TEXT NOT NULL,          -- antinuke | antiraid | antispam | serverwatch
        severity TEXT NOT NULL,      -- LOW | MEDIUM | HIGH | CRITICAL
        executor_id INTEGER,
        details TEXT,
        created_at INTEGER NOT NULL
    )
    """,
    # ---- Server Watch suspicious activity ----
    """
    CREATE TABLE IF NOT EXISTS watch_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        guild_id INTEGER NOT NULL,
        event_type TEXT NOT NULL,
        severity TEXT NOT NULL,
        executor_id INTEGER,
        details TEXT,
        created_at INTEGER NOT NULL
    )
    """,
    # ---- Warnings table name kept as `warnings` for the API ----
    # ---- Premium/ignore lists ----
    """
    CREATE TABLE IF NOT EXISTS ignore_channels (
        guild_id INTEGER NOT NULL,
        channel_id INTEGER NOT NULL,
        feature TEXT NOT NULL,      -- 'antispam' | 'automod' | ...
        PRIMARY KEY (guild_id, channel_id, feature)
    )
    """,
    # ---- Automod word list ----
    """
    CREATE TABLE IF NOT EXISTS automod_words (
        guild_id INTEGER NOT NULL,
        word TEXT NOT NULL,
        PRIMARY KEY (guild_id, word)
    )
    """,
    # ---- Ticket ratings ----
    """
    CREATE TABLE IF NOT EXISTS ticket_ratings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        guild_id INTEGER NOT NULL,
        ticket_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        rating INTEGER NOT NULL,
        comment TEXT,
        created_at INTEGER NOT NULL
    )
    """,
]


async def run_migrations(db: Database) -> None:
    for sql in MIGRATIONS:
        await db.execute(sql)
    await db.execute(
        "CREATE INDEX IF NOT EXISTS idx_incidents_guild_time ON incidents (guild_id, created_at DESC)"
    )
    await db.execute(
        "CREATE INDEX IF NOT EXISTS idx_watch_guild_time ON watch_events (guild_id, created_at DESC)"
    )
