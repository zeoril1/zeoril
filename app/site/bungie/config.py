"""Bungie OAuth: настройки, общие константы и хелперы страниц."""
from __future__ import annotations

from flask import flash, redirect, render_template

from app import config_service
from app.site.auth import SESSION_TTL, _cookie_secure, current_user, logger


BUNGIE_AUTH_URL = 'https://www.bungie.net/en/OAuth/Authorize'
BUNGIE_TOKEN_URL = 'https://www.bungie.net/platform/app/oauth/token/'
BUNGIE_MEMBERSHIPS_URL = ('https://www.bungie.net/Platform/User/'
                          'GetMembershipsForCurrentUser/')

# Типы аккаунтов Destiny 2 (membershipType): 3 = Steam.
DESTINY_MEMBERSHIP_TYPES = {
    1: 'Xbox',
    2: 'PlayStation',
    3: 'Steam',
    4: 'Blizzard',
    5: 'Stadia',
    6: 'Epic Games',
    10: 'EGS',
    254: 'Bungie Next',
}


def bungie_config() -> dict[str, str]:
    """Возвращает настройки Bungie OAuth из конфиг-сервиса.

    Приложение Bungie настроено как Confidential, поэтому ``client_secret``
    обязателен и всегда передаётся в OAuth-запросах.
    """
    cfg = {
        'client_id': (config_service.get('BUNGIE_CLIENT_ID') or '').strip(),
        'client_secret': (config_service.get('BUNGIE_CLIENT_SECRET') or '').strip(),
        'api_key': (config_service.get('BUNGIE_API_KEY') or '').strip(),
        'redirect_uri': (config_service.get('BUNGIE_REDIRECT_URI') or '').strip(),
    }
    required = ('client_id', 'client_secret', 'api_key', 'redirect_uri')
    missing = [key for key in required if not cfg[key]]
    if missing:
        human = {
            'client_id': 'BUNGIE_CLIENT_ID',
            'client_secret': 'BUNGIE_CLIENT_SECRET',
            'api_key': 'BUNGIE_API_KEY',
            'redirect_uri': 'BUNGIE_REDIRECT_URI',
        }
        names = ', '.join(human[m] for m in missing)
        raise RuntimeError(
            f'Для Bungie OAuth (Confidential) не хватает ключей в '
            f'конфиг-сервисе (проект "discord"): {names}. Redirect URI '
            f'должен совпадать с указанным в настройках приложения Bungie '
            f'и оканчиваться на /bungie/callback.'
        )
    return cfg


def _render_error(message: str):
    """Возвращает страницу с ошибкой.

    Для авторизованного пользователя — редирект на главную с flash-сообщением,
    иначе — гостевая страница с сообщением об ошибке. Любые проблемы с БД при
    определении пользователя не должны превращать страницу ошибки в 500.
    """
    try:
        user = current_user()
    except Exception:
        user = None
    if user is not None:
        flash(message)
        return redirect('/')
    return render_template('index.html', logged=False, message=message)


def _set_auth_cookies(resp, token: str, user_id) -> None:
    """Устанавливает cookie Auth и Id с общими параметрами."""
    max_age = int(SESSION_TTL.total_seconds())
    resp.set_cookie('Auth', token, httponly=True, samesite='Lax',
                    secure=_cookie_secure(), max_age=max_age)
    resp.set_cookie('Id', str(user_id), httponly=True, samesite='Lax',
                    secure=_cookie_secure(), max_age=max_age)
