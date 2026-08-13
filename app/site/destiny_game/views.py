"""Страницы мини-игры: главная, лобби, просмотр игры, SSE-поток."""
from __future__ import annotations

import json
import queue

from flask import (Response, jsonify, redirect, render_template, request,
                   url_for)

from app import database
from app.site.auth import current_user, validate_csrf
from app.site.bungie.config import bungie_linked
from app.site.destiny_game.blueprint import (_broadcast, _lock, bp, logger)
from app.site.destiny_game.lobby import (_active_lobbies, _cleanup_lobbies,
                                         _create_lobby, _get_lobby,
                                         _join_lobby, _lobby_state)


BUNGIE_REQUIRED_MSG = ('Для игры в рулетку нужен привязанный '
                       'Bungie-аккаунт — без него нельзя проверить, какое '
                       'оружие из пула уже есть у игрока.')


def _render_index(user: dict, message: str | None = None,
                  bungie_link_required: bool = False):
    """Главная страница мини-игры (сессии + прошлые игры + сообщение)."""
    past_games = []
    try:
        past_games = database.get_destiny_games(limit=20)
    except Exception as exc:
        logger.exception('Не удалось загрузить прошлые игры: %s', exc)
    with _lock:
        _cleanup_lobbies()
        active_sessions = _active_lobbies()
    return render_template(
        'destiny_game.html', user=user, message=message,
        bungie_link_required=bungie_link_required,
        past_games=past_games, active_sessions=active_sessions)


@bp.route('/destiny/game', methods=['GET', 'POST'])
def game_index():
    user = current_user()
    if user is None:
        return redirect('/')
    if request.method == 'POST':
        validate_csrf()
        # Для игры обязателен привязанный Bungie-аккаунт.
        if not bungie_linked(user):
            return _render_index(
                user, BUNGIE_REQUIRED_MSG, bungie_link_required=True)
        name = (request.form.get('name') or '').strip()
        if not name:
            name = f"Лобби {user.get('name_discord') or user['id']}"
        name = name[:80]
        with _lock:
            _cleanup_lobbies()
            lobby = _create_lobby(user, name)
        return redirect(url_for('destiny_game.lobby_page', lobby_id=lobby.id))

    return _render_index(user)


@bp.route('/destiny/game/<lobby_id>')
def lobby_page(lobby_id: str):
    user = current_user()
    if user is None:
        return redirect('/')
    # Вход в лобби (в т.ч. по ссылке-приглашению) — только с привязанным
    # Bungie-аккаунтом.
    if not bungie_linked(user):
        return _render_index(
            user, BUNGIE_REQUIRED_MSG, bungie_link_required=True)
    with _lock:
        _cleanup_lobbies()
        lobby = _get_lobby(lobby_id)
    if lobby is None:
        return _render_index(
            user, 'Лобби не найдено или истекло. Создайте новое.')
    with _lock:
        _join_lobby(lobby, user)
        _broadcast(lobby, 'lobby', _lobby_state(lobby))
        state = _lobby_state(lobby)
    invite_url = url_for('destiny_game.lobby_page', lobby_id=lobby.id,
                         _external=True)
    return render_template('destiny_game_lobby.html', user=user,
                           lobby=state, invite_url=invite_url)


@bp.route('/destiny/game/<int:game_id>/view')
def game_view(game_id: int):
    """Страница просмотра завершённой игры (сохранённые итоги)."""
    user = current_user()
    if user is None:
        return redirect('/')
    try:
        game = database.get_destiny_game(game_id)
    except Exception as exc:
        logger.exception('Не удалось загрузить игру %s: %s', game_id, exc)
        game = None
    if game is None:
        return render_template('destiny_game.html', user=user,
                               message='Игра не найдена', past_games=[],
                               active_sessions=[])
    return render_template('destiny_game_view.html', user=user, game=game)


@bp.route('/destiny/game/<lobby_id>/state')
def game_state(lobby_id: str):
    """AJAX: текущее состояние лобби (для периодической синхронизации)."""
    user = current_user()
    if user is None:
        return jsonify({'ok': False, 'error': 'Не авторизован'}), 401
    if not bungie_linked(user):
        return jsonify({'ok': False,
                        'error': 'Нужен привязанный Bungie-аккаунт'}), 403
    with _lock:
        lobby = _get_lobby(lobby_id)
        if lobby is None:
            return jsonify({'ok': False, 'error': 'Лобби не найдено'}), 404
        _join_lobby(lobby, user)
        return jsonify({'ok': True, 'lobby': _lobby_state(lobby)})


@bp.route('/destiny/game/<lobby_id>/stream')
def game_stream(lobby_id: str):
    """SSE-поток событий лобби."""
    user = current_user()
    if user is None:
        return jsonify({'ok': False, 'error': 'Не авторизован'}), 401
    if not bungie_linked(user):
        return jsonify({'ok': False,
                        'error': 'Нужен привязанный Bungie-аккаунт'}), 403

    with _lock:
        lobby = _get_lobby(lobby_id)
        if lobby is None:
            return jsonify({'ok': False, 'error': 'Лобби не найдено'}), 404
        _join_lobby(lobby, user)
        q: queue.Queue = queue.Queue(maxsize=200)
        lobby.subscribers.append(q)

    def generate():
        try:
            while True:
                if lobby.closed:
                    break
                try:
                    event, data = q.get(timeout=15)
                    payload = (
                        f'event: {event}\n'
                        f'data: {json.dumps(data, ensure_ascii=False)}\n\n')
                    yield payload
                    if event == 'game_end':
                        break
                except queue.Empty:
                    yield ': keep-alive\n\n'
        except GeneratorExit:
            pass
        finally:
            with _lock:
                if q in lobby.subscribers:
                    lobby.subscribers.remove(q)

    resp = Response(generate(), mimetype='text/event-stream')
    resp.headers['Cache-Control'] = 'no-cache'
    resp.headers['X-Accel-Buffering'] = 'no'
    return resp
