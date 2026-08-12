"""Bungie API: доступ к профилю Destiny 2 и инвентарю."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import requests

from app import database
from app.site.auth import logger
from app.site.bungie.config import BUNGIE_TOKEN_URL, bungie_config


# 200 (Characters) — данные персонажей (класс, свет, эмблема),
# 201 (CharacterInventories) — не-экипированные предметы персонажа
#   (включая Lost Items / Special Deliveries почтмейстера),
# 205 (CharacterEquipment) — экипированные предметы.
# 800 (Collectibles) — статусы коллекций игрока (собрано/не собрано).
BUNGIE_PROFILE_URL = ('https://www.bungie.net/Platform/Destiny2/{membership_type}'
                      '/Profile/{membership_id}/?components=200,201,205,800')


# Почтмейстер (Lost Items) — это обычные предметы в компоненте
# CharacterInventories (201), у которых bucketHash указывает на
# специальные bucket'ы почтмейстера. Определяем их именно по bucketHash:
# это надёжный признак (поле location для этой задачи не подходит).
POSTMASTER_BUCKETS = {215593132}


def _is_postmaster(entry: dict) -> bool:
    """True, если предмет лежит в почтмейстере (bucket Lost Items)."""
    # Во внутренних словарях поле называется ``bucket``, в сыром ответе
    # API — ``bucketHash``.
    bucket = entry.get('bucket')
    if bucket is None:
        bucket = entry.get('bucketHash')
    try:
        return int(bucket) in POSTMASTER_BUCKETS
    except (TypeError, ValueError):
        return False



def _save_user_tokens(user_id, access_token: str, refresh_token: str,

                      token_expires: str) -> None:
    """Сохраняет OAuth-токены Bungie для пользователя."""
    with database.db() as conn:
        database.execute(
            conn,
            """UPDATE users
               SET bungie_access_token = %s,
                   bungie_refresh_token = %s,
                   bungie_token_expires = %s
               WHERE id = %s""",
            (access_token, refresh_token, token_expires, user_id),
        )


def _token_is_expired(user) -> bool:
    """True, если сохранённый access-токен протух (или даты нет)."""
    exp = user.get('bungie_token_expires')
    if not exp:
        return True
    try:
        return datetime.fromisoformat(str(exp)) <= datetime.now(timezone.utc)
    except (TypeError, ValueError):
        return True


def _refresh_access_token(user, cfg: dict[str, str]) -> str | None:
    """Обновляет access-токен через refresh_token.

    Возвращает новый access_token (и сохраняет его в БД) или None.
    """
    refresh_token = user.get('bungie_refresh_token')
    if not refresh_token:
        logger.warning(
            'Пользователь %s: refresh_token отсутствует в БД — '
            'нельзя обновить Bungie-токен. '
            'Требуется повторная привязка Bungie.', user['id'])
        return None
    # Приложение Bungie настроено как Confidential — client_secret обязателен
    # и всегда передаётся при обновлении токена.
    token_data = {
        'client_id': cfg['client_id'],
        'client_secret': cfg['client_secret'],
        'grant_type': 'refresh_token',
        'refresh_token': refresh_token,
    }
    try:
        resp = requests.post(
            BUNGIE_TOKEN_URL,
            data=token_data,
            headers={'Content-Type': 'application/x-www-form-urlencoded'},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
    except requests.HTTPError:
        # Логируем код и тело ответа Bungie (refresh_token мог быть
        # отозван/протух, либо неверный client_id/secret).
        logger.warning(
            'Пользователь %s: Bungie отказал в обновлении токена: '
            'HTTP %s, тело: %s',
            user['id'], resp.status_code,
            resp.text[:500])
        return None
    except requests.RequestException as exc:
        logger.warning('Не удалось обновить Bungie-токен: %s', exc)
        return None

    new_access = data.get('access_token')
    if not new_access:
        logger.warning(
            'Пользователь %s: Bungie refresh_token не вернул '
            'новый access_token. Тело ответа: %s',
            user['id'], str(data)[:500])
        return None

    new_refresh = data.get('refresh_token') or refresh_token
    try:
        expires_in = int(data.get('expires_in') or 0)
    except (TypeError, ValueError):
        expires_in = 0
    if expires_in > 0:
        token_expires = (datetime.now(timezone.utc)
                         + timedelta(seconds=expires_in)).isoformat()
    else:
        token_expires = ''
    _save_user_tokens(user['id'], new_access, new_refresh, token_expires)
    return new_access


def _fetch_profile(cfg: dict[str, str], access_token: str,
                   membership_type, membership_id) -> tuple[dict, int]:
    """Запрашивает профиль Destiny 2 (компоненты 200/201/205).

    Возвращает кортеж (данные Response, HTTP-статус). При сетевой ошибке
    возвращает ``(None, 0)``, при HTTP-ошибке — ``(None, <status>)``.
    Исключений не бросает.
    """
    url = BUNGIE_PROFILE_URL.format(
        membership_type=int(membership_type),
        membership_id=int(membership_id),
    )
    try:
        resp = requests.get(
            url,
            headers={
                'Authorization': f'Bearer {access_token}',
                'X-API-Key': cfg['api_key'],
            },
            timeout=10,
        )
        status = resp.status_code
        if status >= 400:
            return None, status
        return resp.json().get('Response') or {}, status
    except requests.RequestException as exc:
        logger.warning('Ошибка запроса профиля Bungie: %s', exc)
        return None, 0


def _component_data(data: dict, key: str) -> dict:
    """Безопасно извлекает ``data[key]['data']`` как словарь.

    Некоторые компоненты ответа Bungie могут приходить не словарём
    (например, просто число ``privacy`` без вложенных ``data``), поэтому
    вместо ``.get()`` используем явную проверку типа. Это исключает
    AttributeError ``'int' object has no attribute 'get'``.
    """
    section = data.get(key)
    if not isinstance(section, dict):
        return {}
    sub = section.get('data')
    if not isinstance(sub, dict):
        return {}
    return sub


def get_user_inventory(user) -> dict:


    """Возвращает инвентарь Destiny 2 пользователя через Bungie API.

    ``user`` — запись из таблицы users (с полями bungie_membership_id,
    bungie_membership_type, bungie_access_token, bungie_refresh_token,
    bungie_token_expires).

    Возвращает словарь с ключами ``ok`` (bool), ``items`` (list[dict]),
    ``postmaster`` (list[dict]) и ``characters`` (dict[character_id -> dict]):
    каждый предмет — itemInstanceId, itemHash, quantity, bucket,
    location (DestinyItemLocation: 3 = Postmaster), character_id;
    каждый персонаж — class_type, light, emblem_path.

    ``items`` содержит ТОЛЬКО обычный инвентарь/экипировку, а предметы
    из почтмейстера — в ``postmaster`` (в ``items`` они не попадают,
    чтобы не путаться со слотами оружия).

    При ошибке возвращает ``ok=False`` и ``error`` (str).


    Никогда не бросает исключений наружу — любые проблемы превращаются
    в ``ok=False`` с логом (чтобы страница не падала в 500).
    """
    try:
        return _get_user_inventory_inner(user)
    except Exception as exc:
        logger.exception('Непредвиденная ошибка при получении инвентаря '
                         'Bungie: %s', exc)
        return {'ok': False, 'error': 'Не удалось получить инвентарь. '
                                      'Попробуйте ещё раз или сообщите '
                                      'администратору.'}


def _get_user_inventory_inner(user) -> dict:
    """Внутренняя реализация get_user_inventory (без общего try/except)."""
    membership_id = user.get('bungie_membership_id')
    membership_type = user.get('bungie_membership_type')
    if not membership_id or not membership_type:
        return {
            'ok': False,
            'error': 'Bungie-аккаунт не привязан. Привяжите его в профиле.',
        }

    try:
        cfg = bungie_config()
    except RuntimeError as exc:
        logger.warning('Bungie OAuth не настроен: %s', exc)
        return {'ok': False, 'error': 'Bungie OAuth не настроен на сервере.'}

    # Предварительно обновляем токен, если он уже истёк по сохранённой дате
    # (или даты истечения вообще нет).
    access_token = user.get('bungie_access_token')
    if not access_token or _token_is_expired(user):
        logger.info('Пользователь %s: токен Bungie истёк или отсутствует, '
                    'пытаемся обновить через refresh_token',
                    user['id'])
        access_token = _refresh_access_token(user, cfg)
        if not access_token:
            logger.warning('Пользователь %s: не удалось обновить токен Bungie '
                           '(подробности выше) — пользователю показано '
                           'предложение отвязать/привязать заново', user['id'])
            return {
                'ok': False,
                'error': 'Не удалось обновить токен Bungie. '
                         'Отвяжите и привяжите Bungie заново.',
            }


    data, status = _fetch_profile(
        cfg, access_token, membership_type, membership_id)

    # Access-токен мог протухнуть между сохранением и запросом (например,
    # был отозван или истёк на стороне Bungie раньше локальной даты).
    # Тогда обновляем токен через refresh_token и повторяем запрос один раз.
    if status == 401:
        logger.info('Bungie вернул 401 (токен недействителен) — '
                    'обновляем токен и повторяем запрос')
        access_token = _refresh_access_token(user, cfg)
        if not access_token:
            return {
                'ok': False,
                'error': 'Не удалось обновить токен Bungie. '
                         'Отвяжите и привяжите Bungie заново.',
            }
        data, status = _fetch_profile(
            cfg, access_token, membership_type, membership_id)

    if status == 0 or status >= 400:
        logger.warning('Ошибка запроса инвентаря Bungie: HTTP %s', status)
        return {'ok': False, 'error': 'Не удалось получить инвентарь от Bungie.'}


    # components=200 (Characters) — данные персонажей (класс, свет, эмблема),
    # components=201 (CharacterEquipment) — экипировка,
    # components=205 (CharacterInventories) — инвентари всех персонажей.
    # Ответ Bungie имеет вид {"data": {<character_id>: {...}}, "privacy": N},
    # поэтому берём именно вложенный словарь data (с защитой от мусора).
    characters_data = _component_data(data, 'characters')
    character_equipment = _component_data(data, 'characterEquipment')
    character_inventories = _component_data(data, 'characterInventories')

    # components=800 (Collectibles) — статусы коллекций игрока.
    # Ответ Bungie для компонента 800 содержит ``profileCollectibles``
    # (учётные записи на профиль) и ``characterCollectibles`` (на персонажа).
    # Броня (особенно экзотическая) трекается ПО ПЕРСОНАЖУ и лежит только
    # в characterCollectibles — в profileCollectibles её может не быть вовсе.
    # Поэтому объединяем оба источника: предмет считается собранным, если
    # он получен хотя бы одним персонажем или на профиле.
    #
    # state — битовая маска DestinyCollectibleState, где бит 1
    # (NotObtained) означает «не получено». Предмет собран, если бит 1
    # снят: (state & 1) == 0.
    collectible_states: dict[int, int] = {}

    def _merge_collectibles(collectibles_data) -> None:
        """Добавляет состояния из одного блока ``collectibles``.

        Не перезаписывает уже известное «собрано» (1) на «не собрано» (0):
        достаточно, чтобы предмет был получен хоть одним персонажем.
        """
        if not isinstance(collectibles_data, dict):
            return
        for collectible_hash, cinfo in collectibles_data.items():
            if not isinstance(cinfo, dict):
                continue
            try:
                state = int(cinfo.get('state') or 0)
            except (TypeError, ValueError):
                state = 0
            obtained = (state & 1) == 0
            collectible_states.setdefault(
                int(collectible_hash), 1 if obtained else 0)
            if obtained:
                collectible_states[int(collectible_hash)] = 1

    # Профильные коллекции (учётные записи в целом).
    collectibles_section = _component_data(data, 'profileCollectibles')
    profile_states = collectibles_section.get('collectibles') or {}
    _merge_collectibles(profile_states)

    # Коллекции на каждого персонажа (тут живёт броня).
    character_collectibles = _component_data(data, 'characterCollectibles')
    character_states_count = 0
    for character_id, cdata in character_collectibles.items():
        if not isinstance(cdata, dict):
            continue
        char_entries = cdata.get('collectibles') or {}
        character_states_count += len(char_entries)
        _merge_collectibles(char_entries)






    # Информация о персонажах: класс (0=Титан, 1=Охотник, 2=Варлок),
    # уровень света и иконка эмблемы.
    characters: dict[str, dict] = {}
    for character_id, cdata in characters_data.items():
        if not isinstance(cdata, dict):
            continue
        characters[str(character_id)] = {
            'class_type': cdata.get('classType'),
            'light': cdata.get('light'),
            'emblem_path': cdata.get('emblemPath'),
        }

    items: list[dict] = []

    def _collect(containers: dict, *, equipped: bool = False) -> None:
        """Складывает предметы из containers в ``items``.

        Предметы почтмейстера (bucket в POSTMASTER_BUCKETS) в ``items``
        НЕ попадают — они вырезаются из общего пула и собираются
        отдельно в ``postmaster`` (см. ниже).
        """

        for character_id, container in containers.items():
            if not isinstance(container, dict):
                logger.warning('Bungie: пропущен контейнер персонажа %r '
                               '(не словарь): %r', character_id, container)
                continue

            entries = container.get('items') or []
            if not isinstance(entries, list):
                logger.warning('Bungie: пропущен список items персонажа %r '
                               '(не список): %r', character_id, entries)
                continue
            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                if _is_postmaster(entry):
                    # Lost Items исключаем из общего инвентаря.
                    continue
                items.append({
                    'itemInstanceId': entry.get('itemInstanceId'),
                    'itemHash': entry.get('itemHash'),
                    'quantity': entry.get('quantity', 1),
                    'bucket': entry.get('bucketHash'),
                    'location': entry.get('location'),
                    'character_id': character_id,
                    'equipped': equipped,
                })


    # Собираем обычные предметы: сначала экипировку, затем инвентари.
    # Из них почтмейстерские предметы уже исключены.
    _collect(character_equipment, equipped=True)
    _collect(character_inventories, equipped=False)

    # Почтмейстер (Lost Items / Special Deliveries) — это предметы из
    # characterInventories (компонент 201), у которых bucketHash —
    # почтмейстерский. Собираем их отдельно (в ``items`` они уже
    # исключены в _collect выше).
    postmaster: list[dict] = []
    for character_id, container in character_inventories.items():
        if not isinstance(container, dict):
            continue
        for entry in container.get('items') or []:
            if not isinstance(entry, dict):
                continue
            if not _is_postmaster(entry):
                continue
            postmaster.append({
                'itemInstanceId': entry.get('itemInstanceId'),
                'itemHash': entry.get('itemHash'),
                'quantity': entry.get('quantity', 1),
                'bucket': entry.get('bucketHash'),
                'location': entry.get('location'),
                'character_id': character_id,
                'equipped': False,
            })


    logger.info(
        'Bungie инвентарь пользователя %s: items=%d, postmaster=%d, '
        'collectibles=%d (profile=%d, chars=%d)',
        user.get('id'), len(items), len(postmaster),
        len(collectible_states), len(profile_states), character_states_count,
    )


    return {
        'ok': True,
        'items': items,
        'postmaster': postmaster,
        'characters': characters,
        'collectible_states': collectible_states,
    }



