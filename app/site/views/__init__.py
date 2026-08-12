"""HTTP-роуты сайта.

Пакет заменил бывший модуль views.py. Единый blueprint 'views' (имя
сохранено — на него ссылаются шаблоны через url_for('views.*') и
app.py). Роуты регистрируются в подмодулях при импорте.

Подмодули:
  * index     — главная (вход, профиль), регистрация;
  * users     — администрирование пользователей и прав;
  * logs      — журнал действий и сообщений;
   * destiny   — список предметов Destiny 2 и челленджи;
   * inventory — инвентарь привязанного Bungie-аккаунта;
   * collections — коллекции Destiny 2 (вкладка «Коллекция»);
   * music     — музыка: админка, AJAX, скачивание;
   * misc      — выход, Discord/Bungie OAuth, конфиг-сервис.
"""
from __future__ import annotations

from app.site.views.blueprint import bp
from app.site.views import (
    collections, destiny, index, inventory, logs, misc, music, users,  # noqa: F401
)


__all__ = ['bp']
