"""Администрирование пользователей и выдача прав."""
from __future__ import annotations

import flask
from flask import redirect, render_template, request
from werkzeug.security import generate_password_hash

from app import database
from app.site.auth import (current_user, get_user_by_id, user_rights,
                           validate_csrf_json)
from app.site.views.blueprint import bp


def get_all_users() -> list[dict]:
    with database.db() as conn:
        rows = database.execute(
            conn,
            'SELECT id, name_discord, login FROM users ORDER BY id'
        ).fetchall()
        return [dict(r) for r in rows]


def get_all_rights() -> list[dict]:
    with database.db() as conn:
        rows = database.execute(
            conn, 'SELECT * FROM rights ORDER BY name'
        ).fetchall()
        return [dict(r) for r in rows]


def get_granted_right_ids(user_id) -> set[str]:
    with database.db() as conn:
        rows = database.execute(
            conn,
            'SELECT id_right FROM users_rights WHERE id_user = %s',
            (str(user_id),),
        ).fetchall()
        return {r[0] for r in rows}


@bp.route('/users', methods=['GET'])
def users():
    user = current_user()
    if user is None:
        return redirect('/')
    rights = user_rights(user['id'])
    if 'Admin' not in rights:
        return render_template('users.html', admin=False)

    all_users = get_all_users()
    return render_template('users.html', admin=True, all_users=all_users)


@bp.route('/users/api/user_rights')
def users_api_user_rights():
    """AJAX: список всех прав и выданные права выбранного пользователя."""
    user = current_user()
    if user is None:
        return flask.jsonify({'ok': False, 'error': 'Не авторизован'}), 401
    if 'Admin' not in user_rights(user['id']):
        return flask.jsonify({'ok': False, 'error': 'Недостаточно прав'}), 403
    uid = (request.args.get('user_id') or '').strip()
    if not uid.isdigit():
        return flask.jsonify({'ok': False, 'error': 'Некорректный ID пользователя'}), 400
    target = get_user_by_id(uid)
    if target is None:
        return flask.jsonify({'ok': False, 'error': 'Пользователь не найден'}), 404
    granted = get_granted_right_ids(uid)
    return flask.jsonify({
        'ok': True,
        'user': {'id': target['id'], 'name': target['name_discord']},
        'rights': [
            {
                'id': r['id'],
                'name': r['name'],
                'desc': r.get('desc') or '',
                'granted': str(r['id']) in granted,
            }
            for r in get_all_rights()
        ],
    })


@bp.route('/users/api/save_rights', methods=['POST'])
def users_api_save_rights():
    """AJAX: сохранить выданные права пользователя."""
    user = current_user()
    if user is None:
        return flask.jsonify({'ok': False, 'error': 'Не авторизован'}), 401
    if 'Admin' not in user_rights(user['id']):
        return flask.jsonify({'ok': False, 'error': 'Недостаточно прав'}), 403
    if not validate_csrf_json():
        return flask.jsonify({'ok': False, 'error': 'Неверный CSRF-токен'}), 400
    payload = request.get_json(silent=True) or {}
    uid = (payload.get('user_id') or '').strip()
    if not uid.isdigit():
        return flask.jsonify({'ok': False, 'error': 'Некорректный ID пользователя'}), 400
    if get_user_by_id(uid) is None:
        return flask.jsonify({'ok': False, 'error': 'Пользователь не найден'}), 404
    selected = [str(r) for r in (payload.get('rights') or []) if str(r).isdigit()]
    with database.db() as conn:
        database.execute(
            conn, 'DELETE FROM users_rights WHERE id_user = %s', (uid,))
        for rid in selected:
            database.execute(
                conn,
                'INSERT INTO users_rights (id_right, id_user) '
                'VALUES (%s, %s)',
                (rid, uid),
            )
    return flask.jsonify({'ok': True})


@bp.route('/users/api/profile')
def users_api_profile():
    """AJAX: данные выбранного пользователя."""
    user = current_user()
    if user is None:
        return flask.jsonify({'ok': False, 'error': 'Не авторизован'}), 401
    if 'Admin' not in user_rights(user['id']):
        return flask.jsonify({'ok': False, 'error': 'Недостаточно прав'}), 403
    uid = (request.args.get('user_id') or '').strip()
    if not uid.isdigit():
        return flask.jsonify({'ok': False, 'error': 'Некорректный ID пользователя'}), 400
    target = get_user_by_id(uid)
    if target is None:
        return flask.jsonify({'ok': False, 'error': 'Пользователь не найден'}), 404
    return flask.jsonify({
        'ok': True,
        'user': {
            'id': target['id'],
            'name': target['name_discord'],
            'login': target.get('login') or '',
        },
    })


@bp.route('/users/api/set_password', methods=['POST'])
def users_api_set_password():
    """AJAX: установить или очистить пароль пользователя."""
    user = current_user()
    if user is None:
        return flask.jsonify({'ok': False, 'error': 'Не авторизован'}), 401
    if 'Admin' not in user_rights(user['id']):
        return flask.jsonify({'ok': False, 'error': 'Недостаточно прав'}), 403
    if not validate_csrf_json():
        return flask.jsonify({'ok': False, 'error': 'Неверный CSRF-токен'}), 400
    payload = request.get_json(silent=True) or {}
    uid = (payload.get('user_id') or '').strip()
    if not uid.isdigit():
        return flask.jsonify({'ok': False, 'error': 'Некорректный ID пользователя'}), 400
    target = get_user_by_id(uid)
    if target is None:
        return flask.jsonify({'ok': False, 'error': 'Пользователь не найден'}), 404
    if payload.get('clear_password'):
        with database.db() as conn:
            database.execute(
                conn, 'UPDATE users SET password = NULL WHERE id = %s', (uid,))
            database.execute(
                conn, 'DELETE FROM session WHERE id = %s', (uid,))
        return flask.jsonify({
            'ok': True,
            'message': 'Пароль очищен. Пользователь может зарегистрироваться заново.',
        })
    new_password = (payload.get('new_password') or '').strip()
    if not new_password:
        return flask.jsonify({
            'ok': False,
            'error': 'Введите новый пароль или нажмите «Очистить пароль».',
        }), 400
    with database.db() as conn:
        database.execute(
            conn, 'UPDATE users SET password = %s WHERE id = %s',
            (generate_password_hash(new_password), uid),
        )
        database.execute(
            conn, 'DELETE FROM session WHERE id = %s', (uid,))
    return flask.jsonify({
        'ok': True,
        'message': 'Пароль обновлён. Новый пароль передан пользователю.',
    })
