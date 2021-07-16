# -*- coding: utf-8 -*-
import discord
import textwrap
import schedule
import datetime
import asyncio
import requests
import threading
import time
import json
from discord import FFmpegPCMAudio
from io import BytesIO
import random
import xlrd,xlwt
from xlutils.copy import copy
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
music_welcome = [[284610292095123456,"music/Dungeon master.mp3"],[209443383385522176,"music/RIP EARS ORGASM.mp3"],
                 [217236953324584960,"music/Boy next door.mp3"],[400709228270059531,"music/Fucking slaves get your ass back here.mp3"],
                 [193425328083828736,"music/Stick your finger in my ass.mp3"],[196682643767689218,"music/FUCK YOU.mp3"],
                 [310730616926896128,"music/Fisting is 300 $.mp3"],[478605922285912074,"music/Do you like watching me.mp3"],
                 [306678386800066562,"music/WOO.mp3"]]
global_xur = [('16.07.2021', '17:05')]

@client.event
async def on_ready():
    print('Logged in as')
    print(client.user.name)
    print(client.user.id)
    print('------')

@client.event
async def on_voice_state_update(member,before,after):
    try:
        if before.channel!=after.channel and discord.voice_client is not None:
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
    global music_list
    if message.content.startswith('!xur'):
        print('[command]: xur ')
        Xur()
        await message.channel.send(file=discord.File('resources/XUR_result.png'))

    if message.content.startswith('!roll'):
        print('[command]: roll ')
        author = message.author

        exot = xlrd.open_workbook('resources/exotic.xls', formatting_info=True)

        sheet = exot.sheet_by_index(0)
        ran = random.randint(1, 87)
        weapon = sheet.row_values(ran)[0]
        chellenge = sheet.row_values(ran)[2]
        EngWeapon = sheet.row_values(ran)[1]

        emb = discord.Embed(title=f'Оружие: {weapon} ({EngWeapon}) ',
                            description=f'\n**Челлендж**:\n{chellenge}',
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
        list = message.content.split('|')
        exot = xlrd.open_workbook('resources/exotic.xls', formatting_info=True)
        sheet = exot.sheet_by_index(0)
        wb = copy(exot)
        sheet_w = wb.get_sheet(0)
        ran = random.randint(1, 87)
        for quest in sheet:
            x=x+1
            if quest[0].value == list[1]:
                if quest[2].value != 'Нет.':
                    text=quest[2].value+';'+list[2]
                else:
                    text =list[2]
                sheet_w.write(x-1,2,text)
                wb.save('resources/exotic.xls')
                break
        '''weapon = sheet.row_values(ran)[0]
        chellenge = sheet.row_values(ran)[2]
        EngWeapon = sheet.row_values(ran)[1]'''
        await message.channel.send('Для' + list[1] +' добавлено испытание '+list[2])

def play_song(id):
    global music_welcome
    time = 0
    for list_id in music_welcome:
        if list_id[0] == id:
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
    print(item[0])
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
    date = datetime.datetime.now().strftime("%d.%m.%Y %H:%M")
    for i in global_xur:
        runTime = i[0] + " " + i[1]
        if i and date == str(runTime):
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

thread = threading.Thread(target=sch)
thread.start()
items_filler()
client.run(DISCORD_BOT_TOKEN)
