"""Журнал действий и сообщений пользователей."""
from __future__ import annotations

from datetime import datetime, timezone

from flask import redirect, render_template

from app import database
from app.paths import LOGS_FILE
from app.site.auth import current_user, user_rights
from app.site.views.blueprint import bp


# Русские подписи типов действий для шаблона.
ACTION_LABELS = {
    'voice_join': 'зашёл в голосовой канал',
    'voice_leave': 'вышел из голосового канала',
    'voice_move': 'перешёл в голосовой канал',
    'guild_join': 'присоединился к серверу',
    'guild_leave': 'покинул сервер',
    'song_play': 'воспроизвёл звук',
    'message_delete': 'удалил сообщение',
    'message_edit': 'изменил сообщение',
}


def _format_log_date(value) -> str:
    """Форматирует дату из БД в читаемый вид (всегда по UTC)."""
    if not value:
        return '—'
    try:
        dt = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        # Приводим к UTC независимо от часового пояса БД/сервера.
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        dt = dt.astimezone(timezone.utc)
        return dt.strftime('%d.%m.%Y %H:%M:%S') + ' UTC'
    except (ValueError, TypeError):
        return str(value)


@bp.route('/logs')
def logs():
    user = current_user()
    if user is None:
        return redirect('/')
    rights = user_rights(user['id'])
    if 'Admin' not in rights:
        return render_template('not_rights.html')

    actions = database.get_recent_actions(limit=200)
    messages = database.get_recent_messages(limit=200)

    try:
        with open(LOGS_FILE, 'r', encoding='utf-8') as f:
            content = f.read()
    except (FileNotFoundError, UnicodeDecodeError):
        content = ''

    return render_template(
        'logs.html',
        log_content=content,
        actions=actions,
        messages=messages,
        action_labels=ACTION_LABELS,
        format_log_date=_format_log_date,
    )
