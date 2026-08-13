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


# --------------------------------------------------------------------------- #
# Полные определения из манифеста (катализаторы)
# --------------------------------------------------------------------------- #

def get_item_defs(locale: str, hashes) -> dict[int, dict]:
    """Читает полные ``DestinyInventoryItemDefinition`` из манифеста.

    Ключ — itemHash (uint), значение — распарсенный JSON определения.
    В отличие от компактного кэша здесь доступны вложенные поля:
    ``objectives.objectiveHashes`` (цели катализатора) и
    ``sockets.socketEntries[].reusablePlugItems[]`` (плаги сокетов оружия).
    """
    hashes = {int(h) for h in hashes if str(h).isdigit()}
    if not hashes:
        return {}
    source = ensure_manifest(locale)
    con = sqlite3.connect(str(source))
    out: dict[int, dict] = {}
    try:
        con.row_factory = sqlite3.Row
        cur = con.cursor()
        signed = [h if h < 2 ** 31 else h - 2 ** 32 for h in hashes]
        placeholders = ','.join('?' * len(signed))
        cur.execute(
            'SELECT id, json FROM DestinyInventoryItemDefinition '
            'WHERE id IN (' + placeholders + ')', signed)
        for row in cur.fetchall():
            h = _unsigned_id(row['id'])
            try:
                out[h] = json.loads(row['json'])
            except ValueError:
                continue
    finally:
        con.close()
    return out


def get_objective_defs(locale: str, hashes) -> dict[int, dict]:
    """Читает ``DestinyObjectiveDefinition`` из манифеста для набора hash.

    Нужно для текста «задания» катализатора (поле ``progressDescription``).
    """
    hashes = {int(h) for h in hashes if str(h).isdigit()}
    if not hashes:
        return {}
    source = ensure_manifest(locale)
    con = sqlite3.connect(str(source))
    out: dict[int, dict] = {}
    try:
        con.row_factory = sqlite3.Row
        cur = con.cursor()
        signed = [h if h < 2 ** 31 else h - 2 ** 32 for h in hashes]
        placeholders = ','.join('?' * len(signed))
        cur.execute(
            'SELECT id, json FROM DestinyObjectiveDefinition '
            'WHERE id IN (' + placeholders + ')', signed)
        for row in cur.fetchall():
            h = _unsigned_id(row['id'])
            try:
                out[h] = json.loads(row['json'])
            except ValueError:
                continue
    finally:
        con.close()
    return out


def get_plug_set_defs(locale: str, hashes) -> dict[int, dict]:
    """Читает ``DestinyPlugSetDefinition`` из манифеста для набора hash.

    Многие экзотические пушки хранят свои плаги (в т.ч. катализатор) не
    инлайново в ``reusablePlugItems``, а ссылкой на plug set через
    ``socketEntry.reusablePlugSetHash``. Этот хелпер нужен, чтобы достать
    наборы плагов и найти катализатор и там.
    """
    hashes = {int(h) for h in hashes if str(h).isdigit()}
    if not hashes:
        return {}
    source = ensure_manifest(locale)
    con = sqlite3.connect(str(source))
    out: dict[int, dict] = {}
    try:
        con.row_factory = sqlite3.Row
        cur = con.cursor()
        signed = [h if h < 2 ** 31 else h - 2 ** 32 for h in hashes]
        placeholders = ','.join('?' * len(signed))
        cur.execute(
            'SELECT id, json FROM DestinyPlugSetDefinition '
            'WHERE id IN (' + placeholders + ')', signed)
        for row in cur.fetchall():
            h = _unsigned_id(row['id'])
            try:
                out[h] = json.loads(row['json'])
            except ValueError:
                continue
    finally:
        con.close()
    return out


# Общие masterwork-плаги, которые похожи на катализатор по категории, но им не
# являются (есть у любого оружия). Настоящий катализатор — всегда «свой».
# Имена даны в обоих языках (en/ru), т.к. локализованы.
_GENERIC_MASTERWORK_NAMES = {
    # EN
    'Upgrade Masterwork',
    'Masterwork Weapon',
    'Increase Weapon Level',
    'Tier 1 Upgrade', 'Tier 2 Upgrade', 'Tier 3 Upgrade',
    'Tier 4 Upgrade', 'Tier 5 Upgrade',
    'Kill Tracker', 'Crucible Tracker', 'Vanguard Tracker', 'Gambit Tracker',
    'Iron Banner Tracker', 'Empty Catalyst Socket', 'Empty Mod Socket',
    'Default Ornament',
    # RU
    'Улучшить Абсолют',        # Upgrade Masterwork
    'Оружие-Абсолют',          # Masterwork Weapon
    'Броня-Абсолют',           # Armor Masterwork
    'Новый Абсолют',           # New Masterwork
    'Абсолют Горнила',         # Crucible Masterwork
    'Абсолют "Авангарда"',     # Vanguard Masterwork
    'Счетчик убийств',         # Kill Tracker
    'Счетчик убийств в Горниле',  # Crucible Tracker
    'Свободная ячейка для катализатора',  # Empty Catalyst Socket
}


def _catalyst_info(defn: dict) -> dict | None:
    """Извлекает данные катализатора из определения предмета (или None).

    Катализатор — «свой» плаг экзотического оружия. Распознаётся тремя
    способами (по убыванию надёжности, приоритет в ``_priority``):
      2 — имя вида «... Catalyst» / «Катализатор для «...»»;
      1 — plugCategoryIdentifier == 'catalysts' (новые «Refit»-катализаторы);
      0 — категория ``masterwork`` с не-общим именем (например, у Ice Breaker
          катализатор называется просто «Ice Breaker», а у Cull's Shadow —
          «Soulfire Succor»).
    У части катализаторов цели (``objectives.objectiveHashes``) не прописаны —
    тогда цель берётся из API-компонента plugObjectives.
    """
    dp = defn.get('displayProperties') or {}
    name = dp.get('name') or ''
    plug = defn.get('plug')
    if not isinstance(plug, dict):
        return None
    pci = plug.get('plugCategoryIdentifier') or ''

    # Заглушки и трекеры катализатором не считаются.
    if 'empty' in pci.lower() or 'trackers' in pci.lower():
        return None
    if name in _GENERIC_MASTERWORK_NAMES:
        return None

    objectives = ((defn.get('objectives') or {}).get('objectiveHashes') or [])
    info = {
        'hash': int(defn.get('hash')),
        'name': name,
        'icon': dp.get('icon') or '',
        'description': dp.get('description') or '',
        'objective_hashes': [int(h) for h in objectives],
    }

    low = name.lower()
    if 'catalyst' in low or 'катализатор' in low:
        return {**info, '_priority': 2}
    if pci.lower() == 'catalysts':
        return {**info, '_priority': 1}
    if 'masterwork' in pci.lower() and 'generic' not in pci.lower():
        return {**info, '_priority': 0}
    return None


def get_weapon_catalysts(locale: str, weapon_hashes) -> dict[int, dict]:
    """Находит катализаторы для списка хэшей экзотического оружия.

    Катализатор ищем среди всех плагов сокетов оружия: инлайновых
    ``reusablePlugItems`` и наборов ``reusablePlugSetHash`` (plug sets).
    Возвращает катализатор (по имени «... Catalyst») для каждого оружия:

      {weapon_item_hash: {'hash', 'name', 'icon', 'description',
                          'objective_hashes': [...]}}
    """
    weapon_hashes = [int(h) for h in weapon_hashes if str(h).isdigit()]
    if not weapon_hashes:
        return {}

    defs = get_item_defs(locale, weapon_hashes)
    if not defs:
        return {}

    # Хэши plug set'ов, на которые ссылаются сокеты оружия (и reusable, и
    # randomized — у части экзотики катализатор лежит в randomizedPlugSetHash).
    pset_hashes: set[int] = set()
    for defn in defs.values():
        for entry in ((defn.get('sockets') or {}).get('socketEntries') or []):
            for key in ('reusablePlugSetHash', 'randomizedPlugSetHash'):
                ph = entry.get(key)
                if ph is not None:
                    pset_hashes.add(int(ph))
    pset_defs = get_plug_set_defs(locale, pset_hashes)

    # Все плаги каждого оружия: инлайн + из plug set'ов.
    weapon_plug_map: dict[int, set[int]] = {}
    all_plug_hashes: set[int] = set()
    for wh, defn in defs.items():
        plugs: set[int] = set()
        for entry in ((defn.get('sockets') or {}).get('socketEntries') or []):
            for rp in (entry.get('reusablePlugItems') or []):
                ph = rp.get('plugItemHash')
                if ph is not None:
                    plugs.add(int(ph))
            for key in ('reusablePlugSetHash', 'randomizedPlugSetHash'):
                pset = pset_defs.get(entry.get(key))
                for p in ((pset or {}).get('reusablePlugItems') or []):
                    ph = p.get('plugItemHash')
                    if ph is not None:
                        plugs.add(int(ph))
        weapon_plug_map[wh] = plugs
        all_plug_hashes |= plugs

    plug_defs = get_item_defs(locale, all_plug_hashes)

    out: dict[int, dict] = {}
    for wh in defs:
        catalyst = None
        best_priority = -1
        for ph in weapon_plug_map[wh]:
            info = _catalyst_info(plug_defs.get(ph) or {})
            if not info:
                continue
            priority = info.pop('_priority', 0)
            if priority > best_priority:
                catalyst = info
                best_priority = priority
        if catalyst:
            out[wh] = catalyst
    return out


# Кэш карты «имя экзотического оружия → катализатор» для локали.
# Ключ — mtime файла манифеста: карта пересобирается при обновлении манифеста.
_exotic_catalysts_cache: dict[str, dict] = {}
_exotic_catalysts_lock = threading.Lock()


def _build_exotic_catalysts_map(locale: str) -> dict[str, dict]:
    """Сканирует манифест и возвращает {имя_оружия: info_катализатора}.

    Перебирает все экзотические пушки и для каждой ищет катализатор по любому
    из её хэшей (у одного оружия бывает несколько хэшей — легаси-версий, и
    катализатор прописан не у всех). Ключ — имя оружия, т.к. именно оно
    совпадает у коллекции и у экземпляра игрока.

    Экзотика определяется по числовому ``inventory.tierType == 6`` — он не
    локализуется (в отличие от ``tierTypeName``), поэтому работает для en/ru.
    """
    source = ensure_manifest(locale)
    con = sqlite3.connect(str(source))
    exotic: dict[int, str] = {}  # hash -> имя оружия
    try:
        con.row_factory = sqlite3.Row
        cur = con.cursor()
        cur.execute('SELECT id, json FROM DestinyInventoryItemDefinition')
        for r in cur.fetchall():
            try:
                d = json.loads(r['json'])
            except ValueError:
                continue
            if d.get('itemType') != 3:
                continue
            if (d.get('inventory') or {}).get('tierType') != 6:
                continue
            name = (d.get('displayProperties') or {}).get('name') or ''
            if name:
                exotic[_unsigned_id(r['id'])] = name
    finally:
        con.close()
    if not exotic:
        return {}

    cats = get_weapon_catalysts(locale, list(exotic.keys()))
    result: dict[str, dict] = {}
    for h, cat in cats.items():
        name = exotic.get(h)
        if name:
            result.setdefault(name, cat)
    return result


def get_exotic_catalysts_by_name(locale: str = DEFAULT_LOCALE) -> dict[str, dict]:
    """Возвращает {имя_экзотического_оружия: info_катализатора}.

    Результат кэшируется до тех пор, пока файл манифеста не изменится
    (проверяется mtime), аналогично кэшу дерева коллекций.
    """
    path = ensure_manifest(locale)
    try:
        mtime = path.stat().st_mtime
    except OSError:
        mtime = 0
    with _exotic_catalysts_lock:
        entry = _exotic_catalysts_cache.get(locale)
        if entry and entry.get('mtime') == mtime:
            return entry['data']
    data = _build_exotic_catalysts_map(locale)
    with _exotic_catalysts_lock:
        _exotic_catalysts_cache[locale] = {'mtime': mtime, 'data': data}
    return data
