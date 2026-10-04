"""Entry point for the Discord Security Bot."""
from __future__ import annotations

import asyncio
import logging

from bot.config import Config
from bot.core.bot import SecurityBot


def setup_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="[%(asctime)s] [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


async def main() -> None:
    config = Config.load()
    setup_logging(config.log_level)

    bot = SecurityBot(config)
    async with bot:
        await bot.start(config.token)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
