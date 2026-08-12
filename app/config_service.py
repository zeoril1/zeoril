"""Клиент конфиг-сервиса: значения конфигурации приходят только отсюда.

В .env/os.environ лежат лишь «ссылки»: CONFIG_SERVICE_URL,
CONFIG_PROJECT_NAME, CONFIG_PROJECT_DB_NAME, CONFIG_TOKEN.
Токен доступа хранится в resources/config_token.txt (общий volume сайта
и бота) или задаётся переменной CONFIG_TOKEN.
"""
from __future__ import annotations

import io
import logging
import os
import time
from pathlib import Path

import requests
from dotenv import dotenv_values

from app.paths import CONFIG_TOKEN_FILE as TOKEN_FILE

logger = logging.getLogger('config_service')

# Логируем в stdout, если вызывающий код ещё не настроил логирование.
if not logger.handlers and not logging.root.handlers:
    logging.basicConfig(level=logging.INFO,
                        format='%(asctime)s %(levelname)s %(name)s: %(message)s')


def _in_docker() -> bool:
    return os.environ.get('DOCKER') == '1' or Path('/.dockerenv').exists()


def in_docker() -> bool:
    """True, если процесс выполняется внутри docker-контейнера."""
    return _in_docker()


CONFIG_PROJECT_NAME = os.environ.get('CONFIG_PROJECT_NAME', 'discord')
CONFIG_DB_PROJECT_NAME = os.environ.get('CONFIG_PROJECT_DB_NAME', 'postgress')


def _detect_config_service_url() -> str:
    """Определяет адрес конфиг-сервиса.

    В docker адреса localhost переписываются на host.docker.internal;
    по умолчанию — http://host.docker.internal:8420 (docker) или
    http://localhost:8420 (локально).
    """
    if 'CONFIG_SERVICE_URL' in os.environ:
        url = (os.environ['CONFIG_SERVICE_URL'] or '').strip()
        if _in_docker() and (url.startswith('http://localhost')
                             or url.startswith('http://127.0.0.1')):
            logger.warning(
                'CONFIG_SERVICE_URL=%s переписан на host.docker.internal '
                '(внутри docker-контейнера localhost — сам контейнер)', url)
            host_part = url.split('://', 1)[1].split('/', 1)[0]  # host:port
            if ':' in host_part:
                port = host_part.rsplit(':', 1)[1]
            else:
                port = '80'
            return f'http://host.docker.internal:{port}'
        return url
    if _in_docker():
        return 'http://host.docker.internal:8420'
    return 'http://localhost:8420'


CONFIG_SERVICE_URL = _detect_config_service_url()

# Результат кэшируем, чтобы не дёргать сервис на каждый запрос.
# Негативный результат проверяем чаще, чтобы окно с токеном закрылось сразу.
CACHE_TTL = float(os.environ.get('CONFIG_CACHE_TTL', '60'))
FAIL_CHECK_TTL = float(os.environ.get('CONFIG_FAIL_CHECK_TTL', '5'))
_CACHE: dict[str, dict] = {}


def _config_url(project: str) -> str:
    """Базовый URL конфига проекта (без ?format=env)."""
    return f'{CONFIG_SERVICE_URL.rstrip("/")}/config/{project}'


def _project_cache(project: str) -> dict:
    """Возвращает кэш-запись для проекта, создавая её при необходимости."""
    return _CACHE.setdefault(project, {
        'data': None, 'loaded_at': 0.0, 'ok': None, 'checked_at': 0.0,
    })


# --------------------------------------------------------------------------- #
# Работа с файлом токена
# --------------------------------------------------------------------------- #

def _read_token_file() -> str | None:
    """Читает токен из resources/config_token.txt (общий volume)."""
    try:
        return TOKEN_FILE.read_text(encoding='utf-8').strip() or None
    except OSError:
        return None


def _write_token_file(token: str) -> None:
    """Сохраняет токен в resources/config_token.txt (общий volume)."""
    try:
        TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
        TOKEN_FILE.write_text(token.strip() + '\n', encoding='utf-8')
        logger.info('Токен конфиг-сервиса сохранён в %s', TOKEN_FILE)
    except OSError as exc:
        logger.warning('Не удалось сохранить токен в %s: %s', TOKEN_FILE, exc)
        raise


def _effective_token() -> str | None:
    """Возвращает действующий токен: файл → переменная окружения."""
    token = _read_token_file()
    if token is None:
        token = (os.environ.get('CONFIG_TOKEN') or '').strip() or None
    return token


def save_token(token: str) -> bool:
    """Сохраняет токен и сразу проверяет его на конфиг-сервисе.

    Возвращает True, если токен принят (сервис отдал конфиг), иначе False.
    """
    token = (token or '').strip()
    if not token:
        return False
    _write_token_file(token)
    # Сбрасываем кэш, чтобы повторные запросы пошли с новым токеном.
    for cache in _CACHE.values():
        cache['data'] = None
        cache['ok'] = None
        cache['checked_at'] = 0.0
    try:
        _load_from_service(CONFIG_PROJECT_NAME)
        cache = _project_cache(CONFIG_PROJECT_NAME)
        cache['ok'] = True
        cache['checked_at'] = time.time()
        return True
    except requests.HTTPError as exc:
        code = exc.response.status_code if exc.response is not None else 0
        logger.warning('Токен отклонён конфиг-сервисом (%s)', code)
        return False
    except requests.RequestException as exc:
        logger.warning('Не удалось проверить токен (%s)', exc)
        return False


# --------------------------------------------------------------------------- #
# Загрузка конфига
# --------------------------------------------------------------------------- #

def _load_from_service(project: str) -> dict[str, str]:
    """Запрашивает конфиг проекта у сервиса в формате .env."""
    url = f'{_config_url(project)}?format=env'
    token = _effective_token()
    headers = {'Authorization': f'Bearer {token}'} if token else {}
    logger.info('Загружаем конфиг проекта "%s" из %s%s',
                project, url,
                ' (с токеном)' if token else ' (без токена)')
    resp = requests.get(url, headers=headers, timeout=5)
    resp.raise_for_status()
    values = dotenv_values(stream=io.StringIO(resp.text))
    return {k: v for k, v in values.items() if v}


def is_available() -> bool:
    """Готов ли бот Discord к запуску (конфиг с DISCORD_BOT_TOKEN получен).

    Значение берётся только из конфиг-сервиса; пока недоступно — сайт
    показывает блокирующее окно ввода токена.
    """
    now = time.time()
    cache = _project_cache(CONFIG_PROJECT_NAME)
    ok = cache.get('ok')
    checked_at = cache.get('checked_at') or 0.0
    # Позитивный результат перепроверяем реже (CACHE_TTL), негативный — чаще.
    ttl = CACHE_TTL if ok is True else FAIL_CHECK_TTL
    if now - checked_at < ttl:
        return bool(ok)

    ok = False
    try:
        config = _load_from_service(CONFIG_PROJECT_NAME)
        ok = bool((config.get('DISCORD_BOT_TOKEN') or '').strip())
    except Exception:
        ok = False

    cache['ok'] = ok
    cache['checked_at'] = now
    if ok:
        cache['data'] = None
    return ok


def invalidate() -> None:
    """Сбрасывает кэш конфига и статуса доступности конфиг-сервиса."""
    for cache in _CACHE.values():
        cache['data'] = None
        cache['loaded_at'] = 0.0
        cache['ok'] = None
        cache['checked_at'] = 0.0


def wait_for_config(timeout: float = float('inf')) -> bool:
    """Блокирующе ждёт, пока конфиг с токеном бота станет доступен."""
    deadline = time.monotonic() + timeout
    delay = 2.0
    while True:
        invalidate()
        if is_available():
            return True
        if time.monotonic() >= deadline:
            return False
        logger.info('DISCORD_BOT_TOKEN ещё не доступен (конфиг-сервис '
                    'требует токен или недоступен). Повторная проверка '
                    'через %.0f с...', delay)
        time.sleep(delay)
        delay = min(delay * 1.5, 15.0)


def load_project_config(project: str) -> dict[str, str]:
    """Возвращает конфиг проекта из конфиг-сервиса.

    При недоступности сервиса — пустой словарь (значения из .env
    не подставляются). Результат кэшируется на CACHE_TTL.
    """
    now = time.time()
    cache = _project_cache(project)
    cached = cache['data']
    if cached is not None and now - cache['loaded_at'] < CACHE_TTL:
        return cached

    data: dict[str, str] = {}
    try:
        data = _load_from_service(project)
        logger.info('Конфиг проекта "%s" получен из конфиг-сервиса '
                    '(%d ключей)', project, len(data))
        cache['ok'] = True
    except Exception as exc:
        logger.warning('Конфиг проекта "%s" не получен из %s (%s). '
                       'Значения из .env / os.environ не используются.',
                       project, CONFIG_SERVICE_URL, exc)
        cache['ok'] = False

    cache['data'] = data
    cache['loaded_at'] = now
    cache['checked_at'] = now
    return data


def load_config() -> dict[str, str]:
    """Возвращает конфиг основного проекта ('discord'): DISCORD_* и пр."""
    return load_project_config(CONFIG_PROJECT_NAME)


def load_db_config() -> dict[str, str]:
    """Возвращает конфиг проекта БД ('postgress'): параметры PostgreSQL."""
    return load_project_config(CONFIG_DB_PROJECT_NAME)


def get(key: str, default: str | None = None,
        project: str | None = None) -> str | None:
    """Возвращает значение ключа ИСКЛЮЧИТЕЛЬНО из конфиг-сервиса.

    По умолчанию берётся основной проект (discord). Для параметров БД
    передавайте ``project=CONFIG_DB_PROJECT_NAME`` или используйте ``get_db``.
    """
    if project is None:
        project = CONFIG_PROJECT_NAME
    value = load_project_config(project).get(key)
    return value if value is not None else default


def get_db(key: str, default: str | None = None) -> str | None:
    """Возвращает значение ключа из проекта БД ('postgress')."""
    return get(key, default, project=CONFIG_DB_PROJECT_NAME)
