"""Клиент Discord: регистрация событий и воспроизведение звука."""
from __future__ import annotations

import asyncio
import logging
import os

import discord
from mutagen.mp3 import MP3

from app import database
from app.paths import MUSIC_DIR
from app.bot import config
from app.bot.audio import MP3AudioSource
from app.bot.users import get_user_song, update_guild_members

logger = logging.getLogger('discord_bot')


def _intents() -> discord.Intents:
    intents = discord.Intents.default()
    intents.members = True
    intents.messages = True
    # Требуется для чтения текста сообщений (privileged intent).
    intents.message_content = True
    return intents



def create_bot() -> discord.Client:
    """Создаёт клиента Discord и регистрирует обработчики событий.

    Должна вызываться ТОЛЬКО внутри работающего event loop (см. bot_main),
    чтобы все внутренние объекты py-cord (heartbeat-поток, aiohttp, Event)
    были привязаны именно к этому циклу.
    """
    client = discord.Client(intents=_intents())

    @client.event
    async def on_ready():
        logger.info('Бот вошёл в сеть как %s (ID: %s)', client.user, client.user.id)
        # Синхронные обращения к БД — в отдельном потоке, чтобы не блокировать loop.
        await asyncio.to_thread(database.ensure_schema)
        for guild in client.guilds:
            await asyncio.to_thread(update_guild_members, guild)

    @client.event
    async def on_guild_join(guild):
        """При добавлении бота на новый сервер заносим его участников в БД."""
        await asyncio.to_thread(update_guild_members, guild)

    @client.event
    async def on_member_join(member):
        """Новый участник на сервере — обновляем список участников и логируем."""
        if member.bot:
            return
        await asyncio.to_thread(update_guild_members, member.guild)
        try:
            await asyncio.to_thread(
                database.log_user_action,
                member.id,
                'guild_join',
                id_guild=member.guild.id,
                guild_name=member.guild.name,
                target_id=member.guild.id,
                target_name=member.guild.name,
            )
        except Exception as exc:
            logger.warning('Не удалось залогировать заход участника: %s', exc)

    @client.event
    async def on_member_remove(member):
        """Участник покинул сервер — убираем сервер из списка и логируем."""
        if member.bot:
            return
        await asyncio.to_thread(database.remove_user_server,
                                member.id, member.guild.id)
        try:
            await asyncio.to_thread(
                database.log_user_action,
                member.id,
                'guild_leave',
                id_guild=member.guild.id,
                guild_name=member.guild.name,
                target_id=member.guild.id,
                target_name=member.guild.name,
            )
        except Exception as exc:
            logger.warning('Не удалось залогировать выход участника: %s', exc)



    @client.event
    async def on_message(message):
        """Логируем каждое сообщение участника на сервере в БД."""
        if message.author.bot:
            return
        if not message.guild:
            return
        content = (message.clean_content or '')[:2000]
        try:
            await asyncio.to_thread(
                database.log_message,
                message.author.id,
                message.id,
                message.channel.id,
                content,
                message.created_at.isoformat(),
                id_guild=message.guild.id,
                guild_name=message.guild.name,
            )
        except Exception as exc:
            logger.warning('Не удалось залогировать сообщение: %s', exc)

    @client.event
    async def on_message_delete(message):
        """Удаление сообщения — помечаем в логах."""
        if message.author and not message.author.bot:
            try:
                await asyncio.to_thread(
                    database.log_user_action,
                    message.author.id,
                    'message_delete',
                    id_guild=getattr(message.guild, 'id', None),
                    guild_name=getattr(message.guild, 'name', None),
                    target_id=message.id,
                    details=(message.clean_content or '')[:2000] or None,
                )
            except Exception as exc:
                logger.warning('Не удалось залогировать удаление сообщения: %s', exc)


    @client.event
    async def on_message_edit(before, after):
        """Редактирование сообщения — записываем новое содержимое."""
        if after.author is None or after.author.bot:
            return
        if not after.guild:
            return
        try:
            content = (after.clean_content or '')[:2000]
            await asyncio.to_thread(
                database.log_message,
                after.author.id,
                after.id,
                after.channel.id,
                content,
                after.edited_at.isoformat() if after.edited_at
                else after.created_at.isoformat(),
                id_guild=after.guild.id,
                guild_name=after.guild.name,
            )
            await asyncio.to_thread(
                database.log_user_action,
                after.author.id,
                'message_edit',
                id_guild=after.guild.id,
                guild_name=after.guild.name,
                target_id=after.id,
                details=content or None,
            )

        except Exception as exc:
            logger.warning('Не удалось залогировать редактирование сообщения: %s', exc)

    @client.event
    async def on_voice_state_update(member, before, after):
        if member.id == config.BOT_USER_ID:
            return

        guild_id = getattr(member.guild, 'id', None)
        guild_name = getattr(member.guild, 'name', None)

        # Переход между голосовыми каналами.
        if (before.channel is not None and after.channel is not None
                and before.channel.id != after.channel.id):
            try:
                await asyncio.to_thread(
                    database.log_user_action,
                    member.id,
                    'voice_move',
                    id_guild=guild_id,
                    guild_name=guild_name,
                    target_id=after.channel.id,
                    target_name=after.channel.name,
                    details=f'{before.channel.name} → {after.channel.name}',
                )
            except Exception as exc:
                logger.warning('Не удалось залогировать переход: %s', exc)

        # Заход в голосовой канал.
        elif after.channel is not None and before.channel is None:
            try:
                await asyncio.to_thread(
                    database.log_user_action,
                    member.id,
                    'voice_join',
                    id_guild=guild_id,
                    guild_name=guild_name,
                    target_id=after.channel.id,
                    target_name=after.channel.name,
                )
            except Exception as exc:
                logger.warning('Не удалось залогировать заход в канал: %s', exc)

        # Выход из голосового канала — музыку не играем.
        elif before.channel is not None and after.channel is None:
            try:
                await asyncio.to_thread(
                    database.log_user_action,
                    member.id,
                    'voice_leave',
                    id_guild=guild_id,
                    guild_name=guild_name,
                    target_id=before.channel.id,
                    target_name=before.channel.name,
                )
            except Exception as exc:
                logger.warning('Не удалось залогировать выход из канала: %s', exc)
            return


        # Воспроизведение музыки при заходе/переходе в голосовой канал.
        if before.channel != after.channel and after.channel is not None:



            song = await asyncio.to_thread(get_user_song, member.id)
            if song is None:
                return
            music_path = os.path.join(MUSIC_DIR, song)

            try:
                file = MP3(music_path)
                time_sleep = file.info.length + 0.2
            except Exception as e:
                logger.warning('Не удалось прочитать %s: %s', music_path, e)
                return

            try:
                voice = discord.utils.get(client.voice_clients,
                                          guild=member.guild)
                if voice is not None and voice.is_connected():
                    if voice.is_playing():
                        logger.info(
                            'Канал занят, пропускаем пользователя %s',
                            member.id)
                        return
                    music = voice
                else:
                    music = await member.voice.channel.connect()

                music.play(MP3AudioSource(music_path))

                try:
                    await asyncio.to_thread(
                        database.log_user_action,
                        member.id,
                        'song_play',
                        id_guild=guild_id,
                        guild_name=guild_name,
                        details=song,
                    )
                except Exception as exc:
                    logger.warning('Не удалось залогировать воспроизведение: %s', exc)


                try:
                    await asyncio.sleep(time_sleep)

                finally:
                    if music.is_playing():
                        music.stop()
                    if music.is_connected():
                        await music.disconnect()
            except Exception as e:
                logger.exception('Ошибка воспроизведения для %s: %s',
                                 member.id, e)

    return client
