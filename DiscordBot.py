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

intents = discord.Intents.default()
intents.members = True
intents.messages = True
client = discord.Client(intents=intents)

conn = sqlite3.connect('resources/discord.sqlite3', check_same_thread=False)
cur = conn.cursor()
cur.execute("SELECT * FROM Configs WHERE ID=1;")
configs = cur.fetchall()

DISCORD_BOT_TOKEN = configs[0][1]
Discord_webhook = "https://discord.com/api/webhooks/943063839015067690/OftJxg_MMHlgssbNvQCpaVL8YbpX5eVqAswVv8-MA317XgpSxincSeY-f_9iRB_E1Ro8"
HEADERS = {"X-API-Key": str(configs[0][2])}
base_url = configs[0][3]
xur_url = configs[0][4]

# Send the request and store the result in res:
logging.info("Connecting to Bungie: " + base_url)
logging.info("Fetching data for: Xur's Inventory!")
res = requests.get(xur_url, headers=HEADERS)
# Print the error status:

maps = ['Алтарь пламени', 'Аномалия', 'Павшее знамя', 'Пепелище', 'Котёл', 'Конвергенция', 'Мёртвые скалы', 'Далёкие берега',
'Бесконечная долина', 'Синий исход', 'Крепость', 'Фрагмент', 'Джавелин - 4', 'Центр города', 'Пассифика', 'Сияющие скалы',
'Ржавая земля', 'Сумеречная Брешь', 'Вдовий двор', 'Червеприбежище']

@client.event
async def on_ready():
    logging.info('Logged in as')
    logging.info(client.user.name)
    logging.info(client.user.id)
    logging.info('------')

@client.event
async def on_member_join(member):
    values = {'Name': member.display_name, 'ID': member.id}
    cur.execute("Select * from Users where Name_discord=:Name OR ID=:ID", values)
    user = cur.fetchall()
    if not user:
        cur.execute("INSERT INTO Users (ID,Name_discord) VALUES (:ID,:Name);", values)
        conn.commit()

@client.event
async def on_member_remove(member):
    async with aiohttp.ClientSession() as session:
        webhook = discord.Webhook.from_url(Discord_webhook, adapter=discord.AsyncWebhookAdapter(session))
        Text = member.display_name+' покинул нас, Милорд'
        await webhook.send(Text)

@client.event
async def on_voice_state_update(member, before, after):
    if member.id != 672119705212944385:
        return_song = play_song(member.id)
        if return_song != None and before.channel != after.channel and after.channel is not None:
            voice = discord.utils.get(client.voice_clients, guild=member.guild)
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

@client.event
async def on_message(message):
    if message.content.startswith('!usersupdate'):
        logging.info('[command]: usersupdate ')
        update_member()
        await message.channel.send('Пользователи обновлены')

    if message.content.startswith('!configupdate'):
        logging.info('[command]: configupdate ')
        config()
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

    else:
        sql = "INSERT INTO Messages (ID,ID_user,Date, ID_channel) VALUES (" + str(message.id) + ", " + str(message.author.id) + ", '" + str(message.created_at) + "', " + str(message.channel.id) + ");"
        cur.execute(sql)
        conn.commit()

@client.event
async def on_raw_message_delete(message):
    sql = "SELECT COUNT(*) FROM Messages WHERE ID=" + str(message.message_id)
    cur.execute(sql)
    count = cur.fetchall()
    if int(count[0][0]) > 0:
        sql = "DELETE FROM Messages WHERE ID = " + str(message.message_id)
        cur.execute(sql)
        conn.commit()

def play_song(id_song):
    sql = "SELECT Song FROM Users WHERE ID=" + str(id_song)
    cur.execute(sql)
    song = cur.fetchall()
    time_sleep = 0
    if song[0][0] != None:
        file = MP3('music/'+song[0][0])
        time_sleep = file.info.length + 0.2
        return time_sleep, 'music/'+song[0][0]


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

def config():
    global vendor_emoji
    with open('resources/emojis.json', 'r', encoding="utf8") as f:
        vendor_emoji = json.load(f)

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

def map_random():
    global maps
    rand = random.randint(0,19)
    return maps[rand]

def get_members():
    global members_destiny
    url = "https://www.bungie.net/Platform/GroupV2/4075707/members"
    members = requests.get(url, headers={'X-API-Key': 'b55da1ccd2534f28b913020fe9a91001', 'Authorization': token})
    members_save = open("resources/members.json", "w", encoding="utf8")
    members_save.write(members.text)  # записываем содержимое в файл; как видите - content запроса
    members_save.close()
    with open("resources/members.json", "r", encoding="utf8") as members_data:
        members = json.load(members_data)
    for member in members['Response']['results']:
        date = datetime.datetime.utcfromtimestamp(int(member['lastOnlineStatusChange']))
        members_destiny.append([member['destinyUserInfo']['displayName'], date])

def update_member():
    global members_destiny
    get_members()
    for member in client.get_all_members():
        if not member.bot:
            values = {'Name': member.display_name, 'ID': member.id}
            cur.execute("Select * from Users where Name_discord=:Name OR ID=:ID", values)
            user = cur.fetchall()
            if not user:
                cur.execute("INSERT INTO Users (ID,Name_discord) VALUES (:ID,:Name);", values)
                conn.commit()
        for user in members_destiny:
            user_name = '%'+user[0]+'%'
            values = {'Name': user_name, 'Last_login': user[1],'Name_game':user[0]}
            cur.execute("Select * from Users where Name_discord LIKE :Name", values)
            member = cur.fetchall()
            if member:
                cur.execute("UPDATE Users SET Last_login=:Last_login, Name_game=:Name_game WHERE ID = "+str(member[0][0]), values)
                conn.commit()
                print(str(member[0][0])+' '+str(user[0]))

config()
client.run(DISCORD_BOT_TOKEN)

