"""Аутентификация: сессии, пароли, права, rate limiting, CSRF."""
from __future__ import annotations

import hashlib
import logging
import secrets
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone

import flask
from flask import request, session as flask_session
from werkzeug.security import check_password_hash, generate_password_hash

from app import config_service, database

logger = logging.getLogger('BotSite')

SESSION_TTL = timedelta(days=7)
_WERKZEUG_HASH_PREFIXES = ('pbkdf2:', 'scrypt:', 'argon2:')


def _cookie_secure() -> bool:
    """Нужен ли атрибут Secure на cookie (Auth, Id, сессия Flask).

    COOKIE_SECURE задаёт его явно; иначе — по схеме запроса (request.is_secure).
    """
    value = (config_service.get('COOKIE_SECURE') or '').strip().lower()
    if value in ('1', 'true', 'yes', 'on'):
        return True
    if value in ('0', 'false', 'no', 'off'):
        return False
    return bool(request.is_secure)


# --------------------------------------------------------------------------- #
# Пользователи и сессии
# --------------------------------------------------------------------------- #

def get_user_by_login(login: str) -> dict | None:
    with database.db() as conn:
        row = database.execute(
            conn, 'SELECT * FROM users WHERE login = %s', (login,)
        ).fetchone()
        return dict(row) if row else None


def get_user_by_id(user_id) -> dict | None:
    with database.db() as conn:
        row = database.execute(
            conn, 'SELECT * FROM users WHERE id = %s', (user_id,)
        ).fetchone()
        return dict(row) if row else None


def _hash_session_token(token: str) -> str:
    """SHA-256 хеш токена сессии."""
    return hashlib.sha256(token.encode('utf-8')).hexdigest()


def get_session_user(token: str | None) -> dict | None:
    """Возвращает пользователя по токену сессии, если сессия валидна."""
    if not token:
        return None
    now = datetime.now(timezone.utc).isoformat()
    token_hash = _hash_session_token(token)
    with database.db() as conn:
        row = database.execute(
            conn,
            """SELECT u.*, s.id AS session_user_id
               FROM users u
               JOIN session s ON u.id = s.id
               WHERE s.hash = %s AND (s.expires IS NULL OR s.expires > %s)""",
            (token_hash, now),
        ).fetchone()
        if row is None:
            # Миграция старых сессий, где токен хранился открытым текстом.
            row = database.execute(
                conn,
                """SELECT u.*, s.id AS session_user_id
                   FROM users u
                   JOIN session s ON u.id = s.id
                   WHERE s.hash = %s AND (s.expires IS NULL OR s.expires > %s)""",
                (token, now),
            ).fetchone()
            if row is not None:
                database.execute(
                    conn,
                    'UPDATE session SET hash = %s WHERE id = %s AND hash = %s',
                    (token_hash, row['id'], token),
                )
        return dict(row) if row else None


def create_session(user_id) -> str:
    """Создаёт сессию и возвращает случайный токен."""
    token = secrets.token_hex(32)
    now = datetime.now(timezone.utc)
    expires = (now + SESSION_TTL).isoformat()
    with database.db() as conn:
        database.execute(
            conn,
            'DELETE FROM session WHERE expires IS NOT NULL AND expires < %s',
            (now.isoformat(),),
        )
        database.execute(
            conn,
            'INSERT INTO session (id, hash, expires) VALUES (%s, %s, %s)',
            (user_id, _hash_session_token(token), expires),
        )
    return token


def delete_session(token: str | None) -> None:
    if token:
        token_hash = _hash_session_token(token)
        with database.db() as conn:
            # Удаляем и по хешу, и по открытому токену (старые сессии).
            database.execute(
                conn, 'DELETE FROM session WHERE hash IN (%s, %s)',
                (token_hash, token))


def user_rights(user_id) -> list[str]:
    with database.db() as conn:
        rows = database.execute(
            conn,
            """SELECT r.name
               FROM rights r
               JOIN users_rights ur ON r.id = ur.id_right
               WHERE ur.id_user = %s""",
            (str(user_id),),
        ).fetchall()
        return [r['name'] for r in rows]


def verify_password(plain: str, hashed: str | None) -> bool:
    if not hashed:
        return False
    if hashed.startswith(_WERKZEUG_HASH_PREFIXES):
        return check_password_hash(hashed, plain)
    # Миграция со старых MD5-хешей.
    return hashlib.md5(plain.encode('utf-8')).hexdigest() == hashed


def current_user() -> dict | None:
    return get_session_user(request.cookies.get('Auth'))


def request_user_is_admin() -> bool:
    user = current_user()
    if user is None:
        return False
    return 'Admin' in user_rights(user['id'])


# --------------------------------------------------------------------------- #
# Rate limiting
# --------------------------------------------------------------------------- #
_RATE_LIMIT_MAX_FAILURES = 5
_RATE_LIMIT_WINDOW = 300
_RATE_LIMIT_LOCKOUT = 900

_login_failures: dict[str, list[float]] = defaultdict(list)
_lockouts: dict[str, float] = {}


def _client_ip() -> str:
    """IP клиента с учётом X-Forwarded-For (за прокси)."""
    forwarded = request.headers.get('X-Forwarded-For')
    if forwarded:
        return forwarded.split(',')[0].strip()
    return request.remote_addr or 'unknown'


def _rate_key(scope: str, ident: str) -> str:
    return f'{scope}:{_client_ip()}:{ident.lower()}'


def rate_limit_wait(key: str) -> int:
    """Секунды ожидания, если попытки исчерпаны; иначе 0."""
    now = time.time()
    until = _lockouts.get(key)
    if until is not None and until > now:
        return int(until - now) + 1
    attempts = [t for t in _login_failures.get(key, [])
                if now - t < _RATE_LIMIT_WINDOW]
    if len(attempts) >= _RATE_LIMIT_MAX_FAILURES:
        _lockouts[key] = now + _RATE_LIMIT_LOCKOUT
        _login_failures.pop(key, None)
        return _RATE_LIMIT_LOCKOUT
    _login_failures[key] = attempts
    return 0


def register_failure(key: str) -> None:
    _login_failures[key].append(time.time())


def clear_failures(key: str) -> None:
    _login_failures.pop(key, None)
    _lockouts.pop(key, None)


# --------------------------------------------------------------------------- #
# CSRF
# --------------------------------------------------------------------------- #

def csrf_token() -> str:
    token = flask_session.get('_csrf_token')
    if not token:
        token = secrets.token_hex(16)
        flask_session['_csrf_token'] = token
    return token


def validate_csrf() -> None:
    sent = request.form.get('_csrf_token')
    if not sent or sent != flask_session.get('_csrf_token'):
        flask.abort(400, description='Неверный CSRF-токен')


def _read_csrf_from_request() -> str | None:
    """Достаёт CSRF-токен из form-data или JSON-тела запроса."""
    token = request.form.get('_csrf_token')
    if token:
        return token
    payload = request.get_json(silent=True)
    if isinstance(payload, dict):
        return payload.get('_csrf_token')
    return None


def validate_csrf_json() -> bool:
    """CSRF-проверка для JSON-эндпоинтов."""
    sent = _read_csrf_from_request()
    return bool(sent and sent == flask_session.get('_csrf_token'))
