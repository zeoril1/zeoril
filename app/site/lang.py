"""Язык интерфейса сайта.

Выбор языка хранится в cookie ``lang`` (значения: en / ru) и действует на
всех страницах. Значение подставляется в шаблоны через контекст-процессор
приложения (см. ``app.site.app``) как глобальная переменная ``lang``, а для
скриптов страниц — через ``window.SITE_LANG`` в ``base.html``.
"""
from __future__ import annotations

import flask

# Доступные языки: код -> подпись в переключателе.
LANGS: dict[str, str] = {
    'en': 'EN',
    'ru': 'RU',
}

DEFAULT_LANG = 'en'


def get_lang() -> str:
    """Возвращает язык из cookie ``lang`` (по умолчанию ``en``)."""
    lang = flask.request.cookies.get('lang') or DEFAULT_LANG
    return lang if lang in LANGS else DEFAULT_LANG
