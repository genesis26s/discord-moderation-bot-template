"""Central configuration loader. All branding/config values live here."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


def _hex_to_int(value: str, default: int) -> int:
    try:
        return int(value, 16) if value.lower().startswith("0x") is False and value.startswith("#") is False else int(value, 16)
    except (ValueError, AttributeError):
        try:
            return int(value, 16)
        except (ValueError, TypeError):
            return default


@dataclass(slots=True)
class Config:
    token: str
    database_path: str

    bot_name: str
    bot_description: str
    bot_status: str
    bot_activity_type: str
    bot_activity: str

    embed_color: int
    success_color: int
    error_color: int
    warning_color: int
    embed_footer: str

    log_level: str

    @classmethod
    def load(cls) -> "Config":
        token = os.getenv("DISCORD_TOKEN", "").strip()
        if not token:
            raise RuntimeError("DISCORD_TOKEN is not set. Copy .env.example to .env and fill it in.")

        db_path = os.getenv("DATABASE_PATH", "data/bot.db")
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)

        return cls(
            token=token,
            database_path=db_path,
            bot_name=os.getenv("BOT_NAME", "Security Bot"),
            bot_description=os.getenv("BOT_DESCRIPTION", "Advanced Discord security & management"),
            bot_status=os.getenv("BOT_STATUS", "online").lower(),
            bot_activity_type=os.getenv("BOT_ACTIVITY_TYPE", "watching").lower(),
            bot_activity=os.getenv("BOT_ACTIVITY", "your server"),
            embed_color=int(os.getenv("EMBED_COLOR", "0x5865F2"), 16),
            success_color=int(os.getenv("SUCCESS_COLOR", "0x57F287"), 16),
            error_color=int(os.getenv("ERROR_COLOR", "0xED4245"), 16),
            warning_color=int(os.getenv("WARNING_COLOR", "0xFEE75C"), 16),
            embed_footer=os.getenv("EMBED_FOOTER", "Security Bot"),
            log_level=os.getenv("LOG_LEVEL", "INFO"),
        )
