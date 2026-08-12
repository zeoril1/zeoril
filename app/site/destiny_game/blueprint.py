"""Общие настройки и инфраструктура мини-игры (лобби и рулетка).

Содержит blueprint ``bp``, константы игры, глобальный словарь лобби и функцию
рассылки событий. Вынесено в отдельный модуль, чтобы остальные части пакета
(лобби, рулетка, страницы, API) могли переиспользовать общее состояние без
циклических импортов.
"""
from __future__ import annotations

import logging
import queue
import threading

from flask import Blueprint

logger = logging.getLogger('BotSite')

bp = Blueprint('destiny_game', __name__)

# Сколько секунд крутится колесо (должно совпадать с CSS transition).
ROLL_ANIMATION_SECONDS = 6.0
# Максимум иконок на колесе (включая выпавшее оружие).
MAX_WHEEL_ITEMS = 12
MIN_WHEEL_ITEMS = 4
# Лобби без активности живёт не дольше этого времени.
LOBBY_TTL = 60 * 60 * 3
# Сколько последних результатов хранить в лобби.
HISTORY_LIMIT = 20

_lock = threading.RLock()
_lobbies: dict[str, 'Lobby'] = {}


def _broadcast(lobby, event: str, data) -> None:
    """Рассылает событие всем подписчикам SSE-потока лобби."""
    message = (event, data)
    for q in list(lobby.subscribers):
        try:
            q.put_nowait(message)
        except queue.Full:
            pass
