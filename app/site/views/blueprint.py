"""Blueprint «views»: единая точка регистрации всех роутов сайта."""
from __future__ import annotations

from flask import Blueprint

# Имя blueprint'а сохранено как 'views' — на него ссылаются шаблоны
# (url_for('views.download_file', ...)) и app.py (views_bp).
bp = Blueprint('views', __name__)
