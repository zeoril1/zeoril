FROM python:3.12-slim-bookworm

# libopus — кодек для голосовых функций Discord; mp3 декодируется
# через miniaudio, поэтому ffmpeg не нужен.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libopus0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Сначала зависимости — используем кэш слоёв при изменениях кода.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Папка для данных монтируется volume'ом из docker-compose.
RUN mkdir -p /app/resources

EXPOSE 80

# Бот запускается из docker-compose командой: python DiscordBot.py
CMD ["python", "BotSite.py"]
