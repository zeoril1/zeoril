# -*- coding: utf-8 -*-
import discord
from discord import FFmpegPCMAudio
from PIL import Image, ImageDraw, ImageFont
import logging
import time
import json, os
import random
from mutagen.mp3 import MP3
import sqlite3
import aiohttp
import bungieapi
import asyncio
import requests
from io import BytesIO

logging.basicConfig(filename="resources/logs.txt", level=logging.INFO)

cookies = []
users = []
vendor_emoji = []
members_destiny =[]

bot = discord.Bot()
math = bot.create_group("math", "Commands related to mathematics.")  # create a slash command group

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

async def slow_func(channel, send=None, delay=1):
    await asyncio.sleep(delay)
    if send is None:
        send = channel.send
    await send('some text')

@bot.slash_command(name="atc", guild_ids=[394939677590945804])
async def atc(ctx, delay:int=1):
    await ctx.defer()
    await slow_func(ctx.channel, send=ctx.followup.send, delay=delay)

async def build_vendors(ID,ctx, delay):
    vendor_full=[]
    vendor_len=[]
    bungieapi.get_vendors(ID[1])
    cur.execute("Select Categories,icon from Vendors WHERE ID =" + str(ID[0]))
    full = cur.fetchall()[0]
    x = full[0]
    icon = full[1]
    Categories = json.loads(x)
    vendor = bungieapi.get_vender_info(ID[0])
    vendor = json.loads(vendor)
    with open("resources/Vendors/Items.json", "r", encoding="utf8") as items:
        items = json.load(items)
    x=0
    for cat in vendor['Response']['categories']['data']['categories']:
        items_vendor = []
        index_cat = str(cat['displayCategoryIndex'])
        for catname in Categories['displayCategories']:
            if str(catname['index']) == index_cat:
                x += 1
                name_cat = catname['displayProperties']['name']
                break
        for index in cat['itemIndexes']:
            id_item=vendor['Response']['sales']['data'][str(index)]['itemHash']
            items_vendor.append([items[str(id_item)]['displayProperties']['name'], items[str(id_item)]['displayProperties']['icon']])
        vendor_full.append([name_cat,items_vendor])
        vendor_len.append(len(items_vendor))

    x = 30
    y = 180
    x1 = 100
    y1 = 100
    x2=0
    for cat in vendor_full:
        y=y+42
        i=0
        for item in cat[1]:
            i=i+1
            if i == 6:
                i = 1
                y = y + y1 + 30
                x=30
            x=x+x1+30
            if x >x2:
                x2 = x
        x=30
        y = y + y1 + 30
    img = Image.new('RGBA', (x2, y), 'white')
    draw = ImageDraw.Draw(img)
    draw.rectangle(xy=[(0, 0), (x2, 180)], fill="#027ae3")
    draw.rectangle(xy=[(0, 0), (30, 180)], fill="#065396")
    fnt = ImageFont.truetype(font="resources/18922.otf", size=172, encoding='UTF-8')
    draw.text(xy=(30, -56), text='HG', font=fnt, fill="#0000ff")
    fnt = ImageFont.truetype(font="resources/18922.otf", size=72, encoding='UTF-8')
    draw.text(xy=(30,90), text=ID[1], font=fnt, fill="#000000")
    fnt = ImageFont.truetype(font="resources/18922.otf", size=32, encoding='UTF-8')
    x = 30
    y = 180
    x1 = 100
    y1 = 100
    for cat in vendor_full:
        draw.text(xy=(x,y), text=cat[0], font=fnt, fill="#000000")
        y=y+42
        i = 0
        for item in cat[1]:
            i = i + 1
            if i == 6:
                i = 1
                y = y + y1 + 30
                x = 30
            url = 'https://www.bungie.net' + str(item[1])
            image = requests.get(url)
            im1 = Image.open(BytesIO(image.content))
            draw.rectangle(xy=[(x, y), (x+x1, y+y1)], fill="#000000", width=5, outline="#008cff")
            img.paste(im1.resize((x1-10,y1-10)),(x+5,y+5))
            x=x+x1+30
        x=30
        y=y+y1+30
    img.save('resources/Vendors/vendor.png')
    picture = discord.File('resources/Vendors/vendor.png')
    await ctx.respond(file=picture)

async def get_vendors(ctx: discord.AutocompleteContext):
    vendor_names = []
    cur.execute("Select Name from Vendors WHERE Enable != false")
    vendors_name = cur.fetchall()
    for vender in vendors_name:
        vendor_names.append(str(vender[0]))
    return vendor_names

@property
def respond(self):
    return self.interaction.response.send_message

@bot.event
async def on_ready():
    print(f"We have logged in as {bot.user}")

@bot.slash_command(guild_ids=[394939677590945804,294888360600666112], name=f"map", description=f"Заролить карту")
async def map(ctx):
    map = map_random()
    await ctx.respond(map)

@bot.slash_command(guild_ids=[394939677590945804, 294888360600666112], name=f"stats", description=f"Статистика сообщений на сервере")
async def message(ctx):
    emb = stats_message(ctx)
    await ctx.respond(embed=emb)

@math.command(guild_ids=[394939677590945804])  # create a slash command
async def add(ctx, num1: int, num2: int):
    """Get the sum of 2 integers."""
    await ctx.respond(f"The sum of these numbers is **{num1+num2}**")


@bot.slash_command(guild_ids=[394939677590945804])
async def venders(ctx: discord.ApplicationContext,vender: Option(str, "Выберите торговца", autocomplete=get_vendors)):
    cur.execute("Select ID,Name from Vendors WHERE Name ='"+str(vender)+"'")
    x = cur.fetchall()[0]
    await ctx.defer()
    await build_vendors(x,ctx, delay=10)


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

@bot.event
async def on_member_join(member):
    values = {'Name': member.display_name, 'ID': member.id}
    cur.execute("Select * from Users where Name_discord=:Name OR ID=:ID", values)
    user = cur.fetchall()
    if not user:
        cur.execute("INSERT INTO Users (ID,Name_discord) VALUES (:ID,:Name);", values)
        conn.commit()

@bot.event
async def on_member_remove(member):
    async with aiohttp.ClientSession() as session:
        webhook = discord.Webhook.from_url(Discord_webhook, adapter=discord.AsyncWebhookAdapter(session))
        Text = member.display_name+' покинул нас, Милорд'
        await webhook.send(Text)

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

def map_random():
    global maps
    rand = random.randint(0,19)
    return maps[rand]

def stats_message(member):
    cur.execute("Select count(*) from Messages WHERE ID_user = "+str(member.author.id))
    members = cur.fetchall()
    emb = discord.Embed()
    if members:
        emb.add_field(name=str(member.author),value='Вы написали: '+str(members[0][0])+' сообщений\n--------------------', inline=True)
        return emb
    else:
        emb.add_field(name=str(member.author), value='Вы написали: 0 сообщений\n--------------------', inline=True)
        return emb

def start():
    bot.run(DISCORD_BOT_TOKEN)

start()
