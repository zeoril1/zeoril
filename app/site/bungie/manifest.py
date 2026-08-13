"""Destiny 2 Manifest: локальное дерево коллекций.

Bungie отдаёт манифест как ZIP-архив, внутри которого лежит SQLite-файл
(таблицы ``DestinyPresentationNodeDefinition``, ``DestinyCollectibleDefinition``
и др.). Этот модуль:

  * скачивает/обновляет манифест (``manifest.content``);
  * распаковывает sqlite и строит дерево коллекций от корневого узла
    ``Items`` (``presentationNodeHash = 3790247699``);
  * по запросу возвращает листья дерева: категории с предметами
    (иконка, itemHash) и подкатегории.

Идемпотентно: файл манифеста и распакованная БД кладутся в ``resources``
и переиспользуются между запросами. Обновление происходит, если файла нет
или он повреждён.
"""
from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
import time
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

from app import paths

logger = logging.getLogger('BotSite')

# Корневой узел коллекций в DestinyPresentationNodeDefinition ("Items").
COLLECTIONS_ROOT_HASH = 3790247699

# Файлы на диске (в resources/, общие для всех пользователей).
MANIFEST_FILE = paths.RESOURCES_DIR / 'manifest.content'
SQLITE_FILE = paths.RESOURCES_DIR / 'manifest.sqlite3'

# Маркер версии скачанного манифеста (версия из DestinyManifest Bungie).
MANIFEST_VERSION_FILE = paths.RESOURCES_DIR / 'manifest_version.txt'

# Доступные локали манифеста (код языка).
LOCALES = ('en', 'ru')
DEFAULT_LOCALE = 'en'

# URL манифеста Destiny 2 (публичный, авторизация не нужна).
MANIFEST_ENDPOINT = (
    'https://www.bungie.net/Platform/Destiny2/Manifest/'
)

# Еженедельный ресет Destiny: вторник 22:00 UTC+3 (= 19:00 UTC).
WEEKLY_RESET_HOUR_UTC = 19

# Подкаталог для кэша в resources/ (на случай, если хотим держать рядом).
CACHE_DIR = paths.RESOURCES_DIR

# Блокировка на загрузку/распаковку манифеста (один поток за раз).
_manifest_lock = threading.Lock()


def _signed_id(hash_value: int) -> int:
    """Приводит uint hash к signed 32-bit, как хранят id в sqlite."""
    h = int(hash_value) & 0xFFFFFFFF
    return h if h < 2 ** 31 else h - 2 ** 32


def _unsigned_id(raw: int) -> int:
    """Обратное преобразование: signed id из sqlite → uint hash."""
    return int(raw) & 0xFFFFFFFF


def _manifest_paths(locale: str) -> tuple[Path, Path]:
    """Возвращает пути (zip, sqlite) файлов манифеста для локали."""
    if locale == 'en':
        return MANIFEST_FILE, SQLITE_FILE
    return (paths.RESOURCES_DIR / f'manifest_{locale}.content',
            paths.RESOURCES_DIR / f'manifest_{locale}.sqlite3')


class ManifestError(RuntimeError):
    """Ошибка загрузки/обработки манифеста Destiny 2."""


def _is_valid_sqlite(path: Path) -> bool:
    """Проверяет, что файл — рабочая sqlite-база с нужными таблицами."""
    if not path.is_file():
        return False
    try:
        con = sqlite3.connect(str(path))
        try:
            cur = con.cursor()
            row = cur.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                ('DestinyPresentationNodeDefinition',),
            ).fetchone()
            return row is not None
        finally:
            con.close()
    except sqlite3.DatabaseError:
        return False


def _fetch_manifest_url(locale: str = DEFAULT_LOCALE) -> str | None:
    """Возвращает URL актуального файла манифеста для локали (или None)."""
    try:
        resp = requests.get(MANIFEST_ENDPOINT, timeout=15)
        resp.raise_for_status()
        data = resp.json().get('Response') or {}
        return data.get('mobileWorldContentPaths', {}).get(locale) or None
    except (requests.RequestException, ValueError) as exc:
        logger.warning('Не удалось получить ссылку на манифест (%s): %s',
                       locale, exc)
        return None


def _download_manifest(locale: str = DEFAULT_LOCALE) -> None:
    """Скачивает и распаковывает манифест нужной локали в resources/."""
    url = _fetch_manifest_url(locale)
    if not url:
        raise ManifestError(
            f'Не удалось получить ссылку на манифест Bungie ({locale}).')
    _download_manifest_url(locale, url)


def _download_manifest_url(locale: str, url: str) -> None:
    """Скачивает манифест по конкретному URL и атомарно сохраняет в resources/."""
    zip_path, sqlite_path = _manifest_paths(locale)

    # Путь у Bungie абсолютный, начинается с '/', добавляем хост.
    full_url = url if url.startswith('http') else 'https://www.bungie.net' + url
    try:
        resp = requests.get(full_url, timeout=60)
        resp.raise_for_status()
        content = resp.content
    except requests.RequestException as exc:
        logger.warning('Ошибка скачивания манифеста: %s', exc)
        raise ManifestError('Не удалось скачать манифест Bungie.') from exc

    # Манифест — это ZIP с одним sqlite-файлом внутри.
    try:
        with zipfile.ZipFile(io_bytes(content)) as zf:
            name = zf.namelist()[0]
            with zf.open(name) as f:
                sqlite_bytes = f.read()
    except (zipfile.BadZipFile, KeyError, IndexError) as exc:
        logger.warning('Манифест пришёл не в формате ZIP: %s', exc)
        raise ManifestError('Манифест Bungie повреждён.') from exc

    try:
        # Пишем сначала во временный файл, затем атомарно переименовываем,
        # чтобы не оставить обрезанный манифест при сбое.
        tmp_sql = CACHE_DIR / (sqlite_path.name + '.tmp')
        with open(tmp_sql, 'wb') as f:
            f.write(sqlite_bytes)
        os.replace(tmp_sql, sqlite_path)

        tmp_zip = CACHE_DIR / (zip_path.name + '.tmp')
        with open(tmp_zip, 'wb') as f:
            f.write(content)
        os.replace(tmp_zip, zip_path)
    except OSError as exc:
        logger.warning('Не удалось сохранить манифест: %s', exc)
        raise ManifestError('Не удалось сохранить манифест Bungie.') from exc

    logger.info('Манифест (%s) обновлён: %d байт (sqlite %d байт)',
                locale, len(content), len(sqlite_bytes))


def io_bytes(data: bytes) -> object:
    """Возвращает BytesIO-объект (для изоляции импорта в тестах)."""
    import io
    return io.BytesIO(data)


# --------------------------------------------------------------------------- #
# Версионирование и плановое/ручное обновление
# --------------------------------------------------------------------------- #

def _stored_version() -> str:
    """Возвращает сохранённую версию манифеста (или '')."""
    try:
        return MANIFEST_VERSION_FILE.read_text(encoding='utf-8').strip()
    except OSError:
        return ''


def _save_version(version: str) -> None:
    """Сохраняет версию скачанного манифеста."""
    try:
        MANIFEST_VERSION_FILE.write_text(version, encoding='utf-8')
    except OSError:
        logger.warning('Не удалось сохранить версию манифеста: %s', version)


def get_current_manifest_info() -> dict:
    """Возвращает {'version': str, 'paths': {locale: url}} текущего манифеста.

    ``paths`` — только для доступных локалей. При ошибке возвращает {}.
    """
    try:
        resp = requests.get(MANIFEST_ENDPOINT, timeout=15)
        resp.raise_for_status()
        data = resp.json().get('Response') or {}
        version = data.get('version') or ''
        paths = data.get('mobileWorldContentPaths') or {}
        return {
            'version': version,
            'paths': {loc: paths.get(loc) for loc in LOCALES
                      if paths.get(loc)},
        }
    except (requests.RequestException, ValueError) as exc:
        logger.warning('Не удалось получить информацию о манифесте: %s', exc)
        return {}


def update_manifests(force: bool = False) -> dict:
    """Проверяет и (при необходимости) обновляет манифесты всех локалей.

    ``force=False`` — скачивает только если версия Bungie отличается от
    сохранённой (используется еженедельным планировщиком).
    ``force=True`` — всегда перекачивает (кнопка «Обновить манифесты»).

    Возвращает словарь: ok, updated, version, locales {locale: 'ok'|'error'|'skipped'},
    error (None, если ok).
    """
    info = get_current_manifest_info()
    if not info.get('paths'):
        return {
            'ok': False, 'updated': False, 'version': '', 'locales': {},
            'error': 'Не удалось получить информацию о манифестах.',
        }
    version = info.get('version') or ''
    if not force and version and version == _stored_version():
        return {
            'ok': True, 'updated': False, 'version': version,
            'locales': {loc: 'skipped' for loc in LOCALES},
            'error': None,
        }

    with _manifest_lock:
        locales: dict[str, str] = {}
        for loc in LOCALES:
            url = info['paths'].get(loc)
            if not url:
                locales[loc] = 'error'
                continue
            try:
                _download_manifest_url(loc, url)
                locales[loc] = 'ok'
            except ManifestError as exc:
                logger.warning('Не удалось обновить манифест (%s): %s',
                               loc, exc)
                locales[loc] = 'error'
        if any(v == 'ok' for v in locales.values()):
            _save_version(version)

    ok = any(v == 'ok' for v in locales.values())
    return {
        'ok': ok,
        'updated': ok,
        'version': version,
        'locales': locales,
        'error': None if ok else 'Не удалось обновить ни один манифест.',
    }


def get_manifests_last_updated() -> str | None:
    """Время последнего обновления манифестов (UTC+3) или None."""
    times = []
    for loc in LOCALES:
        _, sqlite_path = _manifest_paths(loc)
        try:
            times.append(sqlite_path.stat().st_mtime)
        except OSError:
            continue
    if not times:
        return None
    tz_msk = timezone(timedelta(hours=3))  # UTC+3 (Москва)
    return datetime.fromtimestamp(max(times), tz=tz_msk).strftime(
        '%d.%m.%Y %H:%M')


# --------------------------------------------------------------------------- #
# Еженедельное обновление: вторник 22:00 UTC+3 (19:00 UTC)
# --------------------------------------------------------------------------- #

def _next_tuesday_19utc() -> datetime:
    """Следующий вторник в 19:00 UTC (22:00 UTC+3)."""
    now = datetime.now(timezone.utc)
    # weekday(): Monday=0, Tuesday=1, ..., Sunday=6.
    days_ahead = (1 - now.weekday()) % 7
    target = (now + timedelta(days=days_ahead)).replace(
        hour=WEEKLY_RESET_HOUR_UTC, minute=0, second=0, microsecond=0)
    # Если сегодня вторник и время уже прошло — берём следующий вторник.
    if days_ahead == 0 and now >= target:
        target += timedelta(days=7)
    return target


def _manifest_scheduler_loop() -> None:
    """Цикл: спит до следующего вторника 19:00 UTC, затем обновляет манифесты."""
    while True:
        try:
            next_run = _next_tuesday_19utc()
            delta = (next_run - datetime.now(timezone.utc)).total_seconds()
            if delta > 0:
                time.sleep(delta)
            result = update_manifests(force=False)
            logger.info('Плановое обновление манифестов: %s', result)
        except Exception:
            logger.exception('Ошибка в планировщике обновления манифестов')
        # Защита от повторного срабатывания в ту же секунду/после ошибки.
        time.sleep(60)


_scheduler_started = False
_scheduler_lock = threading.Lock()


def start_manifest_scheduler() -> None:
    """Запускает фоновый поток еженедельного обновления манифестов.

    Идемпотентно: повторные вызовы ничего не делают.
    """
    global _scheduler_started
    with _scheduler_lock:
        if _scheduler_started:
            return
        _scheduler_started = True
    thread = threading.Thread(target=_manifest_scheduler_loop,
                              name='manifest-scheduler', daemon=True)
    thread.start()
    logger.info('Планировщик обновления манифестов запущен')


def ensure_manifest(locale: str = DEFAULT_LOCALE) -> Path:
    """Гарантирует наличие локального манифеста, возвращает путь к sqlite.

    Если файла нет или он повреждён — скачивает заново. Потокобезопасно.
    """
    locale = locale if locale in LOCALES else DEFAULT_LOCALE
    _, sqlite_path = _manifest_paths(locale)
    with _manifest_lock:
        if _is_valid_sqlite(sqlite_path):
            return sqlite_path
        logger.info('Манифест (%s) не найден/повреждён — скачиваем.', locale)
        _download_manifest(locale)
        if not _is_valid_sqlite(sqlite_path):
            raise ManifestError('Скачанный манифест не является SQLite-базой.')
        return sqlite_path


# --------------------------------------------------------------------------- #
# Чтение дерева коллекций
# --------------------------------------------------------------------------- #

class CollectibleTree:
    """Дерево коллекций Destiny 2: категории → подкатегории → предметы."""

    def __init__(self, node_defs: dict[int, dict],
                 collectible_defs: dict[int, dict]):
        self.node_defs = node_defs
        self.collectible_defs = collectible_defs

    def node(self, hash_value: int) -> dict | None:
        """Возвращает определение узла (DestinyPresentationNodeDefinition)."""
        return self.node_defs.get(int(hash_value) & 0xFFFFFFFF)

    def children(self, hash_value: int) -> dict:
        """Возвращает children узла (словарь списков)."""
        node = self.node(hash_value)
        if not node:
            return {}
        return node.get('children') or {}

    def collectible(self, hash_value: int) -> dict | None:
        """Возвращает определение коллекции (иконка, itemHash, имя)."""
        return self.collectible_defs.get(int(hash_value) & 0xFFFFFFFF)


def build_tree_from_sqlite(path: Path) -> CollectibleTree:
    """Читает манифест и возвращает CollectibleTree.

    Требует только ``DestinyPresentationNodeDefinition`` и
    ``DestinyCollectibleDefinition`` — их достаточно для дерева коллекций
    и иконок предметов.
    """
    node_defs: dict[int, dict] = {}
    collectible_defs: dict[int, dict] = {}

    con = sqlite3.connect(str(path))
    try:
        con.row_factory = sqlite3.Row
        cur = con.cursor()

        # DestinyPresentationNodeDefinition: id — signed 32-bit.
        cur.execute(
            'SELECT id, json FROM DestinyPresentationNodeDefinition')
        for r in cur.fetchall():
            key = _unsigned_id(r['id'])
            node_defs[key] = json.loads(r['json'])

        cur.execute(
            'SELECT id, json FROM DestinyCollectibleDefinition')
        for r in cur.fetchall():
            key = _unsigned_id(r['id'])
            collectible_defs[key] = json.loads(r['json'])
    finally:
        con.close()

    return CollectibleTree(node_defs, collectible_defs)


# Кэш дерева: locale -> {'mtime': mtime sqlite-файла, 'tree': CollectibleTree}.
# CollectibleTree после построения не мутируется (только чтение), поэтому
# кэш безопасен. Обновляется автоматически при изменении файла манифеста.
_tree_cache: dict[str, dict] = {}
_tree_cache_lock = threading.Lock()


def load_tree(locale: str = DEFAULT_LOCALE) -> CollectibleTree:
    """Загружает (при необходимости скачивает) дерево коллекций для локали.

    Результат кэшируется до тех пор, пока файл манифеста не изменился
    (проверяется mtime) — это экономит чтение ~10 МБ JSON при каждом
    запросе страницы. Кэш ведётся отдельно для каждой локали.
    """
    path = ensure_manifest(locale)
    mtime = path.stat().st_mtime
    with _tree_cache_lock:
        entry = _tree_cache.get(locale)
        if entry and entry.get('mtime') == mtime:
            return entry['tree']
    tree = build_tree_from_sqlite(path)
    with _tree_cache_lock:
        _tree_cache[locale] = {'mtime': mtime, 'tree': tree}
    return tree



# --------------------------------------------------------------------------- #
# Построение категорий для отображения
# --------------------------------------------------------------------------- #

def _collectible_view(tree: CollectibleTree, collectible_hash: int) -> dict | None:
    """Превращает DestinyCollectibleDefinition в словарь для шаблона."""
    cdef = tree.collectible(collectible_hash)
    if not cdef:
        return None
    dp = cdef.get('displayProperties') or {}
    item_hash = cdef.get('itemHash')
    if item_hash is None:
        return None  # без itemHash нечего показывать
    return {
        'hash': collectible_hash,
        'item_hash': int(item_hash),
        'name': dp.get('name') or '',
        'description': dp.get('description') or '',
        'icon': dp.get('icon') or '',
        'source': cdef.get('sourceString') or '',
    }


def _node_view(tree: CollectibleTree, node_hash: int) -> dict | None:
    """Превращает DestinyPresentationNodeDefinition в dict узла дерева.

    Рекурсивно обходит вложенные ``presentationNodes`` любой глубины
    (например, Armor → Titan → PvE → Techsec Suit → предметы), поэтому
    каждый узел имеет единую структуру:

      * hash/name/icon — заголовок узла;
      * items — предметы, лежащие прямо в узле;
      * subgroups — вложенные узлы (та же структура).
    """
    node = tree.node(node_hash)
    if not node:
        return None
    dp = node.get('displayProperties') or {}
    children = node.get('children') or {}

    view: dict = {
        'hash': node_hash,
        'name': dp.get('name') or '',
        'icon': dp.get('icon') or '',
        'subgroups': [],
        'items': [],
    }

    # Вложенные под-категории любой глубины.
    for sub in children.get('presentationNodes') or []:
        sub_view = _node_view(tree, sub.get('presentationNodeHash'))
        if sub_view and (sub_view['subgroups'] or sub_view['items']):
            view['subgroups'].append(sub_view)

    # Предметы прямо в узле (например, Weapons → Primary → Auto Rifles).
    for c in children.get('collectibles') or []:
        item = _collectible_view(tree, c.get('collectibleHash'))
        if item:
            view['items'].append(item)

    return view



def build_collections_view(tree: CollectibleTree,
                           root_hash: int = COLLECTIONS_ROOT_HASH) -> list[dict]:
    """Возвращает список корневых категорий коллекций для страницы."""
    root = tree.node(root_hash)
    if not root:
        return []
    out: list[dict] = []
    for child in (root.get('children') or {}).get('presentationNodes') or []:
        view = _node_view(tree, child.get('presentationNodeHash'))
        if view and (view['subgroups'] or view['items']):
            out.append(view)
    return out
