"""Подключение к PostgreSQL: URL, connect, db, execute."""
from __future__ import annotations

import logging
from contextlib import contextmanager
from urllib.parse import quote_plus

import psycopg2
import psycopg2.extras

from app import config_service

logger = logging.getLogger('db')


# --------------------------------------------------------------------------- #
# Определение строки подключения
# --------------------------------------------------------------------------- #

def _build_database_url_from_pg() -> str | None:
    """Собирает postgresql:// URL из конфиг-сервиса (проект 'postgress')."""
    user = config_service.get_db('PGUSER')
    dbname = config_service.get_db('PGDATABASE')
    if not user or not dbname:
        return None
    password = config_service.get_db('PGPASSWORD') or ''
    port = config_service.get_db('PGPORT') or '5432'
    # Внутри docker-сети БД доступна по имени сервиса 'db'; вне docker —
    # PGHOST из конфиг-сервиса (или localhost).
    if config_service.in_docker():
        host = 'db'
    else:
        host = config_service.get_db('PGHOST') or 'localhost'
    # Спецсимволы в пароле/логине/имени БД URL-кодируем.
    return (f'postgresql://{quote_plus(user)}:{quote_plus(password)}'
            f'@{host}:{port}/{quote_plus(dbname)}')


def _resolve_database_url() -> str:
    """Определяет строку подключения к PostgreSQL из конфиг-сервиса."""
    url = _build_database_url_from_pg()
    if url:
        logger.info('Параметры PostgreSQL получены из конфиг-сервиса '
                    '(проект "%s")', config_service.CONFIG_DB_PROJECT_NAME)
        return url
    logger.error(
        'Параметры PostgreSQL не получены из конфиг-сервиса (проект "%s"). '
        'Значения должны храниться ТОЛЬКО в конфиг-сервисе: '
        'PGUSER, PGDATABASE, PGPASSWORD, PGPORT (опционально PGHOST).',
        config_service.CONFIG_DB_PROJECT_NAME)
    if config_service.in_docker():
        return 'postgresql://postgres:postgres@db:5432/postgres'
    return 'postgresql://postgres:postgres@localhost:5432/postgres'


DATABASE_URL = _resolve_database_url()


def connect():
    """Создаёт подключение к PostgreSQL (транзакции по умолчанию)."""
    return psycopg2.connect(
        DATABASE_URL,
        cursor_factory=psycopg2.extras.RealDictCursor,
    )


@contextmanager
def db():
    """Контекстный менеджер: подключение + commit/rollback/close."""
    conn = connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def execute(conn, sql, params=None):
    """Выполняет запрос и возвращает курсор (RealDictCursor)."""
    cur = conn.cursor()
    cur.execute(sql, params)
    return cur
