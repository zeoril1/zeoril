"""JSON API мини-игры: ролл, реролл, перемешивание, выход."""
from __future__ import annotations

import random
import time

from flask import jsonify, request

from app.site.auth import current_user, get_user_by_id, validate_csrf_json
from app.site.bungie.api import get_user_owned_hashes
from app.site.destiny_game.blueprint import (_broadcast, _lock, bp)
from app.site.destiny_game.lobby import (_end_game, _get_lobby, _leave_lobby,
                                         _lobby_state)
from app.site.destiny_game.roulette import _begin_roll_locked, _pick_challenge


def _error(msg: str, code: int = 400):
    return jsonify({'ok': False, 'error': msg}), code


def _cancel_reroll(lobby_id: str) -> None:
    """Откатывает активный реролл и флаг rolling (вызывается под _lock)."""
    with _lock:
        lobby = _get_lobby(lobby_id)
        if lobby is None:
            return
        lobby.rolling = False
        lobby.reroll_active = None
        _broadcast(lobby, 'reroll', {
            'pending': lobby.reroll_pending,
            'active': None,
        })
        _broadcast(lobby, 'lobby', _lobby_state(lobby))


@bp.route('/destiny/game/api/roll', methods=['POST'])
def api_roll():
    user = current_user()
    if user is None:
        return _error('Не авторизован', 401)
    if not validate_csrf_json():
        return _error('Неверный CSRF-токен', 400)

    payload = request.get_json(silent=True) or {}
    lobby_id = (payload.get('lobby_id') or '').strip()
    uid = str(user['id'])

    with _lock:
        lobby = _get_lobby(lobby_id)
        if lobby is None or lobby.closed:
            return _error('Лобби не найдено или закрыто', 404)
        if uid not in lobby.members:
            return _error('Вы не в этом лобби', 403)
        if lobby.rolling:
            return _error('Рулетка уже крутится, дождитесь результата', 409)
        if lobby.round_done:
            return _error('Круг завершён. Запросите реролл у владельца', 409)
        if not lobby.order or lobby.order[lobby.current_index] != uid:
            return _error('Сейчас не ваш ход', 409)
        lobby.rolling = True
        rolled = set(lobby.rolled.get(uid, ()))

    # В пул игрока попадает только то оружие, которое у него уже есть в
    # Destiny 2 (проверяем инвентарь через Bungie), минус то, что уже
    # выпадало в этом лобби.
    ok, owned = get_user_owned_hashes(user)
    if not ok:
        with _lock:
            lobby = _get_lobby(lobby_id)
            if lobby is not None:
                lobby.rolling = False
        return _error('Не удалось проверить ваш инвентарь Bungie. '
                      'Попробуйте ещё раз.', 500)

    challenge, pool = _pick_challenge(owned=owned, rolled=rolled)
    if challenge is None:
        with _lock:
            lobby = _get_lobby(lobby_id)
            if lobby is not None:
                lobby.rolling = False
        return _error('В вашем арсенале нет оружия из пула рулетки — '
                      'либо всё уже выпадало.', 409)

    with _lock:
        lobby = _get_lobby(lobby_id)
        if lobby is None or lobby.closed:
            return _error('Лобби закрыто', 404)
        if not _begin_roll_locked(lobby, uid, challenge, pool):
            lobby.rolling = False
            return _error('Не удалось собрать колесо рулетки', 500)

    return jsonify({'ok': True})


@bp.route('/destiny/game/api/reroll', methods=['POST'])
def api_reroll():
    """Игрок запрашивает у владельца реролл для себя."""
    user = current_user()
    if user is None:
        return _error('Не авторизован', 401)
    if not validate_csrf_json():
        return _error('Неверный CSRF-токен', 400)

    payload = request.get_json(silent=True) or {}
    lobby_id = (payload.get('lobby_id') or '').strip()
    uid = str(user['id'])

    with _lock:
        lobby = _get_lobby(lobby_id)
        if lobby is None or lobby.closed:
            return _error('Лобби не найдено или закрыто', 404)
        if uid not in lobby.members:
            return _error('Вы не в этом лобби', 403)
        if lobby.rolling:
            return _error('Сейчас крутится рулетка, дождитесь результата', 409)
        if not lobby.round_done:
            return _error('Реролл доступен после завершения круга', 409)
        if lobby.reroll_pending:
            return _error('Уже есть активный запрос на реролл', 409)
        if lobby.reroll_active:
            return _error('Реролл уже выполняется', 409)

        lobby.reroll_pending.append(uid)
        lobby.last_activity = time.time()
        _broadcast(lobby, 'reroll', {
            'pending': lobby.reroll_pending,
            'active': lobby.reroll_active,
        })
        _broadcast(lobby, 'lobby', _lobby_state(lobby))

    return jsonify({'ok': True})


@bp.route('/destiny/game/api/reroll/approve', methods=['POST'])
def api_reroll_approve():
    """Владелец одобряет/отклоняет реролл для конкретного игрока."""
    user = current_user()
    if user is None:
        return _error('Не авторизован', 401)
    if not validate_csrf_json():
        return _error('Неверный CSRF-токен', 400)

    payload = request.get_json(silent=True) or {}
    lobby_id = (payload.get('lobby_id') or '').strip()
    owner_uid = str(user['id'])
    target_uid = str(payload.get('user_id') or '').strip()
    approve = bool(payload.get('approve'))

    with _lock:
        lobby = _get_lobby(lobby_id)
        if lobby is None or lobby.closed:
            return _error('Лобби не найдено или закрыто', 404)
        if lobby.owner_id != owner_uid:
            return _error('Это может делать только создатель лобби', 403)
        if target_uid not in lobby.reroll_pending:
            return _error('Запрос на реролл не найден', 404)
        if lobby.rolling:
            return _error('Рулетка уже крутится', 409)

        if not approve:
            lobby.reroll_pending = [
                u for u in lobby.reroll_pending if u != target_uid]
            _broadcast(lobby, 'reroll', {
                'pending': lobby.reroll_pending,
                'active': lobby.reroll_active,
            })
            _broadcast(lobby, 'lobby', _lobby_state(lobby))
            return jsonify({'ok': True})

        # Одобряем: запускаем точечный реролл для игрока.
        # Очередь ходов и статус круга не меняются — меняется только результат
        # конкретного игрока (см. is_reroll в _finish_roll).
        lobby.reroll_pending = [
            u for u in lobby.reroll_pending if u != target_uid]
        lobby.reroll_active = target_uid
        lobby.rolling = True
        rolled = set(lobby.rolled.get(target_uid, ()))

        _broadcast(lobby, 'reroll', {
            'pending': lobby.reroll_pending,
            'active': lobby.reroll_active,
        })
        _broadcast(lobby, 'lobby', _lobby_state(lobby))

    # Для реролла тоже важен инвентарь конкретного игрока (target_uid),
    # а не владельца, который одобряет реролл.
    try:
        target_id = int(target_uid)
    except (TypeError, ValueError):
        target_id = None
    target_user = get_user_by_id(target_id) if target_id else None
    if target_user is None:
        _cancel_reroll(lobby_id)
        return _error('Игрок не найден', 404)

    ok, owned = get_user_owned_hashes(target_user)
    if not ok:
        _cancel_reroll(lobby_id)
        return _error('Не удалось проверить инвентарь игрока Bungie. '
                      'Попробуйте ещё раз.', 500)

    challenge, pool = _pick_challenge(owned=owned, rolled=rolled)
    if challenge is None:
        _cancel_reroll(lobby_id)
        return _error('У игрока нет оружия из пула рулетки — '
                      'либо всё уже выпадало.', 409)

    with _lock:
        lobby = _get_lobby(lobby_id)
        if lobby is None or lobby.closed:
            return _error('Лобби закрыто', 404)
        if not _begin_roll_locked(lobby, target_uid, challenge, pool,
                                  is_reroll=True):
            lobby.rolling = False
            lobby.reroll_active = None
            _broadcast(lobby, 'reroll', {
                'pending': lobby.reroll_pending,
                'active': None,
            })
            _broadcast(lobby, 'lobby', _lobby_state(lobby))
            return _error('Не удалось собрать колесо рулетки', 500)


    return jsonify({'ok': True})


@bp.route('/destiny/game/api/shuffle', methods=['POST'])
def api_shuffle():
    user = current_user()
    if user is None:
        return _error('Не авторизован', 401)
    if not validate_csrf_json():
        return _error('Неверный CSRF-токен', 400)

    payload = request.get_json(silent=True) or {}
    lobby_id = (payload.get('lobby_id') or '').strip()
    uid = str(user['id'])

    with _lock:
        lobby = _get_lobby(lobby_id)
        if lobby is None or lobby.closed:
            return _error('Лобби не найдено или закрыто', 404)
        if lobby.owner_id != uid:
            return _error('Перемешивать может только создатель лобби', 403)
        if lobby.rolling:
            return _error('Дождитесь окончания текущего броска', 409)

        random.shuffle(lobby.order)
        lobby.current_index = 0
        # Новый круг: сбрасываем результаты рулетки прошлого круга.
        lobby.round_results = []
        lobby.round_done = False
        lobby.reroll_pending = []
        lobby.reroll_active = None
        lobby.last_activity = time.time()
        _broadcast(lobby, 'round', lobby.round_results)
        _broadcast(lobby, 'reroll', {
            'pending': lobby.reroll_pending,
            'active': None,
        })
        _broadcast(lobby, 'turn', {
            'user_id': lobby.order[0] if lobby.order else None})
        _broadcast(lobby, 'lobby', _lobby_state(lobby))

    return jsonify({'ok': True})


@bp.route('/destiny/game/api/leave', methods=['POST'])
def api_leave():
    """Выход из лобби. Владелец завершает игру для всех."""
    user = current_user()
    if user is None:
        return _error('Не авторизован', 401)
    if not validate_csrf_json():
        return _error('Неверный CSRF-токен', 400)

    payload = request.get_json(silent=True) or {}
    lobby_id = (payload.get('lobby_id') or '').strip()
    uid = str(user['id'])

    with _lock:
        lobby = _get_lobby(lobby_id)
        if lobby is None:
            return jsonify({'ok': True})

        if lobby.owner_id == uid and not lobby.closed:
            _end_game(lobby)
            return jsonify({'ok': True, 'ended': True})

        _leave_lobby(lobby, uid)
        _broadcast(lobby, 'reroll', {
            'pending': lobby.reroll_pending,
            'active': lobby.reroll_active,
        })
        _broadcast(lobby, 'lobby', _lobby_state(lobby))
        if lobby.order and lobby.order[lobby.current_index] in lobby.members:
            _broadcast(lobby, 'turn', {
                'user_id': lobby.order[lobby.current_index]})
        else:
            _broadcast(lobby, 'turn', {'user_id': None})

    return jsonify({'ok': True})
