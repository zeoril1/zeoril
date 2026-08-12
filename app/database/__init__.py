"""Общий слой доступа к PostgreSQL для бота и сайта.

Строки возвращаются через RealDictCursor (доступ по имени колонки),
плейсхолдеры — ``%s``. Параметры подключения берутся только из
конфиг-сервиса (проект ``postgress``).

Реализация разбита на тематические модули:
  * connection     — строка подключения, connect/db/execute;
  * schema         — создание таблиц и миграции;
  * users          — список серверов пользователей;
  * logging_db     — журнал действий и сообщений;
  * destiny_*      — Destiny 2: предметы, челленджи, сохранённые игры.
"""
from __future__ import annotations

from app.database.connection import DATABASE_URL, connect, db, execute
from app.database.schema import SCHEMA_STATEMENTS, ensure_schema
from app.database.users import (
    add_user_server, get_user_servers, parse_servers, remove_user_server,
)
from app.database.logging_db import (
    get_recent_actions, get_recent_messages, log_message, log_user_action,
)
from app.database.destiny_challenges import (
    get_destiny_challenges, get_destiny_roulette_pool,
    get_random_destiny_challenge, update_destiny_challenge,
)
from app.database.destiny_games import (
    get_destiny_game, get_destiny_games, save_destiny_game,
)

__all__ = [
    'DATABASE_URL', 'SCHEMA_STATEMENTS',
    'connect', 'db', 'execute', 'ensure_schema',
    'parse_servers', 'get_user_servers', 'add_user_server', 'remove_user_server',
    'log_user_action', 'log_message', 'get_recent_actions', 'get_recent_messages',
    'update_destiny_challenge', 'get_destiny_challenges',
    'get_destiny_roulette_pool', 'get_random_destiny_challenge',
    'save_destiny_game', 'get_destiny_games', 'get_destiny_game',
]
