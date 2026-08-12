"""Discord OAuth 2.0: вход через Discord."""
from __future__ import annotations

import secrets

import requests
from flask import (make_response, redirect, render_template, request,
                   session as flask_session)
from urllib.parse import urlencode

from app import config_service, database
from app.site.auth import (SESSION_TTL, _cookie_secure, create_session,
                           get_user_by_id, logger)


DISCORD_AUTH_URL = 'https://discord.com/oauth2/authorize'
DISCORD_TOKEN_URL = 'https://discord.com/api/oauth2/token'
DISCORD_API_URL = 'https://discord.com/api/v10/users/@me'


def oauth_config() -> dict[str, str]:
    """Возвращает настройки Discord OAuth из конфиг-сервиса."""
    cfg = {
        'client_id': (config_service.get('DISCORD_CLIENT_ID') or '').strip(),
        'client_secret': (config_service.get('DISCORD_CLIENT_SECRET') or '').strip(),
        'redirect_uri': (config_service.get('DISCORD_REDIRECT_URI') or '').strip(),
    }
    if not all(cfg.values()):
        raise RuntimeError(
            'Для Discord OAuth задайте DISCORD_CLIENT_ID, '
            'DISCORD_CLIENT_SECRET и DISCORD_REDIRECT_URI в конфиг-сервисе '
            '(проект "discord"). Redirect URI должен оканчиваться на '
            '/discord/callback.'
        )
    return cfg


def discord_login():
    """Начинает OAuth-флоу: редирект на Discord с state-параметром."""
    cfg = oauth_config()
    state = secrets.token_hex(16)
    flask_session['_oauth_state'] = state

    params = {
        'client_id': cfg['client_id'],
        'redirect_uri': cfg['redirect_uri'],
        'response_type': 'code',
        'scope': 'identify',
        'state': state,
    }
    return redirect(f'{DISCORD_AUTH_URL}?{urlencode(params)}')


def discord_callback():
    """Обрабатывает возврат от Discord: обмен code на токен, вход в аккаунт."""
    error = request.args.get('error')
    if error:
        return render_template('index.html', logged=False,
                               message='Вход через Discord отменён или не удался')
    code = request.args.get('code')
    state = request.args.get('state')
    if not code or not state:
        return render_template('index.html', logged=False,
                               message='Неверный ответ от Discord (нет code/state)')
    if state != flask_session.get('_oauth_state'):
        return render_template('index.html', logged=False,
                               message='Неверный параметр state — повторите вход')
    flask_session.pop('_oauth_state', None)

    cfg = oauth_config()

    try:
        token_resp = requests.post(
            DISCORD_TOKEN_URL,
            data={
                'client_id': cfg['client_id'],
                'client_secret': cfg['client_secret'],
                'grant_type': 'authorization_code',
                'code': code,
                'redirect_uri': cfg['redirect_uri'],
                'scope': 'identify',
            },
            headers={'Content-Type': 'application/x-www-form-urlencoded'},
            timeout=10,
        )
        token_resp.raise_for_status()
        token_json = token_resp.json()
    except requests.RequestException as exc:
        logger.warning('Ошибка обмена кода Discord OAuth: %s', exc)
        return render_template('index.html', logged=False,
                               message='Не удалось получить токен от Discord')

    access_token = token_json.get('access_token')
    if not access_token:
        return render_template('index.html', logged=False,
                               message='Discord не вернул access_token')

    try:
        me_resp = requests.get(
            DISCORD_API_URL,
            headers={'Authorization': f'Bearer {access_token}'},
            timeout=10,
        )
        me_resp.raise_for_status()
        me = me_resp.json()
    except requests.RequestException as exc:
        logger.warning('Ошибка запроса данных пользователя Discord: %s', exc)
        return render_template('index.html', logged=False,
                               message='Не удалось получить данные профиля Discord')

    uid = me.get('id')
    username = me.get('username') or 'Discord-пользователь'
    if not uid:
        return render_template('index.html', logged=False,
                               message='Discord не вернул ID пользователя')

    user = get_user_by_id(uid)
    if user is None:
        logger.info('OAuth: новый пользователь %s (%s)', uid, username)
        with database.db() as conn:
            database.execute(
                conn,
                'INSERT INTO users (id, name_discord) VALUES (%s, %s) '
                'ON CONFLICT (id) DO NOTHING',
                (uid, username),
            )
        user = get_user_by_id(uid)
        if user is None:
            return render_template('index.html', logged=False,
                                   message='Не удалось создать профиль — обратитесь к администратору')

    if user.get('name_discord') != username:
        with database.db() as conn:
            database.execute(
                conn, 'UPDATE users SET name_discord = %s WHERE id = %s',
                (username, uid),
            )

    token = create_session(uid)
    resp = make_response(redirect('/'))
    resp.set_cookie('Auth', token, httponly=True, samesite='Lax',
                    secure=_cookie_secure(),
                    max_age=int(SESSION_TTL.total_seconds()))
    resp.set_cookie('Id', str(uid), httponly=True, samesite='Lax',
                    secure=_cookie_secure(),
                    max_age=int(SESSION_TTL.total_seconds()))

    return resp

