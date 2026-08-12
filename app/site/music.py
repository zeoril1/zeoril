"""Безопасная загрузка и список музыкальных файлов."""
from __future__ import annotations

import os
import re

from app.paths import MUSIC_DIR

ALLOWED_EXTENSIONS = {'.mp3'}


def safe_filename(filename: str) -> str:
    """Убирает пути и недопустимые символы из имени файла."""
    name = os.path.basename(filename.replace('\\', '/'))
    name = re.sub(r'[\x00-\x1f<>:"/\\|?*]', '_', name)
    name = name.strip(' .')
    return name or 'file'


def is_allowed_music(filename: str) -> bool:
    return os.path.splitext(filename)[1].lower() in ALLOWED_EXTENSIONS


def save_music(upload) -> tuple[bool, str]:
    """Сохраняет загруженный mp3. Возвращает (успех, сообщение)."""
    if upload is None or not upload.filename:
        return False, 'Выберите файл для загрузки'
    filename = safe_filename(upload.filename)
    if not is_allowed_music(filename):
        return False, 'Допускаются только файлы .mp3'
    path = os.path.join(MUSIC_DIR, filename)
    if os.path.exists(path):
        return False, 'Такая песня уже есть'
    upload.save(path)
    return True, f'Файл {filename} загружен'


def list_music_files() -> list[str]:
    files = []
    for root, _dirs, names in os.walk(MUSIC_DIR):
        for name in names:
            if is_allowed_music(name):
                files.append(name)
    return sorted(files)
