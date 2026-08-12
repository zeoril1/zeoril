"""Точка входа Discord-бота.

Реальная логика живёт в пакете app/bot; здесь только запуск.
"""
from app.logging import setup_logging
from app.bot.main import start

setup_logging('discord_bot')

if __name__ == '__main__':
    start()
