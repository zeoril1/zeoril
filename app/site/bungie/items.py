"""Destiny 2: предметы из локального манифеста (замена таблицы destiny_items).

Имена, иконки, типы и редкости предметов читаются напрямую из
``DestinyInventoryItemDefinition`` локального манифеста в локали выбранного
языка. Чтобы не сканировать манифест (~39 тыс. JSON-записей) при каждом
запросе, из него лениво строится компактный sqlite-кэш
(``manifest_items_<locale>.sqlite`` в resources/) только с нужными полями и
индексами. Кэш пересобирается автоматически, когда меняется манифест
(проверяется mtime исходного файла).
"""
from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
from pathlib import Path

from app import paths
from app.site.bungie.manifest import DEFAULT_LOCALE, ensure_manifest, _unsigned_id

logger = logging.getLogger('BotSite')

# Поля, извлекаемые из DestinyInventoryItemDefinition.
_SELECT_FIELDS = (
    'hash, name, icon, description, item_type, item_type_display_name, '
    'tier_type_name, class_type, ammo_type, default_damage_type'
)

_CREATE_TABLE = '''
CREATE TABLE IF NOT EXISTS items (
    hash INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    icon TEXT NOT NULL DEFAULT '',
    description TEXT NOT NULL DEFAULT '',
    item_type INTEGER,
    item_type_display_name TEXT NOT NULL DEFAULT '',
    tier_type_name TEXT NOT NULL DEFAULT '',
    class_type INTEGER,
    ammo_type INTEGER,
    default_damage_type INTEGER
)
'''

# Блокировка пересборки кэша (один поток за раз).
_build_lock = threading.Lock()


def _cache_path(locale: str) -> Path:
    """Путь к компактному кэшу предметов для локали."""
    return paths.RESOURCES_DIR / f'manifest_items_{locale}.sqlite'


def _extract_item(raw_id: int, def_json: bytes | str) -> dict | None:
    """Извлекает нужные поля из JSON предмета (или None, если нет имени)."""
    try:
        data = json.loads(def_json)
    except (ValueError, TypeError):
        return None
    dp = data.get('displayProperties') or {}
    name = (dp.get('name') or '').strip()
    if not name:
        return None
    inv = data.get('inventory') or {}
    return {
        'hash': _unsigned_id(raw_id),
        'name': name,
        'icon': dp.get('icon') or '',
        'description': dp.get('description') or '',
        'item_type': data.get('itemType'),
        'item_type_display_name': data.get('itemTypeDisplayName') or '',
        'tier_type_name': inv.get('tierTypeName') or '',
        'class_type': data.get('classType'),
        'ammo_type': (data.get('equippingBlock') or {}).get('ammoType'),
        'default_damage_type': data.get('defaultDamageType'),
    }


def _rebuild_cache(locale: str, source: Path) -> None:
    """Пересобирает компактный кэш предметов из файла манифеста."""
    cache = _cache_path(locale)
    tmp = cache.with_name(cache.name + '.tmp')

    src = sqlite3.connect(str(source))
    dst = sqlite3.connect(str(tmp))
    try:
        src.row_factory = sqlite3.Row
        dst.execute(_CREATE_TABLE)
        cur = src.cursor()
        cur.execute('SELECT id, json FROM DestinyInventoryItemDefinition')
        rows: list[tuple] = []
        for r in cur.fetchall():
            item = _extract_item(r['id'], r['json'])
            if item:
                rows.append((
                    item['hash'], item['name'], item['icon'],
                    item['description'], item['item_type'],
                    item['item_type_display_name'], item['tier_type_name'],
                    item['class_type'], item['ammo_type'],
                    item['default_damage_type'],
                ))
        dst.executemany(
            'INSERT OR REPLACE INTO items '
            '(hash, name, icon, description, item_type, item_type_display_name,'
            ' tier_type_name, class_type, ammo_type, default_damage_type) '
            'VALUES (?,?,?,?,?,?,?,?,?,?)',
            rows,
        )
        dst.execute('CREATE INDEX IF NOT EXISTS idx_items_tier ON items(tier_type_name)')
        dst.execute('CREATE INDEX IF NOT EXISTS idx_items_type ON items(item_type)')
        dst.commit()
    finally:
        src.close()
        dst.close()
    os.replace(tmp, cache)
    logger.info('Кэш предметов (%s) пересобран: %d записей', locale, len(rows))


def _ensure_cache(locale: str) -> Path:
    """Возвращает путь к кэшу предметов, при необходимости пересобирая его."""
    source = ensure_manifest(locale)
    cache = _cache_path(locale)
    with _build_lock:
        try:
            src_mtime = source.stat().st_mtime
        except OSError:
            src_mtime = 0
        if cache.is_file():
            try:
                if cache.stat().st_mtime >= src_mtime:
                    return cache
            except OSError:
                pass
        _rebuild_cache(locale, source)
    return cache


def _connect(locale: str) -> sqlite3.Connection:
    """Открывает кэш предметов (при необходимости пересобирая его)."""
    con = sqlite3.connect(str(_ensure_cache(locale)))
    con.row_factory = sqlite3.Row
    return con


def get_items(locale: str = DEFAULT_LOCALE, limit: int = 50,
              tier_type_name: str | None = None,
              item_type: int | None = None,
              page: int = 1,
              only_filled: bool = False) -> tuple[list[dict], int]:
    """Возвращает страницу предметов из манифеста.

    ``limit`` — сколько записей выводить на страницу (до 1000).
    ``tier_type_name`` — фильтр по редкости (например, 'Legendary').
    ``item_type`` — фильтр по числовому типу предмета.
    ``page`` — номер страницы (с 1).
    ``only_filled`` — только предметы с описанием.

    Возвращает кортеж (записи страницы, общее число найденных предметов).
    """
    limit = max(1, min(int(limit), 1000))
    page = max(1, int(page))
    offset = (page - 1) * limit

    where = 'WHERE 1=1'
    params: list = []
    if tier_type_name:
        where += ' AND tier_type_name = ?'
        params.append(tier_type_name)
    if item_type is not None:
        where += ' AND item_type = ?'
        params.append(int(item_type))
    if only_filled:
        where += " AND description IS NOT NULL AND description <> ''"

    con = _connect(locale)
    try:
        cur = con.cursor()
        cur.execute('SELECT COUNT(*) AS cnt FROM items ' + where, params)
        total = int(cur.fetchone()['cnt'])
        cur.execute(
            'SELECT ' + _SELECT_FIELDS + ' FROM items ' + where +
            ' ORDER BY name ASC LIMIT ? OFFSET ?',
            params + [limit, offset],
        )
        return [dict(r) for r in cur.fetchall()], total
    finally:
        con.close()


def get_filters(locale: str = DEFAULT_LOCALE) -> tuple[list[str], list[int]]:
    """Возвращает списки уникальных tier_type_name и item_type для фильтров."""
    con = _connect(locale)
    try:
        cur = con.cursor()
        tiers = [r['tier_type_name'] for r in cur.execute(
            'SELECT DISTINCT tier_type_name FROM items '
            "WHERE tier_type_name IS NOT NULL AND tier_type_name <> '' "
            'ORDER BY tier_type_name')]
        types = [r['item_type'] for r in cur.execute(
            'SELECT DISTINCT item_type FROM items '
            'WHERE item_type IS NOT NULL ORDER BY item_type')]
        return tiers, types
    finally:
        con.close()


def get_items_by_hashes(locale: str, hashes: list) -> dict[int, dict]:
    """Возвращает информацию о предметах по списку itemHash.

    Ключ результата — itemHash (int), значение — словарь предмета
    (name, icon, tier_type_name, item_type_display_name и т.д.).
    """
    hashes = [int(h) for h in hashes if str(h).isdigit()]
    if not hashes:
        return {}
    con = _connect(locale)
    try:
        cur = con.cursor()
        placeholders = ','.join('?' * len(hashes))
        cur.execute(
            'SELECT ' + _SELECT_FIELDS + ' FROM items '
            'WHERE hash IN (' + placeholders + ')',
            hashes,
        )
        return {r['hash']: dict(r) for r in cur.fetchall()}
    finally:
        con.close()


def get_item(locale: str, item_hash: int) -> dict | None:
    """Возвращает информацию об одном предмете (или None)."""
    out = get_items_by_hashes(locale, [item_hash])
    return out.get(int(item_hash))
