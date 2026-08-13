"""Рулетка челленджей: колесо, выбор челленджа и обработка броска."""
from __future__ import annotations

import random
import secrets
import threading
import time

from app import database
from app.site.bungie import items as manifest_items
from app.site.destiny_game.blueprint import (HISTORY_LIMIT, MAX_WHEEL_ITEMS,
                                             MIN_WHEEL_ITEMS,
                                             ROLL_ANIMATION_SECONDS,
                                             _broadcast, _lobbies, _lock)
from app.site.destiny_game.lobby import (Lobby, _advance_turn, _all_rolled,
                                         _lobby_state)
from app.site.lang import get_lang


def _enrich_challenges(rows: list[dict]) -> list[dict]:
    """Добавляет в строки челленджей имя/иконку из манифеста.

    Имена локализуются по выбранному языку (манифест локали). Строки без
    иконки (предмет не найден в манифесте) отбрасываются — они не нужны
    ни на колесе, ни в результатах.
    """
    hashes = [int(r['item_hash']) for r in rows
              if str(r['item_hash']).isdigit()]
    info = manifest_items.get_items_by_hashes(get_lang(), hashes)
    out: list[dict] = []
    for r in rows:
        it = info.get(int(r['item_hash'])) or {}
        icon = it.get('icon') or ''
        if not icon:
            continue
        out.append({
            'item_hash': r['item_hash'],
            'name': it.get('name') or r.get('item_name') or 'Неизвестно',
            'icon': icon,
            'solo_challenge': r.get('solo_challenge'),
            'team_challenge': r.get('team_challenge'),
            'notes': r.get('notes'),
        })
    return out


def _build_wheel(pool: list[dict], challenge: dict) -> list[dict] | None:
    """Собирает колесо из случайных оружий, гарантированно включая target."""
    target_hash = str(challenge['item_hash'])
    target_item = {
        'hash': challenge['item_hash'],
        'icon': challenge.get('icon') or '',
        'name': challenge.get('name') or 'Неизвестно',
    }
    rest = [
        {
            'hash': it['item_hash'],
            'icon': it.get('icon') or '',
            'name': it.get('name') or 'Неизвестно',
        }
        for it in pool
        if str(it['item_hash']) != target_hash
    ]
    random.shuffle(rest)
    wheel = rest[:MAX_WHEEL_ITEMS - 1]
    if len(wheel) < MIN_WHEEL_ITEMS:
        wheel = wheel[:MIN_WHEEL_ITEMS]
    idx = random.randint(0, len(wheel))
    wheel.insert(idx, target_item)
    return wheel


def _filter_pool(enriched: list[dict], owned: set[int] | None,
                 rolled: set[int] | None) -> list[dict]:
    """Оставляет в пуле только оружие, которое есть у игрока и ещё не выпадало.

    ``owned`` — множество itemHash предметов игрока (что у него есть в
    Destiny 2); если ``None`` — фильтр владения не применяется.
    ``rolled`` — множество itemHash, уже выпадавших игроку в этом лобби;
    такие предметы исключаются.
    """
    out: list[dict] = []
    for c in enriched:
        try:
            h = int(c['item_hash'])
        except (TypeError, ValueError):
            continue
        if owned is not None and h not in owned:
            continue
        if rolled and h in rolled:
            continue
        out.append(c)
    return out


def _pick_challenge(owned: set[int] | None = None,
                    rolled: set[int] | None = None
                    ) -> tuple[dict | None, list[dict]]:
    """Случайный челлендж из пула и сам пул оружия (из манифеста).

    ``owned`` — itemHash предметов, которые есть у игрока (в Destiny 2).
    Если задано, из пула исключается оружие, которого у игрока НЕТ, —
    остаётся только то, что он уже имеет. ``rolled`` — itemHash, уже
    выпадавшие игроку в этом лобби; они тоже исключаются. Если после
    фильтров пул пуст, возвращается ``(None, [])`` — крутить нечего.
    """
    pool = database.get_destiny_roulette_pool()
    enriched = _enrich_challenges(pool)
    if not enriched:
        return None, []
    eligible = _filter_pool(enriched, owned, rolled)
    if not eligible:
        return None, []
    target = random.choice(eligible)
    return target, eligible


def _begin_roll_locked(lobby: Lobby, uid: str, challenge: dict,
                       pool: list[dict], is_reroll: bool = False) -> bool:
    """Запускает ролл (вызывается при захваченном _lock).

    ``is_reroll=True`` — точечный реролл результата конкретного игрока:
    очередь ходов и статус круга при этом не меняются.
    """
    wheel = _build_wheel(pool, challenge)
    if not wheel:
        return False
    roll_id = secrets.token_hex(4)
    member = lobby.members.get(uid) or {}
    roll_data = {
        'roll_id': roll_id,
        'user_id': uid,
        'user_name': member.get('name', 'Игрок'),
        'items': wheel,
        'target_hash': challenge['item_hash'],
        'challenge': {
            'item_hash': challenge['item_hash'],
            'name': challenge.get('name'),
            'icon': challenge.get('icon'),
            'solo_challenge': challenge.get('solo_challenge'),
            'team_challenge': challenge.get('team_challenge'),
            'notes': challenge.get('notes'),
        },
    }
    lobby.current_roll = roll_data
    lobby.last_activity = time.time()
    _broadcast(lobby, 'roll_start', roll_data)

    t = threading.Thread(
        target=_finish_roll,
        args=(lobby, uid, challenge, is_reroll),
        daemon=True,
    )
    t.start()
    return True


def _finish_roll(lobby_ref: Lobby, uid: str, challenge: dict,
                 is_reroll: bool = False) -> None:
    """Фоновая задача: завершает бросок после анимации у игроков.

    При ``is_reroll=True`` результат заменяется только у конкретного игрока
    без сдвига очереди и без пересчёта статуса круга.
    """
    time.sleep(ROLL_ANIMATION_SECONDS)
    with _lock:
        lobby = _lobbies.get(lobby_ref.id)
        if lobby is None or not lobby.rolling or lobby.closed:
            return
        lobby.rolling = False
        lobby.current_roll = None
        lobby.last_activity = time.time()

        entry = {
            'user_id': uid,
            'user_name': (lobby.members.get(uid) or {}).get('name', 'Игрок'),
            'item_hash': challenge['item_hash'],
            'name': challenge.get('name'),
            'icon': challenge.get('icon'),
            'solo_challenge': challenge.get('solo_challenge'),
            'team_challenge': challenge.get('team_challenge'),
            'notes': challenge.get('notes'),
            'reroll': is_reroll,
            'ts': time.time(),
        }
        lobby.history.insert(0, entry)
        del lobby.history[HISTORY_LIMIT:]

        # Запоминаем, что это оружие уже выпадало игроку, — чтобы в
        # следующих бросках оно исключалось из его пула рулетки.
        try:
            lobby.rolled.setdefault(uid, set()).add(int(challenge['item_hash']))
        except (TypeError, ValueError):
            pass

        # Обновляем результат круга для этого игрока (по одному на игрока).
        for i, r in enumerate(lobby.round_results):
            if r['user_id'] == uid:
                lobby.round_results[i] = entry
                break
        else:
            lobby.round_results.append(entry)

        if not is_reroll:
            lobby.round_done = _all_rolled(lobby)
        lobby.reroll_active = None
        lobby.reroll_pending = []
        _broadcast(lobby, 'reroll', {
            'pending': lobby.reroll_pending,
            'active': lobby.reroll_active,
        })
        _broadcast(lobby, 'round', lobby.round_results)

        if not is_reroll:
            _advance_turn(lobby)
        _broadcast(lobby, 'history', lobby.history)
        _broadcast(lobby, 'turn', {
            'user_id': lobby.order[lobby.current_index]
            if lobby.order else None,
        })
        _broadcast(lobby, 'lobby', _lobby_state(lobby))
