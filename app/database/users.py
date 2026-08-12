"""Пользователи: список серверов (колонка users.servers)."""
from __future__ import annotations

import json

from app.database.connection import db, execute


def parse_servers(value: str | None) -> list[str]:
    """Разбирает колонку users.servers (JSON-массив ID серверов) в список."""
    if not value:
        return []
    try:
        data = json.loads(value)
    except (ValueError, TypeError):
        return []
    if not isinstance(data, list):
        return []
    return [str(x) for x in data]


def get_user_servers(user_id) -> list[str]:
    """Возвращает список ID серверов, на которых состоит пользователь."""
    with db() as conn:
        row = execute(
            conn, 'SELECT servers FROM users WHERE id = %s', (user_id,)
        ).fetchone()
    return parse_servers(row['servers']) if row else []


def add_user_server(user_id, server_id) -> None:
    """Добавляет ID сервера в список серверов пользователя."""
    servers = get_user_servers(user_id)
    server_id = str(server_id)
    if server_id in servers:
        return
    servers.append(server_id)
    with db() as conn:
        execute(
            conn,
            'UPDATE users SET servers = %s WHERE id = %s',
            (json.dumps(servers), user_id),
        )


def remove_user_server(user_id, server_id) -> None:
    """Удаляет ID сервера из списка серверов пользователя."""
    servers = get_user_servers(user_id)
    server_id = str(server_id)
    if server_id not in servers:
        return
    servers.remove(server_id)
    with db() as conn:
        execute(
            conn,
            'UPDATE users SET servers = %s WHERE id = %s',
            (json.dumps(servers), user_id),
        )
