# -*- coding: utf-8 -*-
import discord
import textwrap
import schedule
import datetime
import requests
import threading
import gspread
import time
import json
import random
import yadisk
from discord import FFmpegPCMAudio
from io import BytesIO
from mutagen.mp3 import MP3
from PIL import Image, ImageDraw,ImageFont


DISCORD_BOT_TOKEN = 'NjcyMTE5NzA1MjEyOTQ0Mzg1.XjG2QQ.vX9v5I-taWoAaBE-CfMEc1y3N0k'
Discord_webhook = "https://discord.com/api/webhooks/865537838279950366/PDHL8Y_Z_UatFOmCIm9K37ZzqqZOERc4tB-TBnCmAptk3czhl0QTImiN_3GLMWPyLwuH"

HEADERS = {"X-API-Key":'d1a68787e89b4fd1a0f6a99dca645db7'}
 
base_url = "https://www.bungie.net"
xur_url = "https://www.bungie.net/Platform/Destiny2/Vendors/?components=402"

# Send the request and store the result in res:
print ("\n\n\nConnecting to Bungie: " + base_url + "\n")
print ("Fetching data for: Xur's Inventory!")
res = requests.get(xur_url, headers=HEADERS)
# Print the error status:
client = discord.Client()

list_h = []
list_w = []
list_t = []
list_we = []
list_prew = []
music_welcome = []
global_xur = [('16.07.2021', '19:05')]

@client.event
async def on_ready():
    print('Logged in as')
    print(client.user.name)
    print(client.user.id)
    print('------')

@client.event
async def on_voice_state_update(member,before,after):
    try:
        if before.channel!=after.channel and discord.voice_client is not None and after.channel is not None:
            return_song = play_song(member.id)
            if return_song[0] > 0:
                bot = await discord.VoiceChannel.connect(member.voice.channel)
                bot.play(FFmpegPCMAudio(return_song[1]))
                time.sleep(return_song[0])
                await bot.disconnect()
    except Exception:
        print(Exception)

@client.event
async def on_message(message):
    if message.content.startswith('!xur'):
        print('[command]: xur ')
        Xur()
        await message.channel.send(file=discord.File('resources/XUR_result.png'))

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
        x=0
        print('[command]: update ')
        list_con = message.content.split('|')
        status = chellenge_update(list_con)
        if status == 0:
            await message.channel.send('Для **' + list_con[1] +'** добавлено испытание **'+list_con[2]+'**')
        elif status == 1:
            await message.channel.send('**'+list_con[1] + '** не найден')

def play_song(id):
    global music_welcome
    time = 0
    for list_id in music_welcome:
        if int(list_id[0]) == id:
            file = MP3(list_id[1])
            time = file.info.length + 0.2
            break
    return (time,list_id[1])

def magic_ball():
    answer = ['Бесспорно', 'Предрешено', 'Никаких сомнений', 'Определённо да', 'Можешь быть уверен в этом',
              'Мне кажется — «да»', 'Вероятнее всего', 'Хорошие перспективы', 'Знаки говорят — «да»', 'Да',
              'Пока не ясно, попробуй снова', 'Спроси позже', 'Лучше не рассказывать', 'Сейчас нельзя предсказать', 'Сконцентрируйся и спроси опять',
              'Даже не думай', 'Мой ответ — «нет»', 'По моим данным — «нет»', 'Перспективы не очень хорошие', 'Весьма сомнительно']
    rand = random.randint(0,19)
    return answer[rand]

def Xur():
    print(3)
    items_filler()
    global list_h, list_w, list_t, list_we, yp, ys, yt
    i = 0
    x = 0
    selItems = res.json()['Response']['sales']['data']['2190858386']['saleItems']
    im1 = Image.open('resources/XUR.png')
    for saleItem in selItems:
        x=0
        itemHash = res.json()['Response']['sales']['data']['2190858386']['saleItems'][saleItem]['itemHash']
        if  itemHash != 2125848607 and itemHash != 3875551374:
            if x != 1 and x != 2 and x !=3:
                for item in list_h:
                    if int(item[0]) == int(itemHash):
                        yp = 228 + (468*2)
                        ys = 140 + (468*2)
                        yt = 250 + (468*2)
                        draw(item, saleItem, im1, yp, ys, yt)
                        x = 0
                        break
                    else:
                        x=1

            if x != 0 and x!=2 and x !=3:
                for item in list_w:
                    if int(item[0]) == int(itemHash):
                        yp = 228 + (468*3)
                        ys = 140 + (468*3)
                        yt = 250 + (468*3)
                        draw(item, saleItem,im1,yp,ys,yt)
                        x=1
                        break
                    else:
                        x=2

            if x != 0 and x != 1 and x !=3:
                for item in list_t:
                    if int(item[0]) == int(itemHash):
                        yp = 228 + 468
                        ys = 140 + 468
                        yt = 250 + 468
                        draw(item, saleItem, im1, yp, ys, yt)
                        x = 2
                        break
                    else:
                        x=3

            if x != 0 and x != 1 and x !=2:
                for item in list_we:
                    if int(item[0]) == int(itemHash):
                        yp = 228
                        ys = 140
                        yt = 250
                        draw(item, saleItem, im1, yp, ys, yt)
                        x=3
                        break
                    else:
                        x = 4
    im1.save('resources/XUR_result.png')

def draw(item, saleItem, im1, yp, ys, yt):
    loadIcon = requests.get("https://www.bungie.net" + item[2])
    im2 = Image.open(BytesIO(loadIcon.content))
    im1.paste(im2.resize((300, 300)), (115, yp))
    draw = ImageDraw.Draw(im1)
    sale = res.json()['Response']['sales']['data']['2190858386']['saleItems'][saleItem]['costs'][0]['quantity']
    ytt = yt
    for line in textwrap.wrap(str(item[1]), width=10):
        font = ImageFont.truetype("resources/18922.otf", 62)
        draw.text((460, ytt), line, (0, 0, 0), font=font)
        font = ImageFont.truetype("resources/18922.otf", 60)
        draw.text((460, ytt), line, (149, 191, 255), font=font)
        ytt += font.getsize(line)[1]
    font = ImageFont.truetype("resources/18922.otf", 72)
    draw.text((510, ys), str(sale), (0, 0, 0), font=font)
    font = ImageFont.truetype("resources/18922.otf", 70)
    draw.text((510, ys), str(sale), (149, 191, 255), font=font)

def items_filler():
    global list_h,list_w,list_t,list_w,list_prew
    m = open("resources/manifest.json", "w", encoding="utf8")
    manifest = requests.get("https://www.bungie.net/Platform/Destiny2/Manifest/")
    m.write(manifest.text)  # записываем содержимое в файл; как видите - content запроса
    m.close()
    with open("resources/manifest.json", "r", encoding="utf8") as mf:
        manifest = json.load(mf)
    url_items = "https://www.bungie.net"+manifest['Response']['jsonWorldComponentContentPaths']['ru']['DestinyInventoryItemLiteDefinition']
    f = open("resources/Items.json", "w", encoding="utf8")
    down_mani = requests.get(
        url_items)  # делаем запрос
    f.write(down_mani.text)  # записываем содержимое в файл; как видите - content запроса
    f.close()

    with open("resources/Items.json", "r", encoding="utf8") as read_file:
        Items = json.load(read_file)
    for id_w in Items:
        try:
            sale = Items[id_w]
            if sale['inventory']['tierTypeName'] == 'Экзотический':
                list_prew.append(id_w)
                list_prew.append(sale['displayProperties']['name'])
                list_prew.append(sale['displayProperties']['icon'])
                if sale['classType'] == 1:
                    list_h.append(list_prew)
                elif sale['classType'] == 2:
                    list_w.append(list_prew)
                elif sale['classType'] == 0:
                    list_t.append(list_prew)
                elif sale['classType'] == 3:
                    list_we.append(list_prew)
                list_prew = []
        except KeyError:
            x = 1
        else:
            y = 1

def auto_xur():
    global global_xur
    print(1)
    date = datetime.datetime.now().strftime("%d.%m.%Y %H:%M")
    for i in global_xur:
        runTime = i[0] + " " + i[1]
        if i and date == str(runTime):
            print(2)
            Xur()
            webhook = discord.Webhook.from_url(
                Discord_webhook,
                adapter=discord.RequestsWebhookAdapter())
            webhook.send(file=discord.File('resources/XUR_result.png'))

def sch():
    schedule.every().minutes.do(auto_xur)
    while True:
        schedule.run_pending()
        time.sleep(1)

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
    with open('resources/welcome_song.txt', 'r') as f:
        for eachLine in f:
            a = eachLine
            a = a.split(',')
            for spl in a:
                b = spl.split(' ', maxsplit=1)
                music_welcome.append(b)

def download_config():
    song_url = "https://www.zeoril.ru/zaebala/welcome_song.txt"
    song_config = requests.get(song_url)
    with open('resources/welcome_song.txt', 'w') as f:
        f.write(song_config.text)

thread = threading.Thread(target=sch)
thread.start()
download_config()
read_song()
client.run(DISCORD_BOT_TOKEN)
