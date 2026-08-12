"""Музыка: админка, AJAX-список и скачивание файлов."""
from __future__ import annotations

import flask
from flask import redirect, render_template, request, send_from_directory

from app import database
from app.paths import MUSIC_DIR
from app.site.auth import current_user, get_user_by_id, user_rights, validate_csrf, validate_csrf_json
from app.site.music import list_music_files, save_music
from app.site.views.blueprint import bp


def render_music_admin(message: str | None = None,
                       selected_user: dict | None = None):
    with database.db() as conn:
        rows = database.execute(
            conn,
            'SELECT id, name_discord, song FROM users ORDER BY name_discord'
        ).fetchall()
        users_with_song = [dict(r) for r in rows]
    return render_template('song.html', users=users_with_song,
                           music_files=list_music_files(), message=message,
                           selected_user=selected_user)


@bp.route('/song', methods=['GET', 'POST'])
def song():
    user = current_user()
    if user is None:
        return redirect('/')
    rights = user_rights(user['id'])
    if 'Admin' not in rights and 'Music_ALL' not in rights:
        return render_template('not_rights.html')

    if request.method == 'POST':
        validate_csrf()
        action = request.form.get('action')
        if action == 'save_song':
            uid = (request.form.get('Name') or '').strip()
            new_music = (request.form.get('new_music') or '').strip()
            if (uid.isdigit() and new_music
                    and new_music in list_music_files()
                    and get_user_by_id(uid) is not None):
                with database.db() as conn:
                    database.execute(
                        conn, 'UPDATE users SET song = %s WHERE id = %s',
                        (new_music, uid))
            return redirect('/song')
        upload = request.files.get('music')
        if upload is not None and upload.filename:
            _ok, msg = save_music(upload)
            return render_music_admin(message=msg)
        return render_music_admin()

    uid = request.args.get('Name')
    selected_user = None
    if uid and uid.isdigit():
        selected_user = get_user_by_id(uid)
    return render_music_admin(message=None, selected_user=selected_user)


@bp.route('/song/api/music_list')
def song_api_music_list():
    """AJAX: список музыки и текущий трек выбранного пользователя."""
    user = current_user()
    if user is None:
        return flask.jsonify({'ok': False, 'error': 'Не авторизован'}), 401
    rights = user_rights(user['id'])
    if 'Admin' not in rights and 'Music_ALL' not in rights:
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
            'song': target.get('song') or '',
        },
        'music_files': list_music_files(),
    })


@bp.route('/song/api/save_song', methods=['POST'])
def song_api_save_song():
    """AJAX: сохранить выбранную музыку пользователю."""
    user = current_user()
    if user is None:
        return flask.jsonify({'ok': False, 'error': 'Не авторизован'}), 401
    rights = user_rights(user['id'])
    if 'Admin' not in rights and 'Music_ALL' not in rights:
        return flask.jsonify({'ok': False, 'error': 'Недостаточно прав'}), 403
    if not validate_csrf_json():
        return flask.jsonify({'ok': False, 'error': 'Неверный CSRF-токен'}), 400
    payload = request.get_json(silent=True) or {}
    uid = (payload.get('user_id') or '').strip()
    new_music = (payload.get('new_music') or '').strip()
    if not uid.isdigit():
        return flask.jsonify({'ok': False, 'error': 'Некорректный ID пользователя'}), 400
    target = get_user_by_id(uid)
    if target is None:
        return flask.jsonify({'ok': False, 'error': 'Пользователь не найден'}), 404
    if new_music not in list_music_files():
        return flask.jsonify({'ok': False, 'error': 'Файл не найден в библиотеке'}), 400
    with database.db() as conn:
        database.execute(
            conn, 'UPDATE users SET song = %s WHERE id = %s',
            (new_music, uid))
    return flask.jsonify({'ok': True, 'song': new_music})


@bp.route('/music/<path:filename>')
def download_file(filename):
    user = current_user()
    if user is None:
        return flask.abort(403)
    rights = user_rights(user['id'])
    if user.get('song') == filename:
        return send_from_directory(MUSIC_DIR, filename)
    if ('Admin' in rights or 'Music_down' in rights
            or 'Music_ALL' in rights):
        return send_from_directory(MUSIC_DIR, filename)
    return flask.abort(403)
