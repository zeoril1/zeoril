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
from discord import FFmpegPCMAudio, Emoji
from io import BytesIO
from mutagen.mp3 import MP3
from PIL import Image, ImageDraw, ImageFont
import os
cookies = []
token = ''
refresh_token = 'CIGxAxKGAgAgybmnpVgnk2m56Plyd8/cx+CJgGJt/tj1jycxt6o0+ObgAAAAbm6POKQPcIrqwaNM3s/Mixpuz0LSHnrsI7TsmnfZaKqCBgn85Qt3TNMQEUjN8kobe9UuIb6KI3WMQhtkV9iLXHlMJNoA82eToXCZw2epDOiiX6gw1DKKVfIitYJfkTO9RAuOyzk66MDaIbB7LDKWtpVJ+tQ2xN9sdLRIVmvmirIFUyWZY98OeiZQ/a++UVdk2iaV74nrDgWURBpsFkM8H3hdq5dFGzy8tvXVsSW44Jz82ymDDrGT6d3uAOq38+gfBXLUAaLcuG97SbzlwW6MYCwFSUomWyQlu6c6WE2PxGg='

DISCORD_BOT_TOKEN = 'NjcyMTE5NzA1MjEyOTQ0Mzg1.XjG2QQ.vX9v5I-taWoAaBE-CfMEc1y3N0k'
Discord_webhook = "https://discord.com/api/webhooks/865537838279950366/PDHL8Y_Z_UatFOmCIm9K37ZzqqZOERc4tB-TBnCmAptk3czhl0QTImiN_3GLMWPyLwuH"
discord_hook_token = "https://discord.com/api/webhooks/865526515344212018/GJNKyPj9dAVLluVcA3_CZs49u52P64XLWCIa2C4t-xju0M36Uo-PQcTp_qst8XGK5xz1"

HEADERS = {"X-API-Key": 'd1a68787e89b4fd1a0f6a99dca645db7'}
 
base_url = "https://www.bungie.net"
xur_url = "https://www.bungie.net/Platform/Destiny2/Vendors/?components=402"

# Send the request and store the result in res:
print("\n\n\nConnecting to Bungie: " + base_url + "\n")
print("Fetching data for: Xur's Inventory!")
res = requests.get(xur_url, headers=HEADERS)
# Print the error status:
client = discord.Client()

list_h = []
list_w = []
list_t = []
list_we = []
list_prew = []
music_welcome = []
vendor_items = []
vendor_emoji =""
global_xur = [('23.07.2021', '17:05')]
name_items = [["улучшающие призмы","Улучшающая призма"],["улучшающие ядра","Улучшающее ядро"],["блеск","Блеск"],
              ["датасети","Датасеть"],["барионную ветвь","Барионная ветвь"],["гелиевые нити","Гелиевые нити"],
              ["листья из кругометалла","Листья из кругометалла"]]

@client.event
async def on_ready():
    print('Logged in as')
    print(client.user.name)
    print(client.user.id)
    print('------')

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
        print('[command]: configupdate ')
        download_config_song()
        await message.channel.send('Конфиг обновлен')

    if message.content.startswith('!spider'):
        print('[command]: spider ')
        emb = get_vender_info('863940356')
        await message.channel.send(embed=emb)

    if message.content.startswith('!clovis'):
        print('[command]: clovis ')
        emb = get_vender_info('672118013')
        await message.channel.send(embed=emb)

    if message.content.startswith('!xur'):
        print('[command]: xur ')
        get_vender_info('2190858386')
        await message.channel.send(file=discord.File('resources/XUR_result.png'))
        '''print('[command]: xur ')
        Xur()
        await message.channel.send(file=discord.File('resources/XUR_result.png'))'''

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

def draw(item, cost, im1, yp, ys, yt):
    loadIcon = requests.get("https://www.bungie.net" + item[1])
    im2 = Image.open(BytesIO(loadIcon.content))
    im1.paste(im2.resize((284, 303)), (116, yp))
    draw = ImageDraw.Draw(im1)
    text = item[0].split(' ')
    for line in text:
        font = ImageFont.truetype("resources/18922.otf", 62)
        draw.text((460, yt), line, (0, 0, 0), font=font)
        font = ImageFont.truetype("resources/18922.otf", 60)
        draw.text((460, yt), line, (149, 191, 255), font=font)
        yt += font.getsize(line)[1]
    font = ImageFont.truetype("resources/18922.otf", 72)
    draw.text((510, ys), str(cost[1]), (0, 0, 0), font=font)
    font = ImageFont.truetype("resources/18922.otf", 70)
    draw.text((510, ys), str(cost[1]), (149, 191, 255), font=font)

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
            #Xur()
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

def download_config_cookie():
    cookies_url = "https://www.zeoril.ru/zaebala/cookie.txt"
    cookies_config = requests.get(cookies_url)
    with open('resources/cookies.txt', 'w') as f:
        f.write(cookies_config.text)
    return (cookies_config.text)

def get_info():
    r = requests.get(
        'https://www.bungie.net/Platform/Destiny2/3/Profile/4611686018496871111/Character/2305843009565724374/Vendors/?components=400',
        headers={'X-API-Key': 'b55da1ccd2534f28b913020fe9a91001', 'Authorization': token})
    print(r.text)

def xur_img(vendor_items):
    items_filler()
    global list_h, list_w, list_t, list_we, yp, ys, yt
    im1 = Image.open('resources/XUR.png')
    for item in vendor_items:
        info = []
        x=0
        if x == 0:
            for item_list in list_h:
                if item[0] == item_list[0]:
                    yp = 228 + (468 * 2)
                    ys = 140 + (468 * 2)
                    yt = 250 + (468 * 2)
                    info.append(item[0])
                    info.append(item_list[1])
                    draw(info, item[2][0], im1, yp, ys, yt)
                    x=0
                    break
                else:
                    x = 1
        if x == 1:
            for item_list in list_w:
                if item[0] == item_list[0]:
                    yp = 228 + (468 * 3)
                    ys = 140 + (468 * 3)
                    yt = 250 + (468 * 3)
                    info.append(item[0])
                    info.append(item_list[1])
                    draw(info, item[2][0], im1, yp, ys, yt)
                    x = 1
                    break
                else:
                    x = 2
        if x == 2:
            for item_list in list_t:
                if item[0] == item_list[0]:
                    yp = 227 + 468
                    ys = 140 + 468
                    yt = 250 + 468
                    info.append(item[0])
                    info.append(item_list[1])
                    draw(info, item[2][0], im1, yp, ys, yt)
                    x = 2
                    break
                else:
                    x = 3
        if x == 3 and item[0] != 'Экзотическая энграмма':
            for item_list in list_we:
                if item[0] == item_list[0]:
                    yp = 227
                    ys = 140
                    yt = 250
                    info.append(item[0])
                    info.append(item_list[1])
                    draw(info, item[2][0], im1, yp, ys, yt)
                    x=3
                    break
                else:
                    x = 4
        if x == 4:
            print (item[0]+' не найдено')
    im1.save('resources/XUR_result.png')
    print("Готово")

def get_vender_info(vendor_id):
    global vendor_items
    vendor_items=[]
    items_buy_cost=[]
    r = requests.get(
        'https://www.bungie.net/Platform/Destiny2/3/Profile/4611686018496871111/Character/2305843009565724374/Vendors/'+str(vendor_id)+'/?components=402,401',
        headers={'X-API-Key': 'b55da1ccd2534f28b913020fe9a91001', 'Authorization': token})
    vendor_save = open("resources/vendor.json", "w", encoding="utf8")
    vendor_save.write(r.text)  # записываем содержимое в файл; как видите - content запроса
    vendor_save.close()
    with open("resources/vendor.json", "r", encoding="utf8") as vendor_data:
        vendor = json.load(vendor_data)
    cat_vendor = vendor['Response']['categories']['data']['categories']
    vendor = vendor['Response']['sales']['data']
    if '863940356' == str(vendor_id):
        cat_index = 3
    elif '672118013' == str(vendor_id):
        cat_index = 8
    elif '2190858386' == str(vendor_id):
        cat_index = 0
    for cat_id in cat_vendor:
        if int(cat_id['displayCategoryIndex']) == cat_index:
            for item_index in cat_id['itemIndexes']:
                items_buy_cost = []
                item = vendor[str(item_index)]
                for cost_items in item['costs']:
                    items_buy_cost.append([cost_items['itemHash'],cost_items['quantity']])
                info_items = get_item_info(item['itemHash'], item['quantity'],items_buy_cost)
                if int(str(info_items[0]).find("Купить ")) != -1:
                    re = info_items[0]
                    re = re.replace("Купить ", "")
                    for name in name_items:
                        if name[0] == re:
                            re = name[1]
                else:
                    re = info_items[0]
                vendor_items.append([re, info_items[1], info_items[2]])
            break
    if '2190858386' != str(vendor_id):
        emb = build_message()
        return emb
    else:
        xur_img(vendor_items)

def get_item_info(itemHash,sell_quantity,items_buy_cost):
    buy_items = []
    with open("resources/Items.json", "r", encoding="utf8") as read_file:
        Items = json.load(read_file)
    x=0
    for id_w in Items:
        if int(id_w) == int(itemHash):
            item = Items[id_w]
            sell = item['displayProperties']['name']
        else:
            for buy_hash in items_buy_cost:
                if int(id_w) == int(buy_hash[0]):
                    item = Items[id_w]
                    buy_items.append([item['displayProperties']['name'],buy_hash[1]])
    return sell,sell_quantity,buy_items

def build_message():
    emb = discord.Embed()
    for item in vendor_items:
        buiyng = 'Стоимость: '
        print(item[0])
        for item_buy in item[2]:
            buiyng += str(item_buy[1])+' '+vendor_emoji[item_buy[0]]+'\n'
        emoji_buy = vendor_emoji[item[0]]
        if item[2] != 1:
            emb.add_field(name=str(item[1]) + ' ' + item[0] + ' ' + emoji_buy,
                          value=buiyng, inline=True)
        else:
            emb.add_field(name=item[0] + ' ' + emoji_buy,
                          value=buiyng, inline=True)
    return emb

def get_token(code_token,type_get_token):
    global token,refresh_token
    token_url = 'https://www.bungie.net/Platform/App/OAuth/Token/'
    autorization = "Basic MzcxNDg6Rlo4eDItdEFBZ2x4NjBXT1lPeUNBSXMyTTZHQ2ZHVVBMV1NDTVZrdVpBOA=="
    cookies_bungie = download_config_cookie()
    r = requests.post(token_url, headers={
        'Authorization': autorization,
        'Content-Type': 'application/x-www-form-urlencoded', 'cookie': cookies_bungie},
                      data={'grant_type': type_get_token, 'refresh_token': code_token})

    token = str(r.text)
    token = token.split(':')
    refresh_token = token[4].replace('"', "")
    refresh_token = refresh_token.split(',')
    refresh_token = refresh_token[0]
    token = token[1].replace('"', "")
    token = token.split(',')
    token = token[0]
    token = 'Bearer ' + token
    print(token)
    webhook = discord.Webhook.from_url(
        discord_hook_token,
        adapter=discord.RequestsWebhookAdapter())
    webhook.send(refresh_token)
    with open('resources/token.txt', 'w') as f:
        f.write(refresh_token)

thread = threading.Thread(target=sch)
thread.start()
get_token(refresh_token,'refresh_token')
download_config_song()
#get_vender_info('2190858386')
client.run(DISCORD_BOT_TOKEN)
