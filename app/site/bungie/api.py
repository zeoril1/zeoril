"""Bungie API: доступ к профилю Destiny 2 и инвентарю."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import requests

from app import database
from app.site.auth import logger
from app.site.bungie.config import BUNGIE_TOKEN_URL, bungie_config


# Компоненты профиля: 102 (сейф), 200 (персонажи), 201 (инвентари, включая
# почтмейстер), 205 (экипировка), 300 (ItemInstances — primaryStat = сила),
# 301/305/309 (цели/сокеты/плаги — прогресс катализаторов), 800 (коллекции).
BUNGIE_PROFILE_URL = ('https://www.bungie.net/Platform/Destiny2/{membership_type}'
                      '/Profile/{membership_id}/?components=102,200,201,205,300,301,305,309,800')


# Почтмейстерские предметы (Lost Items) в 201 определяются по bucketHash
# (поле location для этой задачи не подходит).
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


def _item_power(entry: dict, instances: dict) -> int:
    """Сила (Power/Light) предмета (0, если её нет).

    Источники по очереди:
    1) ``primaryStat`` у самого компонента предмета (если пришёл);
    2) компонент 300 (ItemInstances): ``instances[instanceId].primaryStat.value``
       — надёжный источник силы из профильного ответа.
    """
    primary = entry.get('primaryStat')
    if isinstance(primary, dict):
        try:
            return int(primary.get('value') or 0)
        except (TypeError, ValueError):
            pass
    instance_id = entry.get('itemInstanceId')
    if not instance_id:
        return 0
    inst = instances.get(str(instance_id))
    if not isinstance(inst, dict):
        return 0
    primary = inst.get('primaryStat') or {}
    try:
        return int(primary.get('value') or 0)
    except (TypeError, ValueError):
        return 0


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
                   membership_type, membership_id,
                   components: str | None = None) -> tuple[dict, int]:
    """Запрашивает профиль Destiny 2 (компоненты 200/201/205).

    ``components`` — при желании можно передать свой список компонентов
    (через запятую) для лёгких запросов; по умолчанию используется
    полный набор из ``BUNGIE_PROFILE_URL``.

    Возвращает кортеж (данные Response, HTTP-статус). При сетевой ошибке
    возвращает ``(None, 0)``, при HTTP-ошибке — ``(None, <status>)``.
    Исключений не бросает.
    """
    if components:
        url = BUNGIE_PROFILE_URL.split('?')[0] + '?components=' + components
    else:
        url = BUNGIE_PROFILE_URL
    url = url.format(
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

    ``user`` — запись из таблицы users (bungie_membership_id/type,
    bungie_access_token/refresh_token, bungie_token_expires).

    Возвращает словарь: ``ok`` (bool), ``items`` (обычный инвентарь и
    экипировка), ``vault`` (сейф), ``postmaster`` (Lost Items), ``characters``
    (class_type, light, emblem_path), а также collectible_states,
    item_objectives, item_socket_plugs, item_plug_objectives (катализаторы).
    При ошибке возвращает ``ok=False`` и ``error`` (str).

    Никогда не бросает исключений наружу.
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


    # components=200/201/205 (персонажи, инвентари, экипировка). Ответ Bungie —
    # {"data": {<character_id>: {...}}}, берём вложенный словарь data.
    characters_data = _component_data(data, 'characters')
    character_equipment = _component_data(data, 'characterEquipment')
    character_inventories = _component_data(data, 'characterInventories')

    # components=800 (Collectibles). Броня трекается по персонажу (лежит в
    # characterCollectibles), поэтому объединяем оба источника.
    # state — битовая маска: бит 1 (NotObtained) = «не получено»,
    # т.е. предмет собран при (state & 1) == 0.
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


    # components=301/305/309 — прогресс катализаторов (itemComponents):
    # objectives[inst].objectives — цели (objectiveHash + прогресс),
    # sockets[inst].sockets — установленные плаги (plugHash),
    # plugObjectives[inst].objectivesPerPlug — словарь
    # plugItemHash -> [{objectiveHash, progress, ...}]: реальные убийства
    # катализатора, даже если у самого катализатора цели в манифесте нет.
    item_components = data.get('itemComponents')
    if not isinstance(item_components, dict):
        item_components = {}

    # Компонент 300 (ItemInstances): instanceId -> primaryStat.value (сила).
    instances_data = _component_data(item_components, 'instances')

    item_objectives: dict[str, dict[int, dict]] = {}
    objectives_data = _component_data(item_components, 'objectives')
    for instance_id, odata in objectives_data.items():
        if not isinstance(odata, dict):
            continue
        objs = odata.get('objectives')
        if not isinstance(objs, list):
            continue
        per: dict[int, dict] = {}
        for obj in objs:
            if not isinstance(obj, dict):
                continue
            try:
                obj_hash = int(obj.get('objectiveHash'))
            except (TypeError, ValueError):
                continue
            if not obj_hash:
                continue
            per[obj_hash] = {
                'progress': obj.get('progress') or 0,
                'completion_value': obj.get('completionValue') or 0,
                'complete': bool(obj.get('complete', False)),
            }
        if per:
            item_objectives[str(instance_id)] = per

    item_socket_plugs: dict[str, list[int]] = {}
    sockets_data = _component_data(item_components, 'sockets')
    for instance_id, sdata in sockets_data.items():
        if not isinstance(sdata, dict):
            continue
        sockets = sdata.get('sockets')
        if not isinstance(sockets, list):
            continue
        plugs: list[int] = []
        for socket in sockets:
            if not isinstance(socket, dict):
                continue
            plug_hash = socket.get('plugHash')
            if plug_hash is None:
                continue
            try:
                plugs.append(int(plug_hash))
            except (TypeError, ValueError):
                continue
        item_socket_plugs[str(instance_id)] = plugs

    # components=309 (ItemPlugObjectives). objectivesPerPlug — словарь
    # plugItemHash -> список целей с реальным прогрессом.
    item_plug_objectives: dict[str, dict[int, dict[int, dict]]] = {}
    plug_objectives_data = _component_data(item_components, 'plugObjectives')
    for instance_id, pdata in plug_objectives_data.items():
        if not isinstance(pdata, dict):
            continue
        per_plug = pdata.get('objectivesPerPlug')
        if not isinstance(per_plug, dict):
            continue
        by_plug: dict[int, dict[int, dict]] = {}
        for plug_raw, obj_list in per_plug.items():
            try:
                plug_hash = int(plug_raw)
            except (TypeError, ValueError):
                continue
            if not isinstance(obj_list, list):
                continue
            by_obj: dict[int, dict] = {}
            for obj in obj_list:
                if not isinstance(obj, dict):
                    continue
                try:
                    obj_hash = int(obj.get('objectiveHash'))
                except (TypeError, ValueError):
                    continue
                if not obj_hash:
                    continue
                by_obj[obj_hash] = {
                    'progress': obj.get('progress') or 0,
                    'completion_value': obj.get('completionValue') or 0,
                    'complete': bool(obj.get('complete', False)),
                }
            if by_obj:
                by_plug[plug_hash] = by_obj
        if by_plug:
            item_plug_objectives[str(instance_id)] = by_plug

    # components=202 (ProfileInventories) — сейф (Vault): почти вся экзотика
    # игрока лежит там, а в ``items`` — только экипировка и инвентари.
    profile_inventory = _component_data(data, 'profileInventory')
    vault: list[dict] = []
    for entry in profile_inventory.get('items') or []:
        if not isinstance(entry, dict):
            continue
        vault.append({
            'itemInstanceId': entry.get('itemInstanceId'),
            'itemHash': entry.get('itemHash'),
            'quantity': entry.get('quantity', 1),
            'bucket': entry.get('bucketHash'),
            'location': entry.get('location'),
            'character_id': None,
            'equipped': False,
            'power': _item_power(entry, instances_data),
        })

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
                    'power': _item_power(entry, instances_data),
                })

    # Собираем обычные предметы: сначала экипировку, затем инвентари.
    # Из них почтмейстерские предметы уже исключены.
    _collect(character_equipment, equipped=True)
    _collect(character_inventories, equipped=False)

    # Почтмейстерские предметы (bucket почтмейстера в 201) собираем отдельно.
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
                'power': _item_power(entry, instances_data),
            })


    logger.info(
        'Bungie инвентарь пользователя %s: items=%d, vault=%d, postmaster=%d, '
        'collectibles=%d (profile=%d, chars=%d), objectives_instances=%d, '
        'sockets_instances=%d, plug_objectives_instances=%d',
        user.get('id'), len(items), len(vault), len(postmaster),
        len(collectible_states), len(profile_states), character_states_count,
        len(item_objectives), len(item_socket_plugs),
        len(item_plug_objectives),
    )

    return {
        'ok': True,
        'items': items,
        # Предметы из сейфа (Vault) — отдельно, чтобы не ломать инвентарь.
        'vault': vault,
        'postmaster': postmaster,
        'characters': characters,
        'collectible_states': collectible_states,
        # Прогресс целей предметов (катализаторы) по itemInstanceId.
        'item_objectives': item_objectives,
        # Установленные в сокеты плаги (катализаторы) по itemInstanceId.
        'item_socket_plugs': item_socket_plugs,
        # Связки плаг -> цель (для поиска цели катализатора).
        'item_plug_objectives': item_plug_objectives,
    }

# Компоненты профиля для проверки «что есть у игрока» (лёгкий запрос без
# прогресса катализаторов и коллекций): сейв, инвентари и экипировка.
OWNED_COMPONENTS = '102,201,205'


def get_user_owned_hashes(user) -> tuple[bool, set[int]]:
    """Возвращает (ok, hashes) — множество itemHash предметов игрока.

    Учитываются экипировка, инвентари персонажей и сейв (Vault); предметы
    почтмейстера игнорируются. Нужно для рулетки челленджей: в пул игрока
    должны попадать только те оружия, которые у него уже есть в Destiny 2.

    При любой ошибке возвращает ``(False, set())`` — исключений наружу
    не бросает (как и ``get_user_inventory``).
    """
    try:
        return _get_user_owned_hashes_inner(user)
    except Exception as exc:
        logger.exception('Непредвиденная ошибка при получении инвентаря '
                         'Bungie (owned): %s', exc)
        return False, set()

def _get_user_owned_hashes_inner(user) -> tuple[bool, set[int]]:
    """Внутренняя реализация get_user_owned_hashes (без try/except)."""
    membership_id = user.get('bungie_membership_id')
    membership_type = user.get('bungie_membership_type')
    if not membership_id or not membership_type:
        return False, set()

    try:
        cfg = bungie_config()
    except RuntimeError as exc:
        logger.warning('Bungie OAuth не настроен: %s', exc)
        return False, set()

    access_token = user.get('bungie_access_token')
    if not access_token or _token_is_expired(user):
        access_token = _refresh_access_token(user, cfg)
        if not access_token:
            logger.warning('Пользователь %s: не удалось обновить токен '
                           'Bungie для проверки инвентаря (owned)',
                           user['id'])
            return False, set()

    data, status = _fetch_profile(
        cfg, access_token, membership_type, membership_id,
        components=OWNED_COMPONENTS)
    if status == 401:
        access_token = _refresh_access_token(user, cfg)
        if not access_token:
            return False, set()
        data, status = _fetch_profile(
            cfg, access_token, membership_type, membership_id,
            components=OWNED_COMPONENTS)
    if status == 0 or status >= 400:
        logger.warning('Ошибка запроса инвентаря Bungie (owned): HTTP %s',
                       status)
        return False, set()

    hashes: set[int] = set()

    # Сейв (ProfileInventories): data['profileInventory']['data']['items'].
    vault = _component_data(data, 'profileInventory')
    for entry in vault.get('items') or []:
        if not isinstance(entry, dict) or _is_postmaster(entry):
            continue
        try:
            hashes.add(int(entry.get('itemHash')))
        except (TypeError, ValueError):
            continue

    # Инвентари и экипировка персонажей:
    # data['<component>']['data'] = {character_id: {'items': [...]}}.
    def _collect(containers: dict) -> None:
        for container in containers.values():
            if not isinstance(container, dict):
                continue
            for entry in container.get('items') or []:
                if not isinstance(entry, dict) or _is_postmaster(entry):
                    continue
                try:
                    hashes.add(int(entry.get('itemHash')))
                except (TypeError, ValueError):
                    continue

    _collect(_component_data(data, 'characterInventories'))
    _collect(_component_data(data, 'characterEquipment'))
    return True, hashes

