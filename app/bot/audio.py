"""Аудиоисточник: декодирование MP3 в PCM без внешнего ffmpeg."""
from __future__ import annotations

import miniaudio
from discord import AudioSource
from discord.opus import Encoder as OpusEncoder


class MP3AudioSource(AudioSource):
    """Аудиоисточник, который декодирует MP3 без ffmpeg.

    Использует miniaudio (нативная библиотека без внешних бинарников):
    декодирует mp3 в PCM 16-бит, 48 кГц, стерео — ровно тот формат,
    который py-cord ожидает от AudioSource. Opus-кодирование затем
    выполняет сам Discord (встроенная libopus).
    """

    def __init__(self, filename: str) -> None:
        # Opus-кодер создаётся заранее, чтобы libopus была загружена.
        OpusEncoder(application='audio', bitrate=128)

        # PCM 16-бит, 48 кГц, стерео — требуемый формат для Discord.
        self._stream = miniaudio.stream_file(
            filename,
            output_format=miniaudio.SampleFormat.SIGNED16,
            nchannels=2,
            sample_rate=48000,
            frames_to_read=960,
        )

    def read(self) -> bytes:
        try:
            return next(self._stream).tobytes()
        except (StopIteration, ValueError):
            return b''

    def is_opus(self) -> bool:
        return False

    def cleanup(self) -> None:
        try:
            self._stream.close()
        except Exception:
            pass
