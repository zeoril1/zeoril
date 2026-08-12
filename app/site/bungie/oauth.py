"""Bungie OAuth 2.0: вход, callback и отвязка аккаунта.

Флоу:
  * неавторизованный пользователь — вход по ранее привязанному Bungie-профилю;
  * авторизованный пользователь — привязка Bungie-аккаунта к своему профилю.

Пользователи сайта идентифицируются по Discord ID (users.id), поэтому Bungie
не создаёт новые учётные записи: сначала нужен вход через Discord/логин,
затем привязка Bungie в профиле.
"""
from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import requests
from flask import (flash, make_response, redirect, request,
                   session as flask_session)

from app import config_service, database
from app.site.auth import (create_session, current_user, logger, validate_csrf)
from app.site.bungie.config import (BUNGIE_AUTH_URL, BUNGIE_MEMBERSHIPS_URL,
                                    BUNGIE_TOKEN_URL, _render_error,
                                    _set_auth_cookies, bungie_config)


def _find_user_by_bungie(membership_id) -> dict | None:
    """Ищет пользователя сайта по привязанному Bungie membershipId."""
    with database.db() as conn:
        row = database.execute(
            conn,
            'SELECT * FROM users WHERE bungie_membership_id = %s',
            (int(membership_id),),
        ).fetchone()
        return dict(row) if row else None


def bungie_login():
    """Начинает OAuth-флоу: редирект на Bungie.net с state-параметром."""
    try:
        cfg = bungie_config()
    except RuntimeError as exc:
        logger.warning('Bungie OAuth не настроен: %s', exc)
        return _render_error(
            'Вход через Bungie временно недоступен: приложение Bungie '
            'не настроено. Сообщите администратору.')
    state = secrets.token_hex(16)
    flask_session['_bungie_state'] = state

    # Bungie сам направляет пользователя на Redirect URL, заданный
    # в настройках приложения (передать его в запросе нельзя).
    params = {
        'client_id': cfg['client_id'],
        'response_type': 'code',
        'state': state,
    }
    return redirect(f'{BUNGIE_AUTH_URL}?{urlencode(params)}')


def bungie_callback():
    """Обрабатывает возврат от Bungie.net.

    Если на сайте уже есть авторизованный пользователь — привязывает
    Bungie-аккаунт к нему. Иначе — входит под пользователем, к которому
    привязан Bungie-профиль, либо сообщает, что аккаунт не привязан.
    """
    try:
        return _bungie_callback_inner()
    except Exception as exc:
        # Никогда не отдаём 500 из-за непредвиденной ошибки в OAuth-флоу.
        logger.error('Непредвиденная ошибка в Bungie OAuth callback: %s',
                     exc, exc_info=True)
        return _render_error('Не удалось завершить вход через Bungie. '
                             'Попробуйте ещё раз или сообщите администратору.')


def _bungie_callback_inner():
    """Внутренняя реализация callback (без общего перехвата исключений)."""
    error = request.args.get('error')
    if error:
        return _render_error('Вход через Bungie отменён или не удался')

    code = request.args.get('code')
    state = request.args.get('state')
    if not code or not state:
        return _render_error('Неверный ответ от Bungie.net (нет code/state)')
    if state != flask_session.get('_bungie_state'):
        return _render_error('Неверный параметр state — повторите вход')
    flask_session.pop('_bungie_state', None)

    try:
        cfg = bungie_config()
    except RuntimeError as exc:
        logger.warning('Bungie OAuth не настроен: %s', exc)
        return _render_error(
            'Вход через Bungie временно недоступен: приложение Bungie '
            'не настроено. Сообщите администратору.')


    # Обмен кода авторизации на токен. Приложение Bungie настроено как
    # Confidential — client_secret обязателен и всегда передаётся.
    token_data: dict[str, str] = {
        'client_id': cfg['client_id'],
        'client_secret': cfg['client_secret'],
        'grant_type': 'authorization_code',
        'code': code,
    }
    try:
        token_resp = requests.post(
            BUNGIE_TOKEN_URL,
            data=token_data,
            headers={'Content-Type': 'application/x-www-form-urlencoded'},
            timeout=10,
        )
        token_resp.raise_for_status()
        token_json = token_resp.json()
    except requests.RequestException as exc:
        logger.warning('Ошибка обмена кода Bungie OAuth: %s', exc)
        return _render_error('Не удалось получить токен от Bungie.net')


    access_token = token_json.get('access_token')
    if not access_token:
        return _render_error('Bungie.net не вернул access_token')
    refresh_token = token_json.get('refresh_token') or ''
    # Bungie отдаёт expires_in в секундах с момента выдачи — храним
    # абсолютную дату истечения (ISO), чтобы не зависеть от времени выдачи.
    try:
        expires_in = int(token_json.get('expires_in') or 0)
    except (TypeError, ValueError):
        expires_in = 0
    if expires_in > 0:
        token_expires = (datetime.now(timezone.utc)
                         + timedelta(seconds=expires_in)).isoformat()
    else:
        token_expires = ''


    # Данные аккаунта: все привязанные профили Destiny 2 и Bungie.net.
    try:
        me_resp = requests.get(
            BUNGIE_MEMBERSHIPS_URL,
            headers={
                'Authorization': f'Bearer {access_token}',
                'X-API-Key': cfg['api_key'],
            },
            timeout=10,
        )
        me_resp.raise_for_status()
        payload = me_resp.json().get('Response') or {}
    except requests.RequestException as exc:
        logger.warning('Ошибка запроса данных пользователя Bungie: %s', exc)
        return _render_error('Не удалось получить данные профиля Bungie')

    destiny = payload.get('destinyMemberships') or []
    net_user = payload.get('bungieNetUser') or {}

    # Предпочитаем Steam (membershipType=3), иначе берём первый профиль.
    primary = next((m for m in destiny if m.get('membershipType') == 3), None)
    if primary is None and destiny:
        primary = destiny[0]

    if primary is None:
        return _render_error('Bungie.net не вернул данные профиля Destiny 2')

    membership_id = str(primary.get('membershipId') or '').strip()
    membership_type = int(primary.get('membershipType') or 0)
    display_name = (primary.get('displayName')
                    or net_user.get('uniqueName')
                    or 'Bungie-пользователь')

    if not membership_id:
        return _render_error('Bungie.net не вернул membershipId')

    user = current_user()
    if user is not None:
        # Авторизованный пользователь привязывает Bungie-аккаунт к себе.
        existing = _find_user_by_bungie(membership_id)
        if existing is not None and existing['id'] != user['id']:
            flash('Этот Bungie-аккаунт уже привязан к другому '
                  'пользователю клана. Сначала отвяжите его там.')
            return redirect('/')


        with database.db() as conn:
            database.execute(
                conn,
                """UPDATE users
                   SET bungie_membership_id = %s,
                       bungie_membership_type = %s,
                       bungie_name = %s,
                       bungie_access_token = %s,
                       bungie_refresh_token = %s,
                       bungie_token_expires = %s
                   WHERE id = %s""",
                (int(membership_id), membership_type, display_name,
                 access_token, refresh_token, token_expires, user['id']),

            )
        flash(f'Bungie-аккаунт {display_name} успешно привязан.')


        return redirect('/')

    # Вход по ранее привязанному Bungie-аккаунту.
    linked = _find_user_by_bungie(membership_id)
    if linked is None:
        return _render_error(
            'Этот Bungie-аккаунт не привязан к участникам клана HG. '
            'Сначала войдите через Discord или логин и привяжите '
            'Bungie в своём профиле.')

    # Обновляем сохранённые токены при каждом входе.
    with database.db() as conn:
        database.execute(
            conn,
            """UPDATE users
               SET bungie_access_token = %s,
                   bungie_refresh_token = %s,
                   bungie_token_expires = %s
               WHERE id = %s""",
            (access_token, refresh_token, token_expires, linked['id']),
        )

    token = create_session(linked['id'])
    resp = make_response(redirect('/'))
    _set_auth_cookies(resp, token, linked['id'])
    return resp


def bungie_unlink():
    """Отвязывает Bungie-аккаунт от текущего пользователя."""
    user = current_user()
    if user is None:
        return redirect('/')
    validate_csrf()
    with database.db() as conn:

        database.execute(
            conn,
            """UPDATE users
               SET bungie_membership_id = NULL,
                   bungie_membership_type = NULL,
                   bungie_name = NULL,
                   bungie_access_token = NULL,
                   bungie_refresh_token = NULL,
                   bungie_token_expires = NULL
               WHERE id = %s""",
            (user['id'],),
        )

    flash('Bungie-аккаунт отвязан.')

    return redirect('/')
