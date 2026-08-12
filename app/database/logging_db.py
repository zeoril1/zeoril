"""Логирование действий и сообщений пользователей в БД."""
from __future__ import annotations

from datetime import datetime, timezone

from app.database.connection import db, execute


def log_user_action(user_id, action: str, *, id_guild=None, guild_name=None,
                    target_id=None, target_name=None, details=None) -> None:
    """Записывает действие пользователя Discord в таблицу user_actions.

    ``action`` — короткий код: voice_join / voice_leave / voice_move /
    guild_join / guild_leave / song_play / message_send / message_delete
    / message_edit. Вызывается ботом из потока (asyncio.to_thread).
    """
    with db() as conn:
        execute(
            conn,
            """INSERT INTO user_actions
               (id_user, id_guild, guild_name, action, target_id,
                target_name, details)
               VALUES (%s, %s, %s, %s, %s, %s, %s)""",
            (user_id, id_guild, guild_name, action, target_id,
             target_name, details),
        )


def log_message(user_id, message_id, channel_id, content: str | None = None,
                date: str | None = None, *, id_guild=None,
                guild_name=None) -> None:
    """Записывает сообщение пользователя в таблицу messages."""
    if date is None:
        date = datetime.now(timezone.utc).isoformat()
    with db() as conn:
        execute(
            conn,
            """INSERT INTO messages
               (id, id_user, date, id_channel, content, id_guild, guild_name)
               VALUES (%s, %s, %s, %s, %s, %s, %s)
               ON CONFLICT (id) DO UPDATE SET content = EXCLUDED.content""",
            (message_id, user_id, date, channel_id, content,
             id_guild, guild_name),
        )


def get_recent_actions(limit: int = 200) -> list[dict]:
    """Возвращает последние действия пользователей (с именами из users)."""
    limit = max(1, min(int(limit), 1000))
    with db() as conn:
        rows = execute(
            conn,
            """SELECT a.id, a.id_user, a.id_guild, a.guild_name, a.action,
                      a.target_id, a.target_name, a.details, a.date,
                      COALESCE(u.name_discord, a.target_name, '—')
                          AS user_name
               FROM user_actions a
               LEFT JOIN users u ON u.id = a.id_user
               ORDER BY a.date DESC
               LIMIT %s""",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]


def get_recent_messages(limit: int = 200) -> list[dict]:
    """Возвращает последние сообщения пользователей (с именами из users)."""
    limit = max(1, min(int(limit), 1000))
    with db() as conn:
        rows = execute(
            conn,
            """SELECT m.id, m.id_user, m.date, m.id_channel, m.content,
                      m.id_guild, m.guild_name,
                      COALESCE(u.name_discord, '—') AS user_name
               FROM messages m
               LEFT JOIN users u ON u.id = m.id_user
               ORDER BY m.date DESC
               LIMIT %s""",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]
