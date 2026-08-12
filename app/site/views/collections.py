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

import logging

import flask
from flask import redirect, render_template

from app.site.auth import current_user
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




def _collectible_states_from(user) -> dict[int, int]:
    """Получает статусы коллекций игрока через Bungie API."""
    result = get_user_inventory(user)
    if not result.get('ok'):
        # Коллекции не получим без токена/привязки — вернём пустой статус
        # (все предметы будут «не собраны»), но саму страницу покажем.
        logger.warning('Не удалось получить статусы коллекций: %s',
                       result.get('error'))
        return {}
    return result.get('collectible_states') or {}


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
        )

    states = _collectible_states_from(user)
    data = _apply_states(categories_raw, states)
    # Если одно и то же название встречается в категории несколько раз,
    # оставляем один предмет (с приоритетом «уже собран»).
    _dedupe_items_by_name(data['categories'])
    # Листовые подгруппы-«сеты» (armor → titan → pve) схлопываем в одну
    # сетку родителя, чтобы они не отображались отдельными подпунктами.
    _flatten_leaf_groups(data['categories'])
    # Пересчитываем счётчики на всех уровнях дерева.
    data = _recount(data['categories'])

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
    )
