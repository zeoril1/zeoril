"""Состояние лобби: создание, вход/выход, ходы, завершение игры."""
from __future__ import annotations

import queue
import secrets
import time

from app import database
from app.site.destiny_game.blueprint import (LOBBY_TTL, _broadcast, _lobbies,
                                             _lock, logger)


class Lobby:
    """Состояние одной игровой комнаты."""

    def __init__(self, lobby_id: str, name: str, owner_id: str,
                 owner_name: str) -> None:
        self.id = lobby_id
        self.name = name
        self.owner_id = owner_id
        self.owner_name = owner_name
        # uid(str) -> {'id', 'name'}
        self.members: dict[str, dict] = {}
        self.order: list[str] = []      # порядок ходов после «перемешать»
        self.current_index = 0
        self.rolling = False
        self.current_roll: dict | None = None
        self.history: list[dict] = []
        # Результаты текущего круга: по одной записи на игрока.
        self.round_results: list[dict] = []
        # True, когда все игроки круга уже прокрутили колесо.
        self.round_done = False
        # Очередь запросов на реролл (uid), ожидающих одобрения владельца.
        self.reroll_pending: list[str] = []
        # uid, для которого владелец одобрил реролл (идёт ролл).
        self.reroll_active: str | None = None
        # Лобби закрыто (игра завершена).
        self.closed = False
        self.last_activity = time.time()
        self.subscribers: list[queue.Queue] = []


def _create_lobby(user: dict, name: str) -> Lobby:
    uid = str(user['id'])
    uname = user.get('name_discord') or uid
    lobby_id = secrets.token_hex(4)
    while lobby_id in _lobbies:
        lobby_id = secrets.token_hex(4)
    lobby = Lobby(lobby_id, name, uid, uname)
    lobby.members[uid] = {'id': uid, 'name': uname}
    lobby.order = [uid]
    _lobbies[lobby_id] = lobby
    return lobby


def _get_lobby(lobby_id: str | None) -> Lobby | None:
    if not lobby_id:
        return None
    return _lobbies.get(lobby_id)


def _cleanup_lobbies() -> None:
    """Удаляет давно неактивные лобби (не во время рулетки)."""
    now = time.time()
    for lid in list(_lobbies):
        lobby = _lobbies[lid]
        if not lobby.rolling and now - lobby.last_activity > LOBBY_TTL:
            del _lobbies[lid]


def _lobby_state(lobby: Lobby) -> dict:
    """Полное состояние лобби для клиентов (не зависит от запроса)."""
    order = [
        {'id': uid, 'name': lobby.members[uid]['name']}
        for uid in lobby.order
        if uid in lobby.members
    ]
    current = None
    if lobby.order and lobby.order[lobby.current_index] in lobby.members:
        current = lobby.order[lobby.current_index]
    return {
        'id': lobby.id,
        'name': lobby.name,
        'owner_id': lobby.owner_id,
        'owner_name': lobby.owner_name,
        'order': order,
        'current_user_id': current,
        'rolling': lobby.rolling,
        'current_roll': lobby.current_roll,
        'history': lobby.history,
        'round_results': lobby.round_results,
        'round_done': lobby.round_done,
        'reroll': {
            'pending': lobby.reroll_pending,
            'active': lobby.reroll_active,
        },
    }


def _join_lobby(lobby: Lobby, user: dict) -> bool:
    if lobby.closed:
        return False
    uid = str(user['id'])
    if uid in lobby.members:
        lobby.last_activity = time.time()
        return False
    uname = user.get('name_discord') or uid
    lobby.members[uid] = {'id': uid, 'name': uname}
    lobby.order.append(uid)
    lobby.last_activity = time.time()
    return True


def _leave_lobby(lobby: Lobby, uid: str) -> None:
    uid = str(uid)
    if uid not in lobby.members:
        return
    del lobby.members[uid]
    if uid in lobby.order:
        lobby.order.remove(uid)
    if uid in lobby.reroll_pending:
        lobby.reroll_pending.remove(uid)
    if lobby.reroll_active == uid:
        lobby.reroll_active = None
    if not lobby.order:
        lobby.current_index = 0
        return
    # Если вышел создатель — передаём лобби следующему.
    if lobby.owner_id == uid:
        lobby.owner_id = lobby.order[0]
        lobby.owner_name = lobby.members[lobby.order[0]]['name']
    if lobby.current_index >= len(lobby.order):
        lobby.current_index = 0
    # Если вышел тот, чей сейчас ход, — переходим к следующему.
    if lobby.order[lobby.current_index] not in lobby.members:
        _advance_turn(lobby)
    lobby.last_activity = time.time()


def _advance_turn(lobby: Lobby) -> None:
    """Переходит к следующему активному игроку (начиная со следующего)."""
    if not lobby.order:
        lobby.current_index = 0
        return
    n = len(lobby.order)
    for step in range(1, n + 1):
        idx = (lobby.current_index + step) % n
        if lobby.order[idx] in lobby.members:
            lobby.current_index = idx
            return
    lobby.current_index = 0


def _all_rolled(lobby: Lobby) -> bool:
    """True, если каждый активный игрок уже имеет результат в круге."""
    if not lobby.order:
        return False
    have = {r['user_id'] for r in lobby.round_results}
    return all(uid in have for uid in lobby.order if uid in lobby.members)


def _active_lobbies() -> list[dict]:
    """Список текущих игровых сессий для страницы /destiny/game."""
    out = []
    for lid, lobby in _lobbies.items():
        if lobby.closed:
            continue
        out.append({
            'id': lobby.id,
            'name': lobby.name,
            'owner_name': lobby.owner_name,
            'members_count': len(lobby.members),
            'rolling': lobby.rolling,
        })
    out.sort(key=lambda x: x['owner_name'].lower())
    return out


def _end_game(lobby: Lobby) -> int | None:
    """Завершает игру: сохраняет результаты в БД и закрывает лобби."""
    lobby.closed = True
    lobby.rolling = False
    results = lobby.round_results
    game_id = None
    try:
        owner_id = None
        if str(lobby.owner_id).lstrip('-').isdigit():
            owner_id = int(lobby.owner_id)
        game_id = database.save_destiny_game(
            lobby.id, lobby.name, owner_id, lobby.owner_name, results)
    except Exception as exc:
        logger.exception('Не удалось сохранить игру %s: %s', lobby.id, exc)
    _broadcast(lobby, 'game_end', {'game_id': game_id})
    _lobbies.pop(lobby.id, None)
    return game_id
