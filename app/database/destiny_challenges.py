"""Destiny 2: челленджи экзотического оружия (destiny_challenges).

Здесь хранятся только пользовательские данные челленджей (solo/team/notes).
Имена и иконки предметов берутся из локального манифеста
(``app.site.bungie.items``) на слое сайта.
"""
from __future__ import annotations

from app.database.connection import db, execute


def update_destiny_challenge(item_hash: int, *,
                             solo_challenge: str | None = None,
                             team_challenge: str | None = None,
                             notes: str | None = None) -> bool:
    """Обновляет поля челленджа (solo/team/notes) для указанного item_hash.

    ``None`` в аргументе очищает соответствующее поле. Возвращает True,
    если запись с таким item_hash существует и была обновлена.
    """
    with db() as conn:
        cur = execute(
            conn,
            """UPDATE destiny_challenges
               SET solo_challenge = %s,
                   team_challenge = %s,
                   notes = %s
               WHERE item_hash = %s""",
            (solo_challenge, team_challenge, notes, int(item_hash)),
        )
        return cur.rowcount > 0


def get_destiny_challenges(only_filled: bool = False
                           ) -> tuple[list[dict], int]:
    """Возвращает все челленджи экзотического оружия.

    ``only_filled`` — показывать только предметы с хотя бы одним описанием.

    Возвращает кортеж (записи, всего записей). Имена/иконки предметов сюда
    не включаются — их добавляет слой сайта из манифеста.
    """
    where = 'WHERE 1=1'
    if only_filled:
        where += (" AND (solo_challenge IS NOT NULL"
                  " OR team_challenge IS NOT NULL"
                  " OR notes IS NOT NULL)")

    with db() as conn:
        rows = execute(
            conn,
            """SELECT item_hash, item_name,
                      solo_challenge, team_challenge, notes
               FROM destiny_challenges """ + where + """
               ORDER BY item_name ASC NULLS LAST""",
        ).fetchall()
        result = [dict(r) for r in rows]
        return result, len(result)


def get_destiny_roulette_pool() -> list[dict]:
    """Все оружия с челленджами для колеса рулетки (без иконок).

    В пул попадают только записи с хотя бы одним заполненным текстовым
    полем (solo/team/notes). Иконки/имена добавляет вызывающий код из
    манифеста.
    """
    with db() as conn:
        rows = execute(
            conn,
            """SELECT item_hash, item_name,
                      solo_challenge, team_challenge, notes
               FROM destiny_challenges
               WHERE (solo_challenge IS NOT NULL AND solo_challenge <> %s
                   OR team_challenge IS NOT NULL AND team_challenge <> %s
                   OR notes IS NOT NULL AND notes <> %s)
               ORDER BY item_name ASC NULLS LAST""",
            ('', '', ''),
        ).fetchall()
        return [dict(r) for r in rows]


def get_random_destiny_challenge() -> dict | None:
    """Возвращает случайный челлендж экзотики (или None, если пул пуст).

    Используется в мини-игре: ORDER BY random() + LIMIT 1. Иконки/имена
    добавляет вызывающий код из манифеста.
    """
    with db() as conn:
        row = execute(
            conn,
            """SELECT item_hash, item_name,
                      solo_challenge, team_challenge, notes
               FROM destiny_challenges
               WHERE (solo_challenge IS NOT NULL AND solo_challenge <> %s
                   OR team_challenge IS NOT NULL AND team_challenge <> %s
                   OR notes IS NOT NULL AND notes <> %s)
               ORDER BY random()
               LIMIT 1""",
            ('', '', ''),
        ).fetchone()
        return dict(row) if row else None
