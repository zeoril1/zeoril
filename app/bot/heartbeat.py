"""Heartbeat: процесс бота жив.

Периодически пишем время в resources/bot_heartbeat.txt (общий volume с сайтом).
"""
from __future__ import annotations

import asyncio
import logging
import os
import time

from app.paths import BOT_HEARTBEAT_FILE

logger = logging.getLogger('discord_bot')

HEARTBEAT_INTERVAL = 15


async def heartbeat_loop() -> None:
    """Каждые HEARTBEAT_INTERVAL секунд обновляет файл heartbeat."""
    try:
        os.makedirs(os.path.dirname(BOT_HEARTBEAT_FILE), exist_ok=True)
    except OSError:
        pass
    while True:
        try:
            with open(BOT_HEARTBEAT_FILE, 'w', encoding='utf-8') as f:
                f.write(str(time.time()))
        except OSError as exc:
            logger.warning('Не удалось обновить heartbeat: %s', exc)
        await asyncio.sleep(HEARTBEAT_INTERVAL)
