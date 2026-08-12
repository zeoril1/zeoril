"""Выход из аккаунта, OAuth-роуты и конфиг-сервис."""
from __future__ import annotations

import logging

import flask
from flask import make_response, redirect, request

from app import config_service
from app.site.auth import (_cookie_secure, delete_session, request_user_is_admin,
                           validate_csrf, validate_csrf_json)
from app.site.bungie import bungie_callback, bungie_login, bungie_unlink
from app.site.config import _read_token_from_request, config_needs_action
from app.site.oauth import discord_callback, discord_login
from app.site.views.blueprint import bp

logger = logging.getLogger('BotSite')


# --------------------------------------------------------------------------- #
# Выход
# --------------------------------------------------------------------------- #

@bp.route('/exit', methods=['POST'])
def exit_():
    validate_csrf()
    delete_session(request.cookies.get('Auth'))
    resp = make_response(redirect('/'))
    # Параметры должны совпадать с теми, с которыми cookie были установлены.
    resp.delete_cookie('Auth', httponly=True, samesite='Lax',
                       secure=_cookie_secure())
    resp.delete_cookie('Id', httponly=True, samesite='Lax',
                       secure=_cookie_secure())
    return resp


# --------------------------------------------------------------------------- #
# Discord OAuth
# --------------------------------------------------------------------------- #

@bp.route('/discord/login')
def discord_login_route():
    return discord_login()


@bp.route('/discord/callback')
def discord_callback_route():
    return discord_callback()


# --------------------------------------------------------------------------- #
# Bungie OAuth
# --------------------------------------------------------------------------- #

@bp.route('/bungie/login')
def bungie_login_route():
    return bungie_login()


@bp.route('/bungie/callback')
def bungie_callback_route():
    return bungie_callback()


@bp.route('/bungie/unlink', methods=['POST'])
def bungie_unlink_route():
    return bungie_unlink()


# --------------------------------------------------------------------------- #
# Конфиг-сервис: статус и ввод токена
# --------------------------------------------------------------------------- #

@bp.route('/config_status')
def config_status():
    """AJAX-статус: показывает/скрывает блокирующее окно без перезагрузки."""
    needs = config_needs_action()
    return flask.jsonify({
        'needs_action': needs,
        'is_admin': request_user_is_admin(),
    })


@bp.route('/config_token', methods=['POST'])
def config_token():
    """Принимает токен конфиг-сервиса от администратора."""
    if not request_user_is_admin():
        return flask.jsonify({'ok': False, 'error': 'Недостаточно прав'}), 403
    if not validate_csrf_json():
        return flask.jsonify({'ok': False, 'error': 'Неверный CSRF-токен'}), 400
    token = (_read_token_from_request() or '').strip()

    if not token:
        return flask.jsonify({'ok': False, 'error': 'Токен не может быть пустым'}), 400
    try:
        ok = config_service.save_token(token)
    except Exception as exc:
        logger.warning('Ошибка сохранения токена конфиг-сервиса: %s', exc)
        return flask.jsonify({'ok': False, 'error': 'Не удалось сохранить токен'}), 500
    return flask.jsonify({'ok': ok, 'needs_action': config_needs_action()})
