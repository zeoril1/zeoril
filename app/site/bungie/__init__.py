"""Bungie OAuth 2.0: вход через Bungie.net и привязка аккаунта Destiny 2.

Пакет заменил бывший модуль bungie.py. Публичный интерфейс сохранён —
``from app.site.bungie import ...`` работает как раньше.

Подмодули:
  * config — настройки, константы URL, общие хелперы страниц;
  * oauth  — вход/выход и привязка Bungie-аккаунта;
  * api    — запросы к Bungie API (профиль, инвентарь, обновление токена).
"""
from __future__ import annotations

from app.site.bungie.api import get_user_inventory
from app.site.bungie.config import (BUNGIE_AUTH_URL, BUNGIE_MEMBERSHIPS_URL,
                                    BUNGIE_TOKEN_URL, DESTINY_MEMBERSHIP_TYPES,
                                    bungie_config)
from app.site.bungie.oauth import (bungie_callback, bungie_login, bungie_unlink)

__all__ = [
    'BUNGIE_AUTH_URL', 'BUNGIE_TOKEN_URL', 'BUNGIE_MEMBERSHIPS_URL',
    'DESTINY_MEMBERSHIP_TYPES',
    'bungie_config', 'bungie_login', 'bungie_callback', 'bungie_unlink',
    'get_user_inventory',
]
