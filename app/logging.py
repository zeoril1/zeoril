"""Общая настройка логирования для бота и сайта.

Логи пишутся в stdout (для `docker logs`) и в resources/logs.txt
(общий volume сайта и бота).
"""
from __future__ import annotations

import logging
import os

from app.paths import LOGS_FILE


class NoBadRequestFilter(logging.Filter):
    """Отбрасывает шумные записи werkzeug о бинарных запросах."""

    def filter(self, record: logging.LogRecord) -> bool:
        if record.name != 'werkzeug':
            return True
        msg = record.getMessage()
        return ('Bad request syntax' not in msg
                and 'Bad request version' not in msg)


def setup_logging(name: str, filter_werkzeug: bool = False) -> logging.Logger:
    """Настраивает логирование и возвращает логгер с именем ``name``."""
    fmt = logging.Formatter('%(asctime)s %(levelname)s %(name)s: %(message)s')

    stdout = logging.StreamHandler()
    stdout.setFormatter(fmt)

    handlers: list[logging.Handler] = [stdout]
    try:
        os.makedirs(os.path.dirname(LOGS_FILE), exist_ok=True)
        file_handler = logging.FileHandler(LOGS_FILE, encoding='utf-8')
        file_handler.setFormatter(fmt)
        handlers.append(file_handler)
    except OSError as exc:
        logging.getLogger(name).warning(
            'Не удалось открыть файл логов %s: %s', LOGS_FILE, exc)

    logging.basicConfig(level=logging.INFO, handlers=handlers)
    if filter_werkzeug:
        logging.getLogger('werkzeug').addFilter(NoBadRequestFilter())
    return logging.getLogger(name)
