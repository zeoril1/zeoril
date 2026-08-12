"""Централизованные пути проекта.

Все модули берут пути отсюда, чтобы не зависеть от своего расположения
(модули живут в app/, а данные — в корне проекта).
"""
from __future__ import annotations

from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent

MUSIC_DIR = ROOT_DIR / 'music'
RESOURCES_DIR = ROOT_DIR / 'resources'
LOGS_FILE = RESOURCES_DIR / 'logs.txt'
BOT_HEARTBEAT_FILE = RESOURCES_DIR / 'bot_heartbeat.txt'
CONFIG_TOKEN_FILE = RESOURCES_DIR / 'config_token.txt'
