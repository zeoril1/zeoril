# -*- coding: utf-8 -*-
import discord
import textwrap
import asyncio
import requests
import time
import json
from yandex_music.client import Client
from discord import FFmpegPCMAudio
from discord.utils import get
from io import BytesIO
from lxml import html
from PIL import Image, ImageDraw, ImageFilter,ImageFont

DISCORD_BOT_TOKEN = 'NjcyMTE5NzA1MjEyOTQ0Mzg1.XjG2QQ.vX9v5I-taWoAaBE-CfMEc1y3N0k'

HEADERS = {"X-API-Key":'d1a68787e89b4fd1a0f6a99dca645db7'}
 
base_url = "https://www.bungie.net"
xur_url = "https://www.bungie.net/Platform/Destiny2/Vendors/?components=402"

clientYA = Client.from_credentials('neprim1@yandex.ru', 'xthtp321pasha123') 
# Send the request and store the result in res:
print ("\n\n\nConnecting to Bungie: " + xur_url + "\n")
print ("Fetching data for: Xur's Inventory!")
res = requests.get(xur_url, headers=HEADERS)
with open("test.json", "r") as read_file:
    file_content = read_file.read()
    weapon = json.loads(file_content)
# Print the error status:
music_list=[]
client = discord.Client()

@client.event
async def on_ready():
    print('Logged in as')
    print(client.user.name)
    print(client.user.id)
    print('------')
@client.event
async def on_voice_state_update(member,before,after):
    if member.id == 193425328083828736:
        channel = member.voice.channel
        bot = await discord.VoiceChannel.connect(channel)
        source = FFmpegPCMAudio('music/Никита.mp3')
        bot.play(source)
        
@client.event
async def on_message(message):
    global music_list
    global voice_client
    if message.content.startswith('!xur'):
        Xur()
        await message.channel.send(file=discord.File('2.jpg'))
        
    if message.content.startswith('!pl'):
        s = message.content
        l = s.find('!')
        r = s.find(' ')
        searchMusic = s[:l] + s[r+1:]
        search = clientYA.search(text=searchMusic,type_='track',page=0)['tracks']['results'][0]
        name_music = 'music/'+search['title']+'.mp3'
        search.download(name_music)
        channel = message.author.voice.channel
        voice_client = get(client.voice_clients, guild=message.guild)
        if voice_client and voice_client.is_connected():
            if voice_client.is_playing():
                music_list.append(name_music)
        else:
            bot = await discord.VoiceChannel.connect(channel)
            source = FFmpegPCMAudio(name_music)
            if not bot.is_playing():
                play_music(bot,source)
                
    if message.content.startswith('!test'):
        global voice
        channel = message.author.voice.channel
        voice = get(client.voice_clients, guild=message.guild)

        if voice and voice.is_connected():
            await voice.move_to(channel)

        else:
            voice = await channel.connect()
            print(f'Bot connected to voice channel {channel}\n')

        voice.play(FFmpegPCMAudio('music/223.mp3'), after=lambda e: print(f'RPG music in {channel} has finished playing.'))
        voice.source = discord.PCMVolumeTransformer(voice.source)
        voice.source.volume = 1.00

def play_music(bot,source):
    global player
    player = bot.play(source,after=lambda e: play_next(bot,e))
    voice = get(client.voice_clients, guild=ctx.guild)
    print (voice)
    player.source = discord.PCMVolumeTransformer(player.source)
    
def play_next(bot,e):
    global music_list
    if len(music_list)>0:
        print (music_list)
        source = FFmpegPCMAudio(executable="D:/ffmpeg/bin/ffmpeg.exe",source=music_list[0])
        music_list.pop()
        play_music(bot, source)
        
    else:
        print('закончилось')

        
@client.event
async def on_member_join(member):
    for nameRole in member.roles:
        if nameRole.name != 'Бот':
            print (client.get_guild(394939677590945804).roles)
            role = discord.utils.get(client.get_guild(394939677590945804).roles, name = "Бот")
            await member.add_roles(role)

def Xur():   
    yp=228
    ys=140
    yt=250
    i=0
    im1 = Image.open('test.jpg')
    massage=[]
    print('[command]: xur ')
    jsonItemUrl = base_url+'/common/destiny2_content/json/ru/DestinyInventoryItemLiteDefinition-eba8280f-f7f5-483f-b95c-73106def620d.json'
    itemRes = requests.get(jsonItemUrl)
    '''for saleItem in res.json()['Response']['sales']['data']['2190858386']['saleItems']:
        itemHash = int(res.json()['Response']['sales']['data']['2190858386']['saleItems'][saleItem]['itemHash'])
        nameItem = itemRes.json()[str(itemHash)]['displayProperties']['name']
        imgItem = base_url+itemRes.json()[str(itemHash)]['displayProperties']['icon']
        await message.channel.send(str(nameItem)+ ' ' + str(imgItem))'''
    for saleItem in res.json()['Response']['sales']['data']['2190858386']['saleItems']:
        itemHash = res.json()['Response']['sales']['data']['2190858386']['saleItems'][saleItem]['itemHash']
        for id_w in weapon:
            if (int(id_w['id']) == int(itemHash)):
                response = requests.get("https://www.bungie.net"+id_w['icon'])
                im2 = Image.open(BytesIO(response.content))
                im1.paste(im2.resize((300,300)),(115,yp))
                draw = ImageDraw.Draw(im1)
                sale = res.json()['Response']['sales']['data']['2190858386']['saleItems'][saleItem]['costs'][0]['quantity']
                ytt = yt
                for line in textwrap.wrap(str(id_w['name']), width=10):
                    font = ImageFont.truetype("arial", 62)
                    draw.text((460, ytt), line,(0,0,0), font=font)
                    font = ImageFont.truetype("arial", 60)
                    draw.text((460, ytt), line,(149,191,255), font=font)
                    ytt += font.getsize(line)[1]
                font = ImageFont.truetype("arial", 72)
                draw.text((510, ys),str(sale),(0,0,0),font=font)
                font = ImageFont.truetype("arial", 70)
                draw.text((510, ys),str(sale),(149,191,255),font=font)
                '''font = ImageFont.truetype("18922.otf", 50)
                draw.text((460, yt),str(id_w['name']),(255,0,0),font=font)'''
                yp=yp+468
                ys=ys+468
                yt=yt+468
                break
    im1.save('2.jpg')

        
client.run(DISCORD_BOT_TOKEN)
