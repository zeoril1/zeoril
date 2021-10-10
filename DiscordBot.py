# -*- coding: utf-8 -*-
import discord
import requests
import gspread
import logging
import time
from time import gmtime, strftime
import json, os
import random
from discord import FFmpegPCMAudio
from mutagen.mp3 import MP3
import ast
import sqlite3

logging.basicConfig(filename="resources/logs.txt", level=logging.INFO)

cookies = []
users = []
music_welcome = []
vendor_emoji = []
token = ''

intents = discord.Intents.default()
intents.members = True

client = discord.Client(intents=intents)

conn = sqlite3.connect('resources/discord.sqlite3', check_same_thread=False)
cur = conn.cursor()

DISCORD_BOT_TOKEN = 'NjcyMTE5NzA1MjEyOTQ0Mzg1.XjG2QQ.vX9v5I-taWoAaBE-CfMEc1y3N0k'
Discord_webhook = "https://discord.com/api/webhooks/865537838279950366/PDHL8Y_Z_UatFOmCIm9K37ZzqqZOERc4tB-TBnCmAptk3czhl0QTImiN_3GLMWPyLwuH"

HEADERS = {"X-API-Key": 'd1a68787e89b4fd1a0f6a99dca645db7'}

base_url = "https://www.bungie.net"
xur_url = "https://www.bungie.net/Platform/Destiny2/Vendors/?components=402"

# Send the request and store the result in res:
logging.info("Connecting to Bungie: " + base_url)
logging.info("Fetching data for: Xur's Inventory!")
res = requests.get(xur_url, headers=HEADERS)
# Print the error status:
client = discord.Client()

maps = ['Алтарь пламени', 'Аномалия', 'Павшее знамя', 'Пепелище', 'Котёл', 'Конвергенция', 'Мёртвые скалы', 'Далёкие берега',
'Бесконечная долина', 'Синий исход', 'Крепость', 'Фрагмент', 'Джавелин - 4', 'Центр города', 'Пассифика', 'Сияющие скалы',
'Ржавая земля', 'Сумеречная Брешь', 'Вдовий двор', 'Червеприбежище']

@client.event
async def on_ready():
    print('123')
    logging.info('Logged in as')
    logging.info(client.user.name)
    logging.info(client.user.id)
    logging.info('------')

@client.event
async def on_voice_state_update(member, before, after):
    if before.channel != after.channel and discord.voice_client is not None and after.channel is not None:
        return_song = play_song(member.id)
        if return_song[0] > 0:
            bot = await discord.VoiceChannel.connect(member.voice.channel)
            bot.play(FFmpegPCMAudio(return_song[1]))
            time.sleep(return_song[0])
            await bot.disconnect()

@client.event
async def on_message(message):
    if message.content.startswith('!configupdate'):
        logging.info('[command]: configupdate ')
        read_song()
        await message.channel.send('Конфиг обновлен')

    if message.content.startswith('!map'):
        logging.info('[command]: map ')
        map = map_random()
        await message.channel.send(map)

    if message.content.startswith('!reg'):
        logging.info('[command]: reg ')
        text = reg_users(message)
        await message.channel.send(text)

    if message.content.startswith('!spider'):
        logging.info('[command]: spider ')
        emb = build_message('863940356')
        await message.channel.send(embed=emb)

    if message.content.startswith('!banshe'):
        logging.info('[command]: clovis ')
        emb = build_message('672118013')
        await message.channel.send(embed=emb)

    if message.content.startswith('!ada'):
        logging.info('[command]: ada ')
        emb = build_message('350061650')
        await message.channel.send(embed=emb)

    if message.content.startswith('!xur'):
        logging.info('[command]: xur ')
        with open('resources/Vendors/XUR_result.png', 'rb') as f:
            picture = discord.File(f)
        await message.channel.send(file=picture)

    if message.content.startswith('!roll'):
        logging.info('[command]: roll ')
        chellenge_value = chellenge_roll()
        emb = discord.Embed(title=f'Оружие: {chellenge_value[0]} ({chellenge_value[1]}) ',
                            description=f'\n**Челлендж**:\n{chellenge_value[2]}',
                            colour=discord.Color.blue())

        await message.reply(embed=emb)

    if message.content.startswith('!vote'):
        logging.info('[command]: vote ')
        emb = discord.Embed(title=f'Голосование за рейд',
                            description=':one: Хрустальный Чертог \n\n:two: Склеп Глубокого Камня \n\n:three: Сад '
                                        'Спасения \n\n:four: Последнее Желание',
                            colour=discord.Color.blue())

        mess = await message.channel.send(embed=emb)
        await mess.add_reaction('1️⃣')
        await mess.add_reaction('2️⃣')
        await mess.add_reaction('3️⃣')
        await mess.add_reaction('4️⃣')

    if message.content.startswith('!8 ball'):
        logging.info('[command]: 8 ball ')
        ball = magic_ball()
        await message.channel.send(ball)

    if message.content.startswith('!update'):
        logging.info('[command]: update ')
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
            file = MP3(list_id[1])
            time_sleep = file.info.length + 0.2
            break
    return time_sleep, list_id[1]


def magic_ball():
    answer = ['Бесспорно', 'Предрешено', 'Никаких сомнений', 'Определённо да', 'Можешь быть уверен в этом',
              'Мне кажется — «да»', 'Вероятнее всего', 'Хорошие перспективы', 'Знаки говорят — «да»', 'Да',
              'Пока не ясно, попробуй снова', 'Спроси позже', 'Лучше не рассказывать', 'Сейчас нельзя предсказать',
              'Сконцентрируйся и спроси опять', 'Даже не думай', 'Мой ответ — «нет»', 'По моим данным — «нет»',
              'Перспективы не очень хорошие', 'Весьма сомнительно']
    rand = random.randint(0, 19)
    return answer[rand]


def chellenge_roll():
    gc = gspread.service_account('resources/config_google.json')
    wks = gc.open("Exotic").sheet1
    ran = random.randint(1, 87)
    weapon = wks.row_values(ran)[0]
    chellenge = wks.row_values(ran)[2]
    engweapon = wks.row_values(ran)[1]
    return weapon, engweapon, chellenge


def chellenge_update(list_con):
    try:
        gc = gspread.service_account('resources/config_google.json')
        wks = gc.open("Exotic").sheet1
        cell = wks.find(list_con[1])
        if wks.cell(cell.row, cell.col+2).value == 'Нет.':
            wks.update_cell(cell.row, cell.col+2, list_con[2])
        else:
            wks.update_cell(cell.row, cell.col+2, wks.cell(cell.row, cell.col+2).value+' ; '+list_con[2])
        return 0
    except gspread.exceptions.CellNotFound:
        return 1

def read_song():
    global music_welcome, vendor_emoji
    music_welcome = []
    with open('resources/emojis.json', 'r', encoding="utf8") as f:
        vendor_emoji = json.load(f)
    with open('resources/welcome_song.txt', 'r', encoding="utf8") as f:
        for eachLine in f:
            a = eachLine
            a = a.split(',')
            for spl in a:
                b = spl.split(' ', maxsplit=1)
                music_welcome.append(b)

def get_info():
    r = requests.get(
        'https://www.bungie.net/Platform/Destiny2/3/Profile/4611686018496871111/Character/2305843009565724374/Vendors/?components=400',
        headers={'X-API-Key': 'b55da1ccd2534f28b913020fe9a91001', 'Authorization': token})
    print(r.text)


def build_message(vendor_id):
    vendor_items = open('resources/Vendors/' + vendor_id + '.txt', 'r', encoding="utf8").read()
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

def reg_users(message):
    global users
    x=0
    id = message.author
    for member in users:
        if member[0] == id.id:
            x=1
            break
    if x==0:
        values = {'ID': id.id, 'Name': id.name, 'Song': 'None'}
        cur.execute("INSERT INTO Users (ID,Name,Song) VALUES (:ID, :Name, :Song)",values)
        conn.commit()
        update_member()
        text = 'Пользователь '+ id.name+ ' зарегистрирован'
    else:
        text = 'Пользователь '+ id.name+ ' уже зарегистрирован'
    return text

def map_random():
    global maps
    rand = random.randint(0,19)
    return maps[rand]

def update_member():
    global users
    cur.execute("SELECT * FROM Users;")
    users = cur.fetchall()
    print(users)

read_song()
update_member()
client.run(DISCORD_BOT_TOKEN)
