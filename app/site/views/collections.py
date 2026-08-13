"""Destiny 2: страница «Коллекция».

Показывает коллекции привязанного Bungie-аккаунта в виде дерева
категорий (Exotic / Weapons / Armor / Resources / Equipment / Flair),
аналогично вкладке Collection в игре.

Источники данных:
  * Destiny 2 Manifest (локально, в resources/) — дерево категорий,
    иконки и itemHash предметов (DestinyPresentationNodeDefinition +
    DestinyCollectibleDefinition);
  * Bungie API, components=800 — какие коллекции игрок уже собрал.
"""
from __future__ import annotations

import json
import logging

import flask
from flask import redirect, render_template

from app.site.auth import current_user
from app.site.bungie import items as manifest_items
from app.site.bungie.api import get_user_inventory
from app.site.bungie.manifest import (
    ManifestError,
    build_collections_view,
    load_tree,
)
from app.site.lang import get_lang
from app.site.views.blueprint import bp

logger = logging.getLogger('BotSite')


def _apply_states(categories: list[dict], states: dict[int, int]) -> dict:
    """Проставляет каждому предмету флаг ``obtained`` и считает статистику.

    ``states`` — словарь collectibleHash -> 1 (собрано) / 0 (не собрано).
    На каждый уровень дерева (категория, подгруппа и т.д. любой глубины)
    записывает ``obtained``/``total``. Возвращает ``{'categories': ...,
    'total': int, 'obtained': int}``.
    """

    def _walk(items: list[dict]) -> None:
        """Помечает предметы флагом ``obtained``."""
        for item in items:
            item['obtained'] = bool(states.get(int(item['hash'])) or 0)

    def _walk_node(node: dict) -> None:
        _walk(node.get('items') or [])
        for subgroup in node.get('subgroups') or []:
            _walk_node(subgroup)

    for category in categories:
        _walk_node(category)

    return _recount(categories)


def _recount(categories: list[dict]) -> dict:
    """Пересчитывает ``total``/``obtained`` на каждом уровне дерева.

    Возвращает ``{'categories': ..., 'total': int, 'obtained': int}``.
    """
    def _walk(items: list[dict]) -> tuple[int, int]:
        total = 0
        obtained = 0
        for item in items:
            total += 1
            if item.get('obtained'):
                obtained += 1
        return total, obtained

    def _walk_node(node: dict) -> tuple[int, int]:
        node_total = 0
        node_obtained = 0
        # У схлопнутых узлов предметы лежат в группах-сетах.
        if node.get('groups'):
            for group in node['groups']:
                g_total, g_obtained = _walk(group['items'])
                node_total += g_total
                node_obtained += g_obtained
        else:
            t, o = _walk(node.get('items') or [])
            node_total += t
            node_obtained += o
        for subgroup in node.get('subgroups') or []:
            sub_total, sub_obtained = _walk_node(subgroup)
            node_total += sub_total
            node_obtained += sub_obtained
        node['total'] = node_total
        node['obtained'] = node_obtained
        return node_total, node_obtained

    for category in categories:
        _walk_node(category)

    total = sum(c.get('total', 0) for c in categories)
    obtained = sum(c.get('obtained', 0) for c in categories)
    return {
        'categories': categories,
        'total': total,
        'obtained': obtained,
    }


def _dedupe_items_by_name(categories: list[dict]) -> None:
    """Убирает дубликаты предметов по имени внутри одной категории.

    Если в категории (в любых её подгруппах) встречается несколько
    предметов с одинаковым именем — например, одна и та же пушка
    (Outbreak Perfected и т.п.) в разных разделах — оставляет только один:
    с приоритетом «уже собран» (obtained=True) над «ещё нет». Пустые
    подгруппы, оставшиеся без предметов, вырезаются из дерева.
    """
    for category in categories:
        # Лучший (для показа) предмет для каждого имени во всей категории.
        best_by_name: dict[str, dict] = {}

        def _collect(node: dict) -> None:
            for item in node.get('items') or []:
                name = item.get('name') or ''
                if not name:
                    continue
                prev = best_by_name.get(name)
                if prev is None:
                    best_by_name[name] = item
                elif item.get('obtained') and not prev.get('obtained'):
                    best_by_name[name] = item
            for subgroup in node.get('subgroups') or []:
                _collect(subgroup)

        def _filter(node: dict) -> bool:
            """Возвращает True, если узел остался непустым."""
            node['items'] = [
                item for item in (node.get('items') or [])
                if not (item.get('name') or '') or item is best_by_name[item['name']]
            ]
            node['subgroups'] = [
                sub for sub in (node.get('subgroups') or [])
                if _filter(sub)
            ]
            return bool(node['items']) or bool(node['subgroups'])

        _collect(category)
        _filter(category)


def _flatten_leaf_groups(categories: list[dict]) -> None:
    """Схлопывает листовые подгруппы-«сеты» в группы предметов родителя.

    Если у узла все подгруппы — листовые «сеты» (содержат только предметы
    и не имеют вложенных подгрупп), они не отображаются отдельными
    сворачиваемыми пунктами. Вместо этого у узла появляется ``groups`` —
    список ``{'name': название сета, 'items': [...]}``: предметы каждого
    сета показываются сгруппированными (со своим названием) в одной
    секции узла. Так, armor → titan → pve остаётся без подпунктов-сетов.

    «Каскад» схлопывания наверх не возникает: узлы, которые изначально
    были разделами (имели подгруппы), не схлопываются сами в родителей,
    даже если после обработки стали листами.
    """

    def _mark(node: dict) -> None:
        """Запоминает, был ли узел разделом (имел подгруппы) изначально."""
        node['_had_groups'] = bool(node.get('subgroups'))
        for sub in node.get('subgroups') or []:
            _mark(sub)

    def _flatten(node: dict) -> None:
        for sub in node.get('subgroups') or []:
            _flatten(sub)
        subgroups = node.get('subgroups') or []
        # Схлопываем только листовые «сеты»: те, что изначально не имели
        # своих подгрупп (не появились в результате схлопывания выше).
        if subgroups and all(not sub.get('_had_groups') for sub in subgroups):
            groups: list[dict] = []
            # Собственные предметы узла — группа без названия.
            if node.get('items'):
                groups.append({'name': '', 'items': list(node['items'])})
            # Каждый листовой «сет» — отдельная группа со своим названием.
            for sub in subgroups:
                if sub.get('items'):
                    groups.append({
                        'name': sub.get('name') or '',
                        'items': sub['items'],
                    })
            node['groups'] = groups
            node['items'] = []
            node['subgroups'] = []

    def _clean(node: dict) -> None:
        node.pop('_had_groups', None)
        for sub in node.get('subgroups') or []:
            _clean(sub)

    for category in categories:
        _mark(category)
        _flatten(category)
        _clean(category)




def _inventory_result(user) -> dict:
    """Получает инвентарь/коллекции игрока через Bungie API (один запрос)."""
    result = get_user_inventory(user)
    if not result.get('ok'):
        # Коллекции не получим без токена/привязки — вернём пустой статус
        # (все предметы будут «не собраны»), но саму страницу покажем.
        logger.warning('Не удалось получить статусы коллекций: %s',
                       result.get('error'))
        return {'ok': False}
    return result


def _build_catalysts(result: dict, locale: str) -> dict:
    """Собирает катализаторы экзотического оружия игрока.

    Из инвентаря (``result``) берём экземпляры оружия в слотах, по манифесту
    определяем их катализаторы и сопоставляем с прогрессом целей (компонент
    301, ``item_objectives``), установленными плагами (компонент 305,
    ``item_socket_plugs``) и связками плаг→цель (компонент 309,
    ``item_plug_objectives``) каждого экземпляра.

    Возвращает {weapon_item_hash: {...}}:
      hash/name/icon/description — данные катализатора;
      status — 'missing' (не получен) | 'progress' (идёт) | 'complete';
      quests — список заданий {'text', 'progress', 'completion_value',
      'complete'} (пустой, если катализатор ещё не получен).
    """
    if not result.get('ok'):
        return {}

    items = result.get('items') or []
    vault_items = result.get('vault') or []
    item_objectives = result.get('item_objectives') or {}
    item_socket_plugs = result.get('item_socket_plugs') or {}
    item_plug_objectives = result.get('item_plug_objectives') or {}

    # Только оружие (слоты Kinetic/Energy/Power). Берём и то, что игрок
    # носит/в инвентаре, и то, что лежит в сейфе (там — почти вся экзотика).
    # Внимание: у предметов из сейва bucketHash указывает на сам сейв
    # (138197802), а не на слот оружия, поэтому слоты сейва не определяем —
    # оружие отфильтровываем ниже по item_type из манифеста. Ключи приходят
    # из Bungie API в camelCase (itemHash).
    weapon_entries = [
        it for it in (items + vault_items) if it.get('itemHash')
    ]
    if not weapon_entries:
        return {}

    weapon_hashes = {int(it['itemHash']) for it in weapon_entries}
    # Имя и тип берём из манифеста (в локали выбранного языка).
    info = manifest_items.get_items_by_hashes(locale, list(weapon_hashes))
    # Оставляем только оружие (itemType 3 = Weapon).
    weapon_entries = [
        it for it in weapon_entries
        if (info.get(int(it['itemHash'])) or {}).get('item_type') == 3
    ]
    if not weapon_entries:
        return {}
    hash_name = {
        h: (info.get(h) or {}).get('name')
        for h in weapon_hashes if (info.get(h) or {}).get('name')
    }
    if not hash_name:
        return {}

    # Катализаторы всей экзотики по имени оружия. Ключ — имя, а не хэш:
    # у одного оружия бывает несколько хэшей (легаси-версии), и у коллекции
    # и у экземпляра игрока они могут отличаться, а имя совпадает. Не-экзотика
    # отсеивается сама: её имён в карте катализаторов нет.
    cats_by_name = manifest_items.get_exotic_catalysts_by_name(locale)

    # Экземпляры игрока, сгруппированные по имени оружия.
    instances_by_name: dict[str, list[dict]] = {}
    for it in weapon_entries:
        name = hash_name.get(int(it['itemHash']))
        if not name or name not in cats_by_name:
            continue
        instances_by_name.setdefault(name, []).append(it)
    if not instances_by_name:
        return {}

    # Тексты «заданий» катализаторов (progressDescription целей). Собираем
    # хэши целей из трёх источников: сами катализаторы (манифест), связки
    # плаг→цель (компонент 309) и все цели экземпляров (fallback для
    # катализаторов, у которых цели в манифесте не прописаны).
    cat_hashes = {cat['hash'] for cat in cats_by_name.values()}
    obj_hashes = set()
    for cat in cats_by_name.values():
        obj_hashes.update(cat.get('objective_hashes') or [])
    for entries in item_plug_objectives.values():
        for entry in entries:
            if entry.get('plug_hash') in cat_hashes:
                obj_hashes.add(entry.get('objective_hash'))
    for objectives in item_objectives.values():
        obj_hashes.update(objectives.keys())
    obj_defs = manifest_items.get_objective_defs(locale, list(obj_hashes))

    out: dict = {}
    for name, instances in instances_by_name.items():
        cat = cats_by_name[name]

        best = None  # экземпляр с наибольшим «сигналом» о катализаторе
        for it in instances:
            inst_id = str(it.get('itemInstanceId') or '')
            plugs = item_socket_plugs.get(inst_id) or []
            objectives = item_objectives.get(inst_id) or {}
            plug_objectives = item_plug_objectives.get(inst_id) or []

            # Цели катализатора: сначала по связке плаг→цель (компонент 309),
            # затем — цели самого катализатора из манифеста, затем — все цели
            # экземпляра (у экзотики это и есть цель катализатора).
            cat_obj_hashes = [
                e.get('objective_hash') for e in plug_objectives
                if e.get('plug_hash') == cat['hash']
            ]
            if not cat_obj_hashes:
                cat_obj_hashes = list(cat.get('objective_hashes') or [])
            if not cat_obj_hashes:
                cat_obj_hashes = list(objectives.keys())

            quests = []
            for oh in cat_obj_hashes:
                od = objectives.get(oh)
                if od is None:
                    continue
                quests.append({
                    'text': (obj_defs.get(oh) or {}).get(
                        'progressDescription') or '',
                    'progress': od.get('progress') or 0,
                    'completion_value': od.get('completion_value') or 0,
                    'complete': bool(od.get('complete')),
                })

            socketed = cat['hash'] in plugs
            score = (100 if quests else 0)
            score += (10 if socketed else 0)
            score += (1 if it.get('equipped') else 0)
            if best is None or score > best['score']:
                best = {'quests': quests, 'socketed': socketed,
                        'score': score}

        if best is None:
            best = {'quests': [], 'socketed': False, 'score': 0}

        quests = best['quests']
        socketed = best['socketed']
        complete = bool(quests and all(q['complete'] for q in quests))
        in_progress = bool(quests and any(not q['complete'] for q in quests))

        if in_progress:
            status = 'progress'
        elif complete or socketed:
            status = 'complete'
        else:
            status = 'missing'

        # Прогресс катализатора для полоски на плитке: берём «главную» цель
        # (с наибольшим значением завершения) — у катализатора это обычно
        # убийства/носители, а шаги «улучшить» идут в дополнение.
        progress_pct = 100 if status == 'complete' else 0
        progress_text = 'Катализатор освоен' if status == 'complete' else (
            'Катализатор не получен' if status == 'missing' else '')
        main = None
        for q in quests:
            cv = q.get('completion_value') or 0
            if not cv:
                continue
            if main is None or cv > (main.get('completion_value') or 0):
                main = q
        if main:
            p = main.get('progress') or 0
            cv = main.get('completion_value') or 1
            progress_pct = max(0, min(100, round(p * 100 / cv)))
            progress_text = f'{p} / {cv}'

        out[name] = {
            'hash': cat['hash'],
            'name': cat['name'],
            'icon': cat['icon'],
            'description': cat['description'],
            'status': status,
            'quests': quests,
            'progress_pct': progress_pct,
            'progress_text': progress_text,
        }
    return out


@bp.route('/destiny/collections')
def destiny_collections():
    """Страница с коллекциями Destiny 2 привязанного аккаунта."""
    user = current_user()
    if user is None:
        return redirect('/')

    # Локальный манифест: если его нет — страница не падает, а показывает
    # понятную ошибку (манифест подтянется при следующем заходе).
    try:
        # Язык интерфейса определяет локаль манифеста (en/ru): названия
        # предметов и разделов будут на выбранном языке.
        tree = load_tree(get_lang())
        categories_raw = build_collections_view(tree)

    except ManifestError as exc:
        logger.warning('Манифест коллекций недоступен: %s', exc)
        return render_template(
            'destiny_collections.html',
            error='Коллекции временно недоступны: не удалось загрузить '
                  'манифест Destiny 2. Попробуйте обновить страницу позже.',
            meta={},
            categories=[],
            total=0,
            obtained=0,
            catalysts={},
            catalysts_json='{}',
        )
    except Exception as exc:
        logger.exception('Ошибка построения дерева коллекций: %s', exc)
        return render_template(
            'destiny_collections.html',
            error='Коллекции временно недоступны. Попробуйте позже.',
            meta={},
            categories=[],
            total=0,
            obtained=0,
            catalysts={},
            catalysts_json='{}',
        )

    result = _inventory_result(user)
    states = result.get('collectible_states') or {}
    data = _apply_states(categories_raw, states)
    # Если одно и то же название встречается в категории несколько раз,
    # оставляем один предмет (с приоритетом «уже собран»).
    _dedupe_items_by_name(data['categories'])
    # Листовые подгруппы-«сеты» (armor → titan → pve) схлопываем в одну
    # сетку родителя, чтобы они не отображались отдельными подпунктами.
    _flatten_leaf_groups(data['categories'])
    # Пересчитываем счётчики на всех уровнях дерева.
    data = _recount(data['categories'])

    # Катализаторы экзотического оружия игрока (для карточки при клике).
    catalysts = _build_catalysts(result, get_lang())
    catalysts_json = json.dumps(
        {str(k): v for k, v in catalysts.items()}, ensure_ascii=False)

    meta = {
        'bungie_name': user.get('bungie_name') or '',
    }

    return render_template(
        'destiny_collections.html',
        error=None,
        categories=data['categories'],
        total=data['total'],
        obtained=data['obtained'],
        meta=meta,
        catalysts=catalysts,
        catalysts_json=catalysts_json,
    )
