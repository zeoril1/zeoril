"""Запуск Discord-бота."""
from __future__ import annotations

import asyncio
import logging
import time

from discord.errors import DiscordServerError

from app.logging import setup_logging
from app.bot import config
from app.bot.client import create_bot
from app.bot.heartbeat import heartbeat_loop

logger = logging.getLogger('discord_bot')


async def bot_main() -> None:
    """Запускает heartbeat и клиента Discord."""
    asyncio.create_task(heartbeat_loop())
    client = create_bot()
    await client.start(config.DISCORD_BOT_TOKEN)


def start() -> None:
    delay = 5
    while True:
        try:
            asyncio.run(bot_main())
            return
        except DiscordServerError as exc:
            logger.warning('Discord API временно недоступен (%s). '
                           'Повторный запуск через %d с...', exc, delay)
        except Exception:
            logger.exception('Неожиданная ошибка при запуске бота')
            time.sleep(delay)
        delay = min(delay * 2, 60)


if __name__ == '__main__':
    setup_logging('discord_bot')
    start()
