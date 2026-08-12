"""Создание Flask-приложения сайта."""
from __future__ import annotations

import secrets

from flask import Flask
from werkzeug.middleware.proxy_fix import ProxyFix

from app import config_service, database
from app.paths import ROOT_DIR
from app.site.auth import _cookie_secure, csrf_token
from app.site.config import config_needs_action
from app.site.lang import LANGS, get_lang


def create_app() -> Flask:
    """Создаёт и настраивает Flask-приложение."""
    app = Flask(
        __name__,
        template_folder=str(ROOT_DIR / 'templates'),
        static_folder=str(ROOT_DIR / 'static'),
    )

    # За reverse-proxy (nginx) доверяем заголовкам X-Forwarded-Proto/-For/-Host.
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

    app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 50 МБ на загрузку
    # SECRET_KEY из конфиг-сервиса; fallback на время старта, если он недоступен.
    app.secret_key = config_service.get('SECRET_KEY') or secrets.token_hex(32)

    # Флаг Secure сессионной cookie выставляется динамически — см. _cookie_secure().
    app.config['SESSION_COOKIE_SECURE'] = False

    app.jinja_env.globals['csrf_token'] = csrf_token

    @app.before_request
    def _sync_session_cookie_secure() -> None:
        """Синхронизирует Secure-флаг сессионной cookie с текущим запросом."""
        app.config['SESSION_COOKIE_SECURE'] = _cookie_secure()

    @app.context_processor
    def _inject_config_state():
        """Передаёт в шаблоны флаг, что нужно показать блокирующее окно."""
        try:
            needs = config_needs_action()
        except Exception:
            needs = False
        return {'config_needs_action': needs}

    @app.context_processor
    def _inject_lang():
        """Передаёт в шаблоны выбранный язык и список доступных языков."""
        return {'lang': get_lang(), 'languages': LANGS}

    database.ensure_schema()

    _register_blueprints(app)
    return app

def _register_blueprints(app: Flask) -> None:
    """Регистрирует blueprint'ы приложения."""
    from app.site.destiny_game import bp as game_bp
    from app.site.views import bp as views_bp

    app.register_blueprint(views_bp)
    app.register_blueprint(game_bp)
