"""Работа с пользователями сервера в БД."""
from __future__ import annotations

import json
import logging

from app import database

logger = logging.getLogger('discord_bot')


def get_user_song(user_id: int) -> str | None:
    """Возвращает имя mp3-файла пользователя (или None)."""
    with database.db() as conn:
        row = database.execute(
            conn, 'SELECT song FROM users WHERE id = %s', (user_id,)
        ).fetchone()
        return row['song'] if row else None


def update_guild_members(guild) -> int:
    """Обновляет в БД список участников сервера (guild).

    Для каждого участника создаётся или обновляется запись в Users:
    - ID — Discord ID участника;
    - Name_discord — текущий ник (display_name);
    - в колонку Servers добавляется ID этого сервера (их может быть несколько).

    Возвращает количество обработанных участников.
    """
    updated = 0
    guild_id = str(guild.id)
    with database.db() as conn:
        for member in guild.members:
            if member.bot:
                continue
            row = database.execute(
                conn,
                'SELECT id, name_discord, servers FROM users WHERE id = %s',
                (member.id,),
            ).fetchone()

            if row is None:
                database.execute(
                    conn,
                    'INSERT INTO users (id, name_discord, servers) '
                    'VALUES (%s, %s, %s)',
                    (member.id, member.display_name, json.dumps([guild_id])),
                )
            else:
                servers = database.parse_servers(row['servers'])
                if guild_id not in servers:
                    servers.append(guild_id)
                    database.execute(
                        conn,
                        'UPDATE users SET servers = %s WHERE id = %s',
                        (json.dumps(servers), member.id),
                    )
                if row['name_discord'] != member.display_name:
                    database.execute(
                        conn,
                        'UPDATE users SET name_discord = %s WHERE id = %s',
                        (member.display_name, member.id),
                    )
            updated += 1

    logger.info('Список участников сервера %s (%s) обновлён: %d',
                guild.name, guild_id, updated)
    return updated
