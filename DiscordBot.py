# -*- coding: utf-8 -*-
import discord
import schedule
import datetime
import requests
import threading
import gspread
import time
import json
import random
from discord import FFmpegPCMAudio, Emoji
from io import BytesIO
from mutagen.mp3 import MP3
from PIL import Image, ImageDraw, ImageFont
import ast
import os
cookies = []
token = ''

DISCORD_BOT_TOKEN = 'NjcyMTE5NzA1MjEyOTQ0Mzg1.XjG2QQ.vX9v5I-taWoAaBE-CfMEc1y3N0k'
Discord_webhook = "https://discord.com/api/webhooks/865537838279950366/PDHL8Y_Z_UatFOmCIm9K37ZzqqZOERc4tB-TBnCmAptk3czhl0QTImiN_3GLMWPyLwuH"

HEADERS = {"X-API-Key": 'd1a68787e89b4fd1a0f6a99dca645db7'}
 
base_url = "https://www.bungie.net"
xur_url = "https://www.bungie.net/Platform/Destiny2/Vendors/?components=402"

# Send the request and store the result in res:
print("\n\n\nConnecting to Bungie: " + base_url + "\n")
print("Fetching data for: Xur's Inventory!")
res = requests.get(xur_url, headers=HEADERS)
# Print the error status:
client = discord.Client()

music_welcome = []

global_xur = [('23.07.2021', '17:05')]


@client.event
async def on_ready():
    print('Logged in as')
    print(client.user.name)
    print(client.user.id)
    print('------')

@client.event
async def on_voice_state_update(member, before, after):
    global x
    if before.channel != after.channel and discord.voice_client is not None and after.channel is not None:
        x=1
        return_song = play_song(member.id)
        if return_song[0] > 0:
            bot = await discord.VoiceChannel.connect(member.voice.channel)
            bot.play(FFmpegPCMAudio(return_song[1]))
            time.sleep(return_song[0])
            x = 0
            await bot.disconnect()

@client.event
async def on_message(message):

    if message.content.startswith('!configupdate'):
        print('[command]: configupdate ')
        download_config_song()
        await message.channel.send('Конфиг обновлен')

    if message.content.startswith('!spider'):
        print('[command]: spider ')
        emb = build_message('863940356')
        await message.channel.send(embed=emb)

    if message.content.startswith('!banshe'):
        print('[command]: clovis ')
        emb = build_message('672118013')
        await message.channel.send(embed=emb)

    if message.content.startswith('!ada'):
        print('[command]: ada ')
        emb = build_message('350061650')
        await message.channel.send(embed=emb)

    if message.content.startswith('!xur'):
        print('[command]: xur ')
        await message.channel.send(file=discord.File('resources/Vendors/XUR_result.png'))

    if message.content.startswith('!roll'):
        print('[command]: roll ')
        chellenge_value = chellenge_roll()
        emb = discord.Embed(title=f'Оружие: {chellenge_value[0]} ({chellenge_value[1]}) ',
                            description=f'\n**Челлендж**:\n{chellenge_value[2]}',
                            colour=discord.Color.blue())

        await message.reply(embed=emb)

    if message.content.startswith('!vote'):
        print('[command]: vote ')
        emb = discord.Embed(title=f'Голосование за рейд',
                            description=':one: Хрустальный Чертог \n\n:two: Склеп Глубокого Камня \n\n:three: Сад Спасения \n\n:four: Последнее Желание',
                            colour=discord.Color.blue())

        mess = await message.channel.send(embed=emb)
        await mess.add_reaction('1️⃣')
        await mess.add_reaction('2️⃣')
        await mess.add_reaction('3️⃣')
        await mess.add_reaction('4️⃣')

    if message.content.startswith('!8 ball'):
        print('[command]: 8 ball ')
        ball = magic_ball()
        await message.channel.send(ball)

    if message.content.startswith('!update'):
        print('[command]: update ')
        list_con = message.content.split('|')
        status = chellenge_update(list_con)
        if status == 0:
            await message.channel.send('Для **' + list_con[1] + '** добавлено испытание **'+list_con[2]+'**')
        elif status == 1:
            await message.channel.send('**'+list_con[1] + '** не найден')

def play_song(id_song):
    global music_welcome
    time_sleep = 0
    for list_id in music_welcome:
        if int(list_id[0]) == id_song:
            download_music(list_id[1])
            file = MP3("music/song.mp3")
            time_sleep = file.info.length + 0.2
            break
    return (time_sleep, "music/song.mp3")

def download_music(music_id):
    song_url = "https://www.zeoril.ru/zaebala/"+music_id
    song = requests.get(song_url)
    with open('music/song.mp3', 'wb') as file:
        file.write(song.content)

def magic_ball():
    answer = ['Бесспорно', 'Предрешено', 'Никаких сомнений', 'Определённо да', 'Можешь быть уверен в этом',
              'Мне кажется — «да»', 'Вероятнее всего', 'Хорошие перспективы', 'Знаки говорят — «да»', 'Да',
              'Пока не ясно, попробуй снова', 'Спроси позже', 'Лучше не рассказывать', 'Сейчас нельзя предсказать', 'Сконцентрируйся и спроси опять',
              'Даже не думай', 'Мой ответ — «нет»', 'По моим данным — «нет»', 'Перспективы не очень хорошие', 'Весьма сомнительно']
    rand = random.randint(0,19)
    return answer[rand]

def chellenge_roll():
    gc = gspread.service_account('resources/config_google.json')
    wks = gc.open("Exotic").sheet1
    ran = random.randint(1, 87)
    weapon = wks.row_values(ran)[0]
    chellenge = wks.row_values(ran)[2]
    EngWeapon = wks.row_values(ran)[1]
    return (weapon,EngWeapon,chellenge)

def chellenge_update(list_con):
    try:
        gc = gspread.service_account('resources/config_google.json')
        wks = gc.open("Exotic").sheet1
        cell = wks.find(list_con[1])
        if wks.cell(cell.row,cell.col+2).value == 'Нет.':
            wks.update_cell(cell.row,cell.col+2,list_con[2])
        else:
            wks.update_cell(cell.row,cell.col+2,wks.cell(cell.row,cell.col+2).value+' ; '+list_con[2])
        return 0
    except gspread.exceptions.CellNotFound:
        return 1

def read_song():
    global music_welcome
    music_welcome = []
    with open('resources/welcome_song.txt', 'r') as f:
        for eachLine in f:
            a = eachLine
            a = a.split(',')
            for spl in a:
                b = spl.split(' ', maxsplit=1)
                music_welcome.append(b)

def download_config_song():
    global vendor_emoji
    song_url = "https://www.zeoril.ru/zaebala/welcome_song.txt"
    song_config = requests.get(song_url)
    with open('resources/welcome_song.txt', 'w') as f:
        f.write(song_config.text)

    with open('resources/emojis.json', 'r', encoding="utf8") as f:
        vendor_emoji = json.load(f)
    read_song()

def get_info():
    r = requests.get(
        'https://www.bungie.net/Platform/Destiny2/3/Profile/4611686018496871111/Character/2305843009565724374/Vendors/?components=400',
        headers={'X-API-Key': 'b55da1ccd2534f28b913020fe9a91001', 'Authorization': token})
    print(r.text)

def build_message(vendor_id):
    vendor_items = open('resources/Vendors/' + vendor_id + '.txt','r').read()
    vendor_items = ast.literal_eval(vendor_items)
    emb = discord.Embed()
    for item in vendor_items:
        buiyng = 'Стоимость:\n'
        for item_buy in item[2]:
            buiyng += str(item_buy[1])+' '+vendor_emoji[item_buy[0]]+'\n'
        if vendor_id == '350061650':
            emoji_buy = ''
        else:
            emoji_buy = vendor_emoji[item[0]]
        if item[1] != 1:
            emb.add_field(name=str(item[1]) + ' ' + item[0] + ' ' + emoji_buy,
                          value=buiyng+'\n--------------------', inline=True)
        else:
            emb.add_field(name=item[0] + ' ' + emoji_buy,
                          value=buiyng+'\n--------------------', inline=True)

    return emb

download_config_song()
client.run(DISCORD_BOT_TOKEN)
