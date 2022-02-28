# -*- coding: utf-8 -*-
import discord
import requests
import gspread
import logging
import time
import datetime
from time import gmtime, strftime
import json, os
import random
from discord import FFmpegPCMAudio
from mutagen.mp3 import MP3
import ast
import sqlite3
import aiohttp

logging.basicConfig(filename="resources/logs.txt", level=logging.INFO)

cookies = []
users = []
vendor_emoji = []
token = ''
members_destiny =[]

bot = discord.Bot()

conn = sqlite3.connect('resources/discord.sqlite3', check_same_thread=False)
cur = conn.cursor()

Discord_webhook = "https://discord.com/api/webhooks/943063839015067690/OftJxg_MMHlgssbNvQCpaVL8YbpX5eVqAswVv8-MA317XgpSxincSeY-f_9iRB_E1Ro8"
cur.execute("SELECT value FROM Configs WHERE Name='DISCORD_BOT_TOKEN';")
DISCORD_BOT_TOKEN = cur.fetchall()[0][0]
cur.execute("SELECT value FROM Configs WHERE Name='HEADERS';")
HEADERS = {"X-API-Key": str(cur.fetchall()[0][0])}
cur.execute("SELECT value FROM Configs WHERE Name='base_url';")
base_url = cur.fetchall()[0][0]


maps = ['Алтарь пламени', 'Аномалия', 'Павшее знамя', 'Пепелище', 'Котёл', 'Конвергенция', 'Мёртвые скалы', 'Далёкие берега',
'Бесконечная долина', 'Синий исход', 'Крепость', 'Фрагмент', 'Джавелин - 4', 'Центр города', 'Пассифика', 'Сияющие скалы',
'Ржавая земля', 'Сумеречная Брешь', 'Вдовий двор', 'Червеприбежище']

@bot.event
async def on_ready():
    print(f"We have logged in as {bot.user}")

@bot.slash_command(guild_ids=[394939677590945804], name="hello")
async def hello(ctx):
    await ctx.respond(f"Hello!")

@bot.event
async def on_voice_state_update(member, before, after):
    if member.id != 672119705212944385:
        return_song = play_song(member.id)
        if return_song != None and before.channel != after.channel and after.channel is not None:
            voice = discord.utils.get(bot.voice_clients, guild=member.guild)
            try:
                if not voice is None:  # test if voice is None
                    if not voice.is_connected():
                        music = await discord.VoiceChannel.connect(member.voice.channel)
                        music.play(FFmpegPCMAudio(return_song[1]))
                        time.sleep(return_song[0])
                        await music.disconnect()
                else:
                    music = await discord.VoiceChannel.connect(member.voice.channel)
                    music.play(FFmpegPCMAudio(return_song[1]))
                    time.sleep(return_song[0])
                    await music.disconnect()
            except:
                if voice.is_connected():
                    await music.disconnect()
                print('Ошибка')


def play_song(id_song):
    sql = "SELECT Song FROM Users WHERE ID=" + str(id_song)
    cur.execute(sql)
    song = cur.fetchall()
    time_sleep = 0
    if song:
        if song[0][0] != None:
            file = MP3('music/'+song[0][0])
            time_sleep = file.info.length + 0.2
            return time_sleep, 'music/'+song[0][0]

bot.run(DISCORD_BOT_TOKEN)

