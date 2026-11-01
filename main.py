"""Entry point for the Discord Security Bot."""
from __future__ import annotations

import asyncio
import logging

import discord
from bot.config import Config
from bot.core.bot import SecurityBot

log = logging.getLogger(__name__)

def setup_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="[%(asctime)s] [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

async def main() -> None:
    config = Config.load()
    setup_logging(config.log_level)

    while True:
        bot = SecurityBot(config)
        try:
            async with bot:
                await bot.start(config.token)
            return
        except KeyboardInterrupt:
            return
        except discord.errors.PrivilegedIntentsRequired as e:
            log.error("=====================================================")
            log.error("FATAL ERROR: Missing Privileged Intents!")
            log.error("Your bot is trying to use Intents that are not enabled.")
            log.error("You MUST go to the Discord Developer Portal:")
            log.error("1. Go to your Application -> Bot tab.")
            log.error("2. Scroll down to 'Privileged Gateway Intents'.")
            log.error("3. Turn ON 'Server Members Intent' and 'Message Content Intent'.")
            log.error("4. Save changes and restart the bot.")
            log.error("=====================================================")
            return
        except Exception as exc:
            log.error("Bot crashed: %s. Retrying in 30 seconds...", exc)
            try:
                await asyncio.sleep(30)
            except KeyboardInterrupt:
                return

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
