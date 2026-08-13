"""Destiny 2: инвентарь привязанного Bungie-аккаунта."""
from __future__ import annotations

import logging

from flask import jsonify, make_response, redirect, render_template, request

from app.site.auth import current_user, validate_csrf_json
from app.site.bungie import get_user_inventory
from app.site.bungie.api import transfer_item
from app.site.bungie import items as manifest_items
from app.site.lang import get_lang
from app.site.views.blueprint import bp
from app.site.views.destiny import AMMO_TYPE_LABELS, DAMAGE_TYPE_LABELS

logger = logging.getLogger('BotSite')


# Слоты оружия Destiny 2 (по bucketHash предмета из API):
# 1498876634 — Kinetic Weapons, 2465295065 — Energy Weapons,
# 953998645 — Power Weapons. Это надёжный способ отличить Kinetic от Energy,
# т.к. ammoType не помогает (у энергетических SMG/авто-винтовок тоже Primary).
WEAPON_SLOTS = (
    ('primary', 'Primary'),
    ('special', 'Special'),
    ('heavy', 'Heavy'),
)

WEAPON_SLOT_BUCKETS = {
    1498876634: 'primary',  # Kinetic Weapons
    2465295065: 'special',  # Energy Weapons
    953998645: 'heavy',     # Power Weapons
}

# Слоты брони Destiny 2 (по bucketHash предмета из API):
# 3448274439 — Helmet, 3551918588 — Gauntlets, 14239492 — Chest Armor,
# 20886954 — Leg Armor, 1581506037 — Class Armor (плащ/завеса).
ARMOR_SLOTS = (
    ('helmet', 'Шлем'),
    ('arms', 'Наручи'),
    ('chest', 'Броня'),
    ('legs', 'Поножи'),
    ('class_item', 'Классовый предмет'),
)

ARMOR_SLOT_BUCKETS = {
    3448274439: 'helmet',
    3551918588: 'arms',
    14239492: 'chest',
    20886954: 'legs',
    1585787867: 'class_item',
}

# Отображаемые типы брони (item_type_display_name), по которым можно надёжно
# определить слот, даже когда у предмета аномальный item_type (0/19) и/или
# скрытый bucket (например, 2422292810 у брони «ЭОНА»). Проверяются
# подстрокой в нижнем регистре; порядок важен — более конкретные фразы
# («броня для ног») идут раньше общих («броня»).
ARMOR_DISPLAY_KEYWORDS: tuple[tuple[str, str], ...] = (
    # RU — шлем
    ('шлем', 'helmet'),
    ('маска', 'helmet'),
    ('капюшон', 'helmet'),
    # RU — руки
    ('рукавиц', 'arms'),
    ('перчатк', 'arms'),
    ('обмотк', 'arms'),
    ('наруч', 'arms'),
    ('нарукавник', 'arms'),
    # RU — ноги (раньше «броня», чтобы не съесть её)
    ('броня для ног', 'legs'),
    ('поножи', 'legs'),
    ('сапоги', 'legs'),
    ('штаны', 'legs'),
    ('голенища', 'legs'),
    # RU — торс
    ('нагрудник', 'chest'),
    ('жилет', 'chest'),
    ('кираса', 'chest'),
    ('мантия', 'chest'),
    ('броня', 'chest'),
    # RU — классовый предмет
    ('плащ', 'class_item'),
    ('метка', 'class_item'),
    ('повязка', 'class_item'),
    ('классовое снаряжение', 'class_item'),
    # EN
    ('helmet', 'helmet'),
    ('mask', 'helmet'),
    ('hood', 'helmet'),
    ('gauntlet', 'arms'),
    ('gloves', 'arms'),
    ('glove', 'arms'),
    ('grips', 'arms'),
    ('wraps', 'arms'),
    ('brace', 'arms'),
    ('chest armor', 'chest'),
    ('plate', 'chest'),
    ('vest', 'chest'),
    ('robe', 'chest'),
    ('chest', 'chest'),
    ('leg armor', 'legs'),
    ('greaves', 'legs'),
    ('boots', 'legs'),
    ('strides', 'legs'),
    ('pants', 'legs'),
    ('legs', 'legs'),
    ('class item', 'class_item'),
    ('cloak', 'class_item'),
    ('mark', 'class_item'),
    ('bond', 'class_item'),
)

# Типы предметов (DestinyItemType), которые НЕ показываем в сейве: материалы
# и расходники (Finest Matterweave, ядра, осколки и т.п.) лежат в общем
# инвентаре и только засоряют вывод. Оружие (3) и броня (2) идут в слоты,
# остальное ценное (призраки/корабли/эмблемы/моды) — в секцию Почтмейстера.
VAULT_HIDDEN_ITEM_TYPES = {
    1,   # Currency
    6,   # Consumable
    7,   # ExchangeMaterial
    8,   # MissionReward
    9,   # QuestStep
    10,  # QuestStepComplete
    12,  # Quest
    22,  # Package
    23,  # Bounty
    24,  # Wrapper
    25,  # SeasonalArtifact
}

# Локализованные имена типа предмета (item_type_display_name), которые
# соответствуют материалам/валютам/расходникам (Exotic Cipher, Herealways
# Piece, Ascendant Shard и т.п.). У таких предметов item_type может быть 0
# или 20, поэтому надёжнее фильтровать по отображаемому имени типа.
VAULT_HIDDEN_TYPE_NAMES = {
    # EN
    'Currency', 'Material', 'Materials', 'Consumable', 'Consumables',
    # RU
    'Валюта', 'Материал', 'Материалы', 'Расходный материал',
    'Расходные материалы', 'Расходник', 'Расходники',
}

# Почтмейстер (Lost Items) определяется в api.py по bucketHash
# 215593132 и приходит отдельным списком ``postmaster``. Здесь
# константы не нужны — предметы почтмейстера уже вырезаны из ``items``.



def _safe_int(value) -> int:

    """Безопасно приводит значение к int (невалидное → 0)."""
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0

def _weapon_slot(it, row) -> str | None:
    """Определяет слот оружия.

    Основной способ — bucketHash предмета из API (``it['bucket']``):
    он однозначно указывает слот (Kinetic/Energy/Power). Это чинит баг,
    когда энергетическое оружие с Primary-патронами (например, SMG Funnelweb)
    попадало в Kinetic-слот из-за определения по equippingBlock.ammoType.

    Если bucket неизвестен (например, предмет не в слоте) — fallback:
      * heavy ammo (3) — Power;
      * Kinetic damage (1) — Kinetic (Primary);
      * любая стихия (Arc/Solar/Void/Stasis/Strand) — Energy (Special).

    Возвращает ключ слота: 'primary', 'special' или 'heavy'.
    """
    bucket = _safe_int(it.get('bucket'))
    slot = WEAPON_SLOT_BUCKETS.get(bucket)
    if slot:
        return slot

    ammo = _safe_int(row.get('ammo_type'))
    if ammo == 3:
        return 'heavy'
    damage = _safe_int(row.get('default_damage_type'))
    if damage == 1:
        return 'primary'
    if damage != 0:  # Arc/Solar/Void/Raid/Stasis/Strand — Energy-слот
        return 'special'
    if ammo == 2:
        return 'special'
    if ammo == 1:
        return 'primary'
    return None


def _armor_slot(it, row) -> str | None:
    """Определяет слот брони по bucketHash предмета из API.

    Возвращает ключ слота брони ('helmet'/'arms'/'chest'/'legs'/'class_item')
    или None, если bucket неизвестен (не броня).
    """
    bucket = _safe_int(it.get('bucket'))
    return ARMOR_SLOT_BUCKETS.get(bucket)


def _vault_slot(it, row, item_type: int) -> str | None:
    """Определяет слот предмета сейва (оружие/броня) или None.

    Источники по убыванию надёжности:
    1) bucketHash из API — точный слот оружия/брони;
    2) оружие по патронам/стихии (_weapon_slot) — работает даже при
       аномальном item_type=0;
    3) отображаемый тип брони (item_type_display_name) — надёжно при
       item_type=0/19 и скрытом bucket (например, 2422292810 у «ЭОНА»),
       когда предмет в манифесте числится броней, но слот по bucket
       не определяется.

    Возвращает ключ слота ('primary'/'special'/'heavy'/'helmet'/...
    /'class_item') или None (не оружие и не броня).
    """
    bucket = _safe_int(it.get('bucket'))

    slot = WEAPON_SLOT_BUCKETS.get(bucket)
    if slot:
        return slot

    slot = ARMOR_SLOT_BUCKETS.get(bucket)
    if slot:
        return slot

    if item_type in (0, 3):  # оружие (в т.ч. с аномальным item_type=0)
        slot = _weapon_slot(it, row)
        if slot:
            return slot

    if item_type in (0, 2):  # броня (в т.ч. с аномальным item_type=0/19)
        disp = (row.get('item_type_display_name') or '').lower()
        for keyword, armor_slot in ARMOR_DISPLAY_KEYWORDS:
            if keyword in disp:
                return armor_slot

    return None


def _inventory_weapon(row, it, uid: int) -> dict:

    """Собирает словарь оружия с подписями Ammo/Element (как в /destiny)."""
    item_hash = it.get('itemHash')
    weapon = {
        'uid': uid,
        'hash': int(item_hash),
        'name': row.get('name') or f'#{item_hash}',
        'icon': row.get('icon') or '',
        'tier': row.get('tier_type_name') or '',
        'type': row.get('item_type_display_name') or '',
        'quantity': _safe_int(it.get('quantity')) or 1,
        'instance': it.get('itemInstanceId') or '',
        'equipped': bool(it.get('equipped')),
        # Сила (Power/Light) предмета — из primaryStat.value (0, если нет).
        'power': _safe_int(it.get('power')),
    }
    ammo = _safe_int(row.get('ammo_type'))
    weapon['ammo'] = ammo
    weapon['ammo_label'] = AMMO_TYPE_LABELS.get(ammo, '—')
    damage = _safe_int(row.get('default_damage_type'))
    weapon['element'] = damage
    weapon['element_label'] = DAMAGE_TYPE_LABELS.get(damage, '—')
    return weapon


@bp.route('/inventory')
def inventory():
    """Страница с инвентарём Destiny 2 привязанного Bungie-аккаунта.

    Персонажи (обычно три) выводятся в одну строку в том порядке, в котором
    их вернуло API Bungie. У каждого персонажа оружие сгруппировано по слотам
    Primary / Special / Heavy. Внутри слота экипированное оружие выводится
    отдельной колонкой слева, а остальное — сеткой по 3 в ряд.

    Высота слотов выравнивается по всем персонажам: для каждого слота
    (Primary / Special / Heavy) берётся максимальное число предметов среди
    персонажей, и меньшие слоты добиваются пустыми плитками-заглушками,
    чтобы карточки персонажей выглядели одинаково.
    """

    user = current_user()
    if user is None:
        return redirect('/')

    try:
        result = get_user_inventory(user)
        if not result.get('ok'):
            return render_template(
                'inventory.html',
                error=result.get('error', 'Не удалось получить инвентарь'),
                meta={},
            )

        items = result['items']
        # Предметы почтмейстера приходят отдельным списком из API —
        # они уже не входят в ``items``, поэтому гарантированно не
        # отображаются в слотах оружия.
        postmaster_items = result.get('postmaster') or []
        # Предметы сейфа (Vault) — приходят отдельным списком из API
        # (компонент profileInventory/102), у них character_id=None.
        vault_items = result.get('vault') or []
        characters_raw = result.get('characters') or {}
        # Запрашиваем в БД инфу и по обычным предметам, и по почтмейстеру,
        # и по сейфу (у всех должны быть иконки/имена).
        hashes = [it.get('itemHash') for it in items]
        hashes += [it.get('itemHash') for it in postmaster_items]
        hashes += [it.get('itemHash') for it in vault_items]
        # Имена/иконки берём из манифеста (в локали выбранного языка).
        info = manifest_items.get_items_by_hashes(get_lang(), hashes)



        # Названия классов Destiny 2 (числовой classType из API).
        class_labels = {
            0: 'Титан',
            1: 'Охотник',
            2: 'Варлок',
        }

        # Персонажи выводятся в том порядке, в котором их вернуло API Bungie
        # (без сортировки по классу/свету).
        characters_ordered = list(characters_raw.items())

        classes: list[dict] = []
        uid = 0

        for character_id, cdata in characters_ordered:

            cdata = cdata or {}
            class_type = _safe_int(cdata.get('class_type'))
            label = class_labels.get(class_type, f'Класс {class_type}')

            # Оружие персонажа, сгруппированное по слотам:
            #   'primary' -> {'label': ..., 'equipped': [...], 'other': [...]}
            slots: dict[str, dict] = {key: {
                'key': key,
                'label': label_i,
                'equipped': [],
                'other': [],
            } for key, label_i in WEAPON_SLOTS}

            # Броня персонажа, сгруппированная по слотам:
            #   'helmet' -> {'label': ..., 'equipped': [...], 'other': [...]}
            armor_slots: dict[str, dict] = {key: {
                'key': key,
                'label': label_i,
                'equipped': [],
                'other': [],
            } for key, label_i in ARMOR_SLOTS}


            # Предметы почтмейстера (Lost Items / Special Deliveries):
            # приходят отдельным списком от API. Выводим их секцией над
            # слотами оружия, в слоты не включаем (даже если там лежит
            # оружие).
            postmaster: list[dict] = []

            for it in postmaster_items:
                if str(it.get('character_id') or '') != character_id:
                    continue
                item_hash = it.get('itemHash')
                row = info.get(item_hash, {})
                item = _inventory_weapon(row, it, uid)
                item['slot'] = 'postmaster'
                postmaster.append(item)
                uid += 1

            for it in items:
                if str(it.get('character_id') or '') != character_id:
                    continue
                item_hash = it.get('itemHash')
                row = info.get(item_hash, {})

                if _safe_int(row.get('item_type')) != 3:

                    continue  # оставляем только оружие

                slot_key = _weapon_slot(it, row)
                if slot_key is None:
                    continue  # не удалось определить слот — пропускаем

                weapon = _inventory_weapon(row, it, uid)
                weapon['slot'] = slot_key
                weapon['slot_label'] = slots[slot_key]['label']
                uid += 1

                if weapon['equipped']:
                    slots[slot_key]['equipped'].append(weapon)
                else:
                    # Защита от дублей: если этот экземпляр уже показан как
                    # экипированный (иногда Bungie возвращает предмет и в
                    # инвентаре, и в экипировке) — в неэкипированные не дублируем.
                    equipped_instances = {
                        w['instance'] for w in slots[slot_key]['equipped']
                        if w['instance']
                    }
                    if weapon['instance'] and weapon['instance'] in equipped_instances:
                        continue
                    slots[slot_key]['other'].append(weapon)

            # Второй проход по предметам — собираем броню (item_type == 2).
            # Для брони тоже определяем слот по bucketHash и распределяем
            # на экипированную/неэкипированную.
            for it in items:
                if str(it.get('character_id') or '') != character_id:
                    continue
                item_hash = it.get('itemHash')
                row = info.get(item_hash, {})
                if _safe_int(row.get('item_type')) != 2:
                    continue  # оставляем только броню
                armor_slot_key = _armor_slot(it, row)
                if armor_slot_key is None:
                    continue  # bucket не слот брони — пропускаем
                armor = _inventory_weapon(row, it, uid)
                armor['slot'] = armor_slot_key
                armor['slot_label'] = armor_slots[armor_slot_key]['label']
                uid += 1
                if armor['equipped']:
                    armor_slots[armor_slot_key]['equipped'].append(armor)
                else:
                    equipped_instances = {
                        w['instance'] for w in armor_slots[armor_slot_key]['equipped']
                        if w['instance']
                    }
                    if armor['instance'] and armor['instance'] in equipped_instances:
                        continue
                    armor_slots[armor_slot_key]['other'].append(armor)

            # Слоты всегда выводятся в порядке Primary / Special / Heavy
            # (даже пустые — чтобы колонки у персонажей совпадали).
            weapon_slots = [slots[k] for k, _ in WEAPON_SLOTS]
            armor_slot_list = [armor_slots[k] for k, _ in ARMOR_SLOTS]

            classes.append({
                'character_id': str(character_id),
                'label': label,
                'light': cdata.get('light') or '',
                'emblem': cdata.get('emblem_path') or '',
                'slots': weapon_slots,
                'armor_slots': armor_slot_list,
                'postmaster': postmaster,
            })



        # Секции выводятся ЕДИНОЙ сеткой: каждый ряд — одна секция
        # (Почтмейстер/Разное, Primary, Special, Heavy, Шлем, Наручи, Броня,
        # Поножи, Классовый предмет) для всех четырёх колонок сразу
        # (3 персонажа + хранилище). Благодаря этому заголовки секций всегда
        # на одной высоте без исключений — высоту ряда задаёт самая высокая
        # ячейка, предметы нигде не скрываются и не обрезаются.

        # --- Хранилище (Vault): справа от персонажей ---
        # Предметы сейва (account-wide, character_id=None) раскладываем по
        # слотам оружия (Primary/Special/Heavy) и брони. У сейва нет
        # экипировки — только "обычные" предметы. Всё, что не легло ни в
        # один слот (призраки, корабли, жетоны, расходники, моды и т.п.),
        # показываем отдельной секцией «Разное».
        vault_slots: dict[str, dict] = {key: {
            'key': key,
            'label': label_i,
            'items': [],
        } for key, label_i in WEAPON_SLOTS}
        vault_armor_slots: dict[str, dict] = {key: {
            'key': key,
            'label': label_i,
            'items': [],
        } for key, label_i in ARMOR_SLOTS}

        # Предметы сейва, не попавшие ни в один слот (уходят в Почтмейстер).
        vault_other: list[dict] = []

        for it in vault_items:
            item_hash = it.get('itemHash')
            row = info.get(item_hash, {})
            item = _inventory_weapon(row, it, uid)
            uid += 1
            item_type = _safe_int(row.get('item_type'))

            # Слот предмета сейва определяем по трём источникам сразу
            # (bucketHash → патроны/стихия → отображаемый тип брони),
            # см. _vault_slot. Это чинит броню с аномальным item_type
            # (0/19) и/или скрытым bucket (2422292810 у «ЭОНА»), которая
            # раньше ошибочно падала в «Разное».
            slot_key = _vault_slot(it, row, item_type)

            if slot_key in WEAPON_SLOT_BUCKETS.values():
                item['slot'] = slot_key
                item['slot_label'] = vault_slots[slot_key]['label']
                vault_slots[slot_key]['items'].append(item)
                continue

            if slot_key in ARMOR_SLOT_BUCKETS.values():
                item['slot'] = slot_key
                item['slot_label'] = vault_armor_slots[slot_key]['label']
                vault_armor_slots[slot_key]['items'].append(item)
                continue

            # Материалы/расходники/квесты (Finest Matterweave, Exotic Cipher,
            # Herealways Piece и т.п.) лежат в общем инвентаре — в сейве их
            # не показываем.
            if item_type in VAULT_HIDDEN_ITEM_TYPES:
                continue
            type_name = (row.get('item_type_display_name') or '').strip()
            if type_name in VAULT_HIDDEN_TYPE_NAMES:
                continue

            # Не подошло ни к одному слоту — выводим секцией «Разное».
            item['slot'] = 'other'
            item['slot_label'] = 'Разное'
            vault_other.append(item)

        # --- Единая рядовая сетка секций ---
        # Каждый ряд сетки — одна секция для всех четырёх колонок
        # (3 персонажа + хранилище), чтобы заголовки всегда были на одной
        # высоте без исключений. В «Разное» хранилища попадают только
        # предметы сейва, не легшие в слоты; предметы почтмейстера
        # персонажей сюда НЕ дублируются (у персонажей свой «Почтмейстер»).
        grid_rows: list[dict] = []

        def _cell(label: str, *, equipped=None, other=None, postmaster=False,
                  source: str = 'vault'):
            eq = list(equipped or [])
            items = list(other or [])
            return {
                'label': label,
                'equipped': eq,
                'items': items,
                'has_equipped_col': equipped is not None,
                'postmaster': postmaster,
                'source': source,
                'total': len(eq) + len(items),
            }

        # Ряд «📬 Почтмейстер» (персонажи) / «Разное» (хранилище).
        pm_cells = [
            _cell('📬 Почтмейстер', other=cls['postmaster'], postmaster=True,
                  source=cls['character_id'])
            for cls in classes
        ]
        pm_cells.append(_cell('Разное', other=vault_other))
        grid_rows.append({'key': 'postmaster', 'cells': pm_cells})

        # Ряды оружия: Primary / Special / Heavy.
        for key, label in WEAPON_SLOTS:
            cells = []
            for cls in classes:
                slot = next(s for s in cls['slots'] if s['key'] == key)
                cells.append(_cell(label, equipped=slot['equipped'],
                                   other=slot['other'],
                                   source=cls['character_id']))
            cells.append(_cell(label, other=vault_slots[key]['items']))
            grid_rows.append({'key': key, 'cells': cells})

        # Ряды брони: Шлем / Наручи / Броня / Поножи / Классовый предмет.
        for key, label in ARMOR_SLOTS:
            cells = []
            for cls in classes:
                slot = next(s for s in cls['armor_slots'] if s['key'] == key)
                cells.append(_cell(label, equipped=slot['equipped'],
                                   other=slot['other'],
                                   source=cls['character_id']))
            cells.append(_cell(label, other=vault_armor_slots[key]['items']))
            grid_rows.append({'key': key, 'cells': cells})

        # Итоговый счётчик — все предметы сейва (материалы/расходники
        # отфильтрованы).
        vault_display_total = (
            sum(len(slot['items']) for slot in vault_slots.values())
            + sum(len(slot['items']) for slot in vault_armor_slots.values())
            + len(vault_other)
        )

        vault = {
            'total': vault_display_total,
        }



        weapons_count = sum(
            len(slot['equipped']) + len(slot['other'])
            for cls in classes for slot in cls['slots']
        )
        armor_count = sum(
            len(slot['equipped']) + len(slot['other'])
            for cls in classes for slot in cls['armor_slots']
        )


        meta = {
            'bungie_name': user.get('bungie_name') or '',
            'weapons': weapons_count,
            'armor': armor_count,
            'characters': len(classes),
            'vault': vault['total'],
        }

        # После перемещения предметов страница всегда должна перезагружаться
        # со свежими данными — запрещаем кэширование HTML.
        resp = make_response(render_template(
            'inventory.html',
            error=None,
            classes=classes,
            vault=vault,
            grid_rows=grid_rows,
            meta=meta,
        ))
        resp.headers['Cache-Control'] = 'no-store'
        return resp

    except Exception as exc:
        # Любая внутренняя ошибка не должна превращаться в 500:
        # показываем понятное сообщение и логируем причину для диагностики.
        logger.exception('Ошибка при получении инвентаря: %s', exc)
        return render_template(
            'inventory.html',
            error='Не удалось получить инвентарь. Попробуйте ещё раз '
                  'или сообщите администратору.',
            meta={},
        )


@bp.route('/inventory/transfer', methods=['POST'])
def inventory_transfer():
    """Перемещает предмет (drag & drop) через Bungie TransferItem.

    Тело JSON: ``hash`` (itemReferenceHash), ``instance`` (itemInstanceId),
    ``target`` — 'vault' или character_id получателя.
    """
    user = current_user()
    if user is None:
        return jsonify({'ok': False, 'error': 'Не авторизован'}), 401
    if not validate_csrf_json():
        return jsonify({'ok': False, 'error': 'Неверный CSRF-токен'}), 400

    payload = request.get_json(silent=True) or {}
    try:
        item_hash = int(payload.get('hash'))
    except (TypeError, ValueError):
        return jsonify({'ok': False, 'error': 'Некорректный hash предмета'}), 400
    instance_id = str(payload.get('instance') or '')
    target = str(payload.get('target') or '').strip()
    source = str(payload.get('source') or '').strip()
    if not target or target not in ('vault',) and not target.isdigit():
        return jsonify({'ok': False, 'error': 'Некорректная цель перемещения'}), 400
    if not source or source not in ('vault',) and not source.isdigit():
        return jsonify({'ok': False, 'error': 'Некорректный источник предмета'}), 400

    ok, err = transfer_item(user, item_hash, instance_id, target, source)
    if not ok:
        return jsonify({'ok': False, 'error': err}), 400
    return jsonify({'ok': True})
