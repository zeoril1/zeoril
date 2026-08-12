"""Конфигурация бота: токен и настройки — только из конфиг-сервиса."""
from __future__ import annotations

import logging

from app import config_service

logger = logging.getLogger('discord_bot')

# Токен — только из конфиг-сервиса. Если его нет (сервис недоступен или
# требует токен) — ждём, пока админ введёт его на сайте.
DISCORD_BOT_TOKEN = config_service.get('DISCORD_BOT_TOKEN')

if not DISCORD_BOT_TOKEN:
    logger.warning(
        'DISCORD_BOT_TOKEN не задан (конфиг-сервис недоступен или требует '
        'токен). Ожидаем, пока токен будет введён на сайте администратором...'
    )
    config_service.wait_for_config()
    DISCORD_BOT_TOKEN = config_service.get('DISCORD_BOT_TOKEN')

if not DISCORD_BOT_TOKEN:
    raise RuntimeError(
        'DISCORD_BOT_TOKEN не задан в конфиг-сервисе (проект "discord"). '
        'Задайте его в конфиг-сервисе и перезапустите бота.'
    )

BOT_USER_ID = int(config_service.get('BOT_USER_ID', '672119705212944385'))
