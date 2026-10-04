"""Branded embed helpers. All embed creation goes through here."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable, Optional

import discord

from bot.config import Config


class EmbedFactory:
    def __init__(self, config: Config) -> None:
        self.config = config

    def _base(self, color: int, title: Optional[str] = None, description: Optional[str] = None) -> discord.Embed:
        embed = discord.Embed(
            title=title,
            description=description,
            color=color,
            timestamp=datetime.now(timezone.utc),
        )
        embed.set_footer(text=self.config.embed_footer)
        return embed

    def primary(self, title=None, description=None) -> discord.Embed:
        return self._base(self.config.embed_color, title, description)

    def success(self, title=None, description=None) -> discord.Embed:
        return self._base(self.config.success_color, title, description)

    def error(self, title=None, description=None) -> discord.Embed:
        return self._base(self.config.error_color, title, description)

    def warning(self, title=None, description=None) -> discord.Embed:
        return self._base(self.config.warning_color, title, description)

    def add_fields(self, embed: discord.Embed, fields: Iterable[tuple[str, str, bool]]) -> discord.Embed:
        for name, value, inline in fields:
            embed.add_field(name=name, value=value or "—", inline=inline)
        return embed
