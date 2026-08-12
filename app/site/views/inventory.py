"""Destiny 2: инвентарь привязанного Bungie-аккаунта."""
from __future__ import annotations

import logging

from flask import redirect, render_template

from app.site.auth import current_user
from app.site.bungie import get_user_inventory
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
        characters_raw = result.get('characters') or {}
        # Запрашиваем в БД инфу и по обычным предметам, и по почтмейстеру
        # (у Lost Items тоже должны быть иконки/имена).
        hashes = [it.get('itemHash') for it in items]
        hashes += [it.get('itemHash') for it in postmaster_items]
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
                'label': label,
                'light': cdata.get('light') or '',
                'emblem': cdata.get('emblem_path') or '',
                'slots': weapon_slots,
                'armor_slots': armor_slot_list,
                'postmaster': postmaster,
            })



        # Выравниваем высоту слотов по всем персонажам. Высота слота
        # складывается из левой колонки (экипированные, 1 в столбик)
        # и правой сетки (неэкипированные, по 3 в ряд), поэтому максимумы
        # считаем раздельно для каждой колонки и добиваем заглушками.
        slot_max_equipped: dict[str, int] = {}
        slot_max_other: dict[str, int] = {}
        for cls in classes:
            for slot in cls['slots']:
                key = slot['key']
                n_eq = len(slot['equipped'])
                n_other = len(slot['other'])
                slot_max_equipped[key] = max(
                    slot_max_equipped.get(key, 0), n_eq)
                slot_max_other[key] = max(slot_max_other.get(key, 0), n_other)

        for cls in classes:
            for slot in cls['slots']:
                key = slot['key']
                slot['equip_placeholders'] = max(
                    0, slot_max_equipped[key] - len(slot['equipped']))
                slot['other_placeholders'] = max(
                    0, slot_max_other[key] - len(slot['other']))

        # Почтмейстер тоже выравниваем по всем персонажам: берём максимум
        # предметов среди персонажей и добиваем пустыми плитками, чтобы
        # секция у всех была одинаковой высоты.
        postmaster_max = 0
        for cls in classes:
            postmaster_max = max(postmaster_max, len(cls['postmaster']))

        for cls in classes:
            cls['postmaster_max'] = postmaster_max
            cls['postmaster_placeholders'] = max(
                0, postmaster_max - len(cls['postmaster']))

        # Выравниваем высоту слотов брони по всем персонажам точно так же,
        # как и слоты оружия: максимумы экипированных/неэкипированных
        # раздельно, потом добиваем заглушками.
        armor_max_equipped: dict[str, int] = {}
        armor_max_other: dict[str, int] = {}
        for cls in classes:
            for slot in cls['armor_slots']:
                key = slot['key']
                armor_max_equipped[key] = max(
                    armor_max_equipped.get(key, 0), len(slot['equipped']))
                armor_max_other[key] = max(
                    armor_max_other.get(key, 0), len(slot['other']))

        for cls in classes:
            for slot in cls['armor_slots']:
                key = slot['key']
                slot['equip_placeholders'] = max(
                    0, armor_max_equipped[key] - len(slot['equipped']))
                slot['other_placeholders'] = max(
                    0, armor_max_other[key] - len(slot['other']))



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
        }

        return render_template(
            'inventory.html',
            error=None,
            classes=classes,
            meta=meta,
        )

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
