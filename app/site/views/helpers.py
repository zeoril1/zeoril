"""Общие рендер-хелперы профиля и гостевой страницы."""
from __future__ import annotations

import flask
from flask import render_template

from app.site.auth import SESSION_TTL, _cookie_secure
from app.site.music import list_music_files


def render_guest(message: str | None = None):
    flashed = list(flask.get_flashed_messages())
    message = message or (flashed[0] if flashed else None)
    return render_template(
        'index.html',
        logged=False,
        message=message,
    )


def render_profile(user, rights, message: str | None = None,
                   show_select: bool = False):
    is_admin = 'Admin' in rights
    is_music = is_admin or 'Music' in rights or 'Music_ALL' in rights
    can_download = is_admin or 'Music_down' in rights
    music_files = list_music_files() if show_select else None
    flashed = list(flask.get_flashed_messages())
    message = message or (flashed[0] if flashed else None)
    return render_template(
        'index.html',
        logged=True,
        user=user,
        is_admin=is_admin,
        is_music=is_music,
        can_download=can_download,
        show_select=show_select,
        music_files=music_files,
        message=message,
    )


def _set_auth_cookies(resp, token: str, user_id) -> None:
    """Устанавливает cookie Auth и Id с общими параметрами."""
    max_age = int(SESSION_TTL.total_seconds())
    resp.set_cookie('Auth', token, httponly=True, samesite='Lax',
                    secure=_cookie_secure(), max_age=max_age)
    resp.set_cookie('Id', str(user_id), httponly=True, samesite='Lax',
                    secure=_cookie_secure(), max_age=max_age)
