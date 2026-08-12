"""Главная страница: вход, профиль, регистрация."""
from __future__ import annotations

import logging
import time

from flask import make_response, redirect, render_template, request
from werkzeug.security import generate_password_hash

from app import database
from app.site.auth import (_client_ip, _rate_key, clear_failures,
                           create_session, current_user, get_user_by_id,
                           get_user_by_login, rate_limit_wait,
                           register_failure, user_rights, validate_csrf,
                           verify_password)
from app.site.music import save_music
from app.site.views.blueprint import bp
from app.site.views.helpers import _set_auth_cookies, render_guest, render_profile

logger = logging.getLogger('BotSite')


# --------------------------------------------------------------------------- #
# Главная: вход и профиль
# --------------------------------------------------------------------------- #

@bp.route('/', methods=['GET', 'POST'])
def index():
    user = current_user()
    if user is None:
        return handle_guest()
    return handle_authed(user)


def handle_guest():
    if request.method == 'POST':
        validate_csrf()
        login = (request.form.get('Login') or '').strip()
        password = request.form.get('password') or ''
        if not login or not password:
            return render_guest('Введите логин и пароль')
        key = _rate_key('login', login)
        wait = rate_limit_wait(key)
        if wait:
            logger.warning('Лимит попыток входа от %s: блокировка %s сек',
                           _client_ip(), wait)
            return render_guest(
                f'Слишком много попыток входа. Попробуйте через {wait} сек.')
        user = get_user_by_login(login)
        if user is None or not verify_password(password, user.get('password')):
            register_failure(key)
            time.sleep(0.5)
            return render_guest('ID или пароль не верен')
        clear_failures(key)
        # Миграция старого MD5-пароля на PBKDF2 (werkzeug-хеши не трогаем).
        if not user['password'].startswith(('pbkdf2:', 'scrypt:', 'argon2:')):
            with database.db() as conn:
                database.execute(
                    conn,
                    'UPDATE users SET password = %s WHERE id = %s',
                    (generate_password_hash(password), user['id']),
                )
        token = create_session(user['id'])
        resp = make_response(redirect('/'))
        _set_auth_cookies(resp, token, user['id'])
        return resp

    return render_guest()


def handle_authed(user):
    uid = user['id']
    rights = user_rights(uid)
    is_music = 'Admin' in rights or 'Music' in rights or 'Music_ALL' in rights
    can_download = 'Admin' in rights or 'Music_down' in rights

    if request.method == 'POST':
        validate_csrf()
        action = request.form.get('action')
        if action == 'save_song':
            if not is_music:
                return redirect('/', code=403)
            new_music = (request.form.get('new_music') or '').strip()
            if new_music:
                with database.db() as conn:
                    database.execute(
                        conn, 'UPDATE users SET song = %s WHERE id = %s',
                        (new_music, uid))
            return redirect('/')
        if not can_download:
            return redirect('/', code=403)
        ok, msg = save_music(request.files.get('music_down'))
        return render_profile(user, rights, message=msg, show_select=True)

    show_select = 'Select' in request.args
    if show_select and not is_music:
        return redirect('/', code=403)
    return render_profile(user, rights, show_select=show_select)


# --------------------------------------------------------------------------- #
# Регистрация
# --------------------------------------------------------------------------- #

@bp.route('/register', methods=['POST'])
def register():
    validate_csrf()
    uid = (request.form.get('ID') or '').strip()
    login = (request.form.get('Login') or '').strip()
    password = request.form.get('password') or ''
    if not uid.isdigit() or not login or not password:
        return render_template('register.html', message='Заполните все поля корректно')
    key = _rate_key('register', uid)
    wait = rate_limit_wait(key)
    if wait:
        logger.warning('Лимит попыток регистрации от %s: блокировка %s сек',
                       _client_ip(), wait)
        return render_template(
            'register.html',
            message=f'Слишком много попыток. Попробуйте через {wait} сек.')
    user = get_user_by_id(uid)
    if user is None:
        register_failure(key)
        message = 'Зарегистрироваться могут только участники клана HG'
        return render_template('register.html', message=message)
    if user.get('password'):
        register_failure(key)
        message = 'Пользователь найден, используйте пароль для входа'
        return render_template('register.html', message=message)
    with database.db() as conn:
        database.execute(
            conn,
            'UPDATE users SET password = %s, login = %s WHERE id = %s',
            (generate_password_hash(password), login, uid),
        )
    clear_failures(key)
    return render_template('register.html', message='Регистрация прошла успешно')
