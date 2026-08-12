"""Точка входа Flask-сайта клана HG.

Реальная логика живёт в пакете app/site; здесь только запуск.
"""
from app.logging import setup_logging

logger = setup_logging('BotSite', filter_werkzeug=True)

from app.site.app import create_app

app = create_app()


if __name__ == '__main__':
    from waitress import serve
    # threads увеличены: SSE-подключения рулетки держат по потоку на клиента.
    serve(app, host='0.0.0.0', port=80, threads=32)

