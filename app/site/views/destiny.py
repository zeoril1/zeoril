"""Destiny 2: список предметов и челленджи экзотики."""
from __future__ import annotations

import logging

import flask
from flask import redirect, render_template, request

from app import database
from app.site.auth import current_user, user_rights, validate_csrf_json
from app.site.bungie import items as manifest_items
from app.site.lang import get_lang
from app.site.views.blueprint import bp

logger = logging.getLogger('BotSite')


# Подписи числовых item_type для отображения.
ITEM_TYPE_LABELS = {
    0: 'None',
    1: 'Currency',
    2: 'Armor',
    3: 'Weapon',
    7: 'Message',
    8: 'Engram',
    9: 'Consumable',
    10: 'Exchange Material',
    11: 'Mission Reward',
    12: 'Quest Step',
    13: 'Quest Step Complete',
    14: 'Emblem',
    15: 'Quest',
    16: 'Subclass',
    17: 'Clan Banner',
    18: 'Aura',
    19: 'Mod',
    20: 'Dummy',
    21: 'Ship',
    22: 'Vehicle',
    23: 'Emote',
    24: 'Ghost',
    25: 'Jackolytes',
    26: 'Shader',
    27: 'Ornament',
    28: 'Artifact',
    29: 'Transmat Effect',
    30: 'Bundle',
}

DESTINY_LIMITS = [10, 50, 100, 200, 500]

# Числовые defaultDamageType → название стихии (Element).
DAMAGE_TYPE_LABELS = {
    1: 'Kinetic',
    2: 'Arc',
    3: 'Solar',
    4: 'Void',
    5: 'Raid',
    6: 'Stasis',
    7: 'Strand',
}

# Числовые equippingBlock.ammoType → название типа патронов (Ammo).
AMMO_TYPE_LABELS = {
    0: 'None',
    1: 'Primary',
    2: 'Special',
    3: 'Heavy',
}


@bp.route('/destiny')
def destiny():
    """Страница со списком предметов Destiny 2 из локального манифеста."""
    user = current_user()
    if user is None:
        return redirect('/')

    # Количество записей (по умолчанию 50).
    try:
        limit = int(request.args.get('limit', '50'))
    except (TypeError, ValueError):
        limit = 50
    if limit not in DESTINY_LIMITS:
        limit = 50

    # Фильтр по tier_type_name (редкость).
    tier = (request.args.get('tier') or '').strip()

    # Фильтр по item_type (числовой тип).
    item_type_raw = (request.args.get('item_type') or '').strip()
    item_type = None
    if item_type_raw.isdigit():
        item_type = int(item_type_raw)

    # Только предметы с описанием.
    only_filled = (request.args.get('only_filled') or '').strip() in ('1', 'true', 'on')

    # Номер страницы (с 1).
    try:
        page = int(request.args.get('page', '1'))
    except (TypeError, ValueError):
        page = 1
    page = max(1, page)

    # Предметы читаем из манифеста в локали выбранного языка.
    lang = get_lang()
    items, total = manifest_items.get_items(
        locale=lang, limit=limit, tier_type_name=tier or None,
        item_type=item_type, page=page, only_filled=only_filled)

    total_pages = max(1, (total + limit - 1) // limit)

    if page > total_pages:
        page = total_pages
        items, total = manifest_items.get_items(
            locale=lang, limit=limit, tier_type_name=tier or None,
            item_type=item_type, page=page, only_filled=only_filled)

    tiers, types = manifest_items.get_filters(lang)

    return render_template(
        'destiny.html',
        items=items,
        total=total,
        total_pages=total_pages,
        page=page,
        limits=DESTINY_LIMITS,
        limit=limit,
        tiers=tiers,
        item_types=types,
        item_type_labels=ITEM_TYPE_LABELS,
        damage_type_labels=DAMAGE_TYPE_LABELS,
        ammo_type_labels=AMMO_TYPE_LABELS,
        selected_tier=tier,

        selected_item_type=item_type,
        only_filled=only_filled,
    )


@bp.route('/destiny/challenges')
def destiny_challenges():
    """Страница с челленджами экзотического оружия (destiny_challenges)."""
    user = current_user()
    if user is None:
        return redirect('/')

    rights = user_rights(user['id'])
    is_admin = 'Admin' in rights

    # Количество записей (по умолчанию 50).
    try:
        limit = int(request.args.get('limit', '50'))
    except (TypeError, ValueError):
        limit = 50
    if limit not in DESTINY_LIMITS:
        limit = 50

    only_filled = (request.args.get('only_filled') or '').strip() in ('1', 'true', 'on')


    # Номер страницы (с 1).
    try:
        page = int(request.args.get('page', '1'))
    except (TypeError, ValueError):
        page = 1
    page = max(1, page)

    # Челленджи из БД + имена/иконки из манифеста (в локали выбранного языка).
    challenges_raw, total = database.get_destiny_challenges(
        only_filled=only_filled)
    lang = get_lang()
    hashes = [int(c['item_hash']) for c in challenges_raw
              if str(c['item_hash']).isdigit()]
    info = manifest_items.get_items_by_hashes(lang, hashes)

    challenges = []
    for c in challenges_raw:
        it = info.get(int(c['item_hash'])) or {}
        challenges.append({
            'item_hash': c['item_hash'],
            'item_name': c.get('item_name'),
            'name': (it.get('name') or c.get('item_name')
                     or f"#{c['item_hash']}"),
            'icon': it.get('icon') or '',
            'solo_challenge': c.get('solo_challenge'),
            'team_challenge': c.get('team_challenge'),
            'notes': c.get('notes'),
        })
    challenges.sort(key=lambda x: (x['name'] or '').lower())

    total_pages = max(1, (total + limit - 1) // limit)
    if page > total_pages:
        page = total_pages
    start = (page - 1) * limit
    challenges = challenges[start:start + limit]

    return render_template(
        'destiny_challenges.html',
        challenges=challenges,
        total=total,
        total_pages=total_pages,
        page=page,
        limits=DESTINY_LIMITS,
        limit=limit,
        only_filled=only_filled,
        is_admin=is_admin,
    )


@bp.route('/destiny/challenges/api/save', methods=['POST'])
def destiny_challenges_api_save():
    """AJAX: сохранить отредактированный челлендж (solo/team/notes)."""
    user = current_user()
    if user is None:
        return flask.jsonify({'ok': False, 'error': 'Не авторизован'}), 401
    if 'Admin' not in user_rights(user['id']):
        return flask.jsonify({'ok': False, 'error': 'Недостаточно прав'}), 403
    if not validate_csrf_json():
        return flask.jsonify({'ok': False, 'error': 'Неверный CSRF-токен'}), 400

    payload = request.get_json(silent=True) or {}
    item_hash_raw = (payload.get('item_hash') or '').strip()
    if not item_hash_raw.isdigit():
        return flask.jsonify({'ok': False, 'error': 'Некорректный item_hash'}), 400
    item_hash = int(item_hash_raw)

    def _clean(value) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    solo = _clean(payload.get('solo_challenge'))
    team = _clean(payload.get('team_challenge'))
    notes = _clean(payload.get('notes'))

    try:
        updated = database.update_destiny_challenge(
            item_hash,
            solo_challenge=solo,
            team_challenge=team,
            notes=notes,
        )
    except Exception as exc:
        logger.warning('Ошибка сохранения челленджа %s: %s', item_hash, exc)
        return flask.jsonify({'ok': False, 'error': 'Ошибка базы данных'}), 500

    if not updated:
        return flask.jsonify({
            'ok': False,
            'error': 'Запись не найдена. Возможно, она была удалена.',
        }), 404

    return flask.jsonify({
        'ok': True,
        'item_hash': item_hash,
        'solo_challenge': solo,
        'team_challenge': team,
        'notes': notes,
    })
