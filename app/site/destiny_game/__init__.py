"""Мини-игра: лобби и рулетка челленджей Destiny 2.

Пакет заменил бывший модуль destiny_game.py. Публичный интерфейс сохранён —
``from app.site.destiny_game import bp`` работает как раньше.

Подмодули:
  * blueprint — blueprint ``bp``, константы, общее состояние и рассылка событий;
  * lobby     — класс Lobby и управление лобби (вход/выход, ходы, завершение);
  * roulette  — колесо рулетки и логика броска (в т.ч. реролл);
  * views     — страницы (GET) и SSE-поток лобби;
  * api       — JSON-эндпоинты рулетки.
"""
from __future__ import annotations

from app.site.destiny_game.blueprint import bp
from app.site.destiny_game import api, views  # noqa: F401  (регистрируют роуты)

__all__ = ['bp']
