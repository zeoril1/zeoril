"""Destiny 2: сохранённые игры рулетки (destiny_games)."""
from __future__ import annotations

import json

import psycopg2.extras

from app.database.connection import db, execute


def _parse_results(value) -> list:
    """Приводит значение колонки JSONB results к списку dict.

    psycopg2 2.9 сам парсит JSONB в dict/list, поэтому value может быть
    уже списком; на всякий случай поддерживаем и строку JSON.
    """
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, list) else []
        except (ValueError, TypeError):
            return []
    return []


def save_destiny_game(lobby_id: str, name: str, owner_id, owner_name: str,
                      results: list[dict]) -> int | None:
    """Сохраняет завершённую игру и возвращает её id (или None)."""
    with db() as conn:
        row = execute(
            conn,
            """INSERT INTO destiny_games
               (lobby_id, name, owner_id, owner_name, ended_at, results)
               VALUES (%s, %s, %s, %s, now(), %s)
               RETURNING id""",
            (lobby_id, name, owner_id, owner_name,
             psycopg2.extras.Json(results, dumps=json.dumps)),
        ).fetchone()
        return int(row['id']) if row else None


def get_destiny_games(limit: int = 50, offset: int = 0) -> list[dict]:
    """Возвращает сохранённые игры рулетки (новые сверху)."""
    limit = max(1, min(int(limit), 100))
    offset = max(0, int(offset))
    with db() as conn:
        rows = execute(
            conn,
            """SELECT id, lobby_id, name, owner_id, owner_name,
                      created_at, ended_at, results
               FROM destiny_games
               ORDER BY ended_at DESC
               LIMIT %s OFFSET %s""",
            (limit, offset),
        ).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d['results'] = _parse_results(d.get('results'))
            out.append(d)
        return out


def get_destiny_game(game_id: int) -> dict | None:
    """Возвращает одну сохранённую игру по id (или None)."""
    with db() as conn:
        row = execute(
            conn,
            """SELECT id, lobby_id, name, owner_id, owner_name,
                      created_at, ended_at, results
               FROM destiny_games WHERE id = %s""",
            (int(game_id),),
        ).fetchone()
        if not row:
            return None
        d = dict(row)
        d['results'] = _parse_results(d.get('results'))
        return d
