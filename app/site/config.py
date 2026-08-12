"""Статус бота и блокирующее окно ввода токена конфиг-сервиса.

Бот периодически пишет время в resources/bot_heartbeat.txt (общий volume).
"""
from __future__ import annotations

import time
from pathlib import Path

from app import config_service
from app.paths import BOT_HEARTBEAT_FILE

BOT_HEARTBEAT_TTL = int(config_service.get('BOT_HEARTBEAT_TTL') or '60')


def bot_is_alive() -> bool:
    """Жив ли процесс бота (по времени последнего heartbeat)."""
    try:
        ts = float(Path(BOT_HEARTBEAT_FILE).read_text(encoding='utf-8').strip())
    except (OSError, ValueError):
        return False
    return (time.time() - ts) <= BOT_HEARTBEAT_TTL


def config_needs_action() -> bool:
    """Нужно ли блокирующее окно: конфиг недоступен, а бот ещё не поднялся."""
    return not config_service.is_available() and not bot_is_alive()


def _read_token_from_request():
    """Достаёт токен из form-data или JSON-тела запроса."""
    from flask import request
    token = request.form.get('token')
    if token:
        return token
    payload = request.get_json(silent=True)
    if isinstance(payload, dict):
        return payload.get('token')
    return None
