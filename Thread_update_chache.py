import schedule
import requests
import threading
import datetime
import discord
import sqlite3
import time
import json, os
from PIL import Image, ImageDraw, ImageFont
from io import BytesIO

list_h = []
list_w = []
list_t = []
list_we = []
list_prew = []
vendor_items = []
vendor_emoji = ""
name_items = []
vandors_idname = []
discord_hook_token = "https://discord.com/api/webhooks/865526515344212018/GJNKyPj9dAVLluVcA3_CZs49u52P64XLWCIa2C4t-xju0M36Uo-PQcTp_qst8XGK5xz1"
refresh_token = open("resources/token.txt", "r", encoding="utf8")

conn = sqlite3.connect('resources/discord.sqlite3', check_same_thread=False)
cur = conn.cursor()

def update_member(Name, Last_login):
    values = {'Name': Name, 'Last_login': Last_login}
    cur.execute("Select * from Users where Name_game=:Name",values)
    user = cur.fetchall()
    if not user:
        cur.execute("INSERT INTO Users (Name_game) VALUES (:Name);", values)
        conn.commit()
    cur.execute("UPDATE Users SET Last_login=:Last_login Where Name_game=:Name;", values)
    conn.commit()

def items_filler():
    global list_h, list_w, list_t, list_w, list_prew
    m = open("resources/manifest.json", "w", encoding="utf8")
    manifest = requests.get("https://www.bungie.net/Platform/Destiny2/Manifest/")
    m.write(manifest.text)  # записываем содержимое в файл; как видите - content запроса
    m.close()
    with open("resources/manifest.json", "r", encoding="utf8") as mf:
        manifest = json.load(mf)
    url_items = "https://www.bungie.net"+manifest['Response']['jsonWorldComponentContentPaths']['ru']['DestinyInventoryItemLiteDefinition']
    f = open("resources/Vendors/Items.json", "w", encoding="utf8")
    down_mani = requests.get(url_items)  # делаем запрос
    f.write(down_mani.text)  # записываем содержимое в файл; как видите - content запроса
    f.close()

    with open("resources/Vendors/Items.json", "r", encoding="utf8") as read_file:
        items = json.load(read_file)
    for id_w in items:
        try:
            sale = items[id_w]
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

def config_cookie():
    with open('resources/cookies.txt', 'r', encoding="utf8") as f:
        cookies_config=f.read()
    return (cookies_config)

def hot_cache():
    print("Заполнение кэша")
    global vandors_idname
    day = datetime.datetime.today().weekday()
    hour = datetime.datetime.now().hour
    for vendor_id in vandors_idname:
        if vendor_id[1] == 'Зур' and (day != 2 or day != 3):
            if (day == 1 and hour < 17) or (day == 4 and hour > 17) or day == 5 or day == 6 or day == 7:
                cache = get_vender_info(vendor_id)
                with open('resources/Vendors/' + vendor_id[0] + '.txt', 'w+', encoding="utf8") as f:
                    f.write(str(cache))
                    print(vendor_id[1] + " Готов")
            else:
                print('Зура нет')
        else:
            cache = get_vender_info(vendor_id)
            with open('resources/Vendors/' + vendor_id[0] + '.txt', 'w+', encoding="utf8") as f:
                f.write(str(cache))
            print(vendor_id[1] + " Готов")


def get_token(code_token, type_get_token):
    global token,refresh_token
    token_url = 'https://www.bungie.net/Platform/App/OAuth/Token/'
    autorization = "Basic MzcxNDg6Rlo4eDItdEFBZ2x4NjBXT1lPeUNBSXMyTTZHQ2ZHVVBMV1NDTVZrdVpBOA=="
    cookies_bungie = config_cookie()
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
    with open('resources/token.txt', 'w', encoding="utf8") as f:
        f.write(refresh_token)

def sch():
    schedule.every().hours.do(hot_cache)
    while True:
        schedule.run_pending()
        time.sleep(10)

def get_item_info(itemHash,sell_quantity,items_buy_cost, vendor_id):
    buy_items = []
    with open("resources/Vendors/Items.json", "r", encoding="utf8") as read_file:
        Items = json.load(read_file)
    x=0
    for id_w in Items:
        if int(id_w) == int(itemHash) and '2190858386' != str(vendor_id):
            item = Items[id_w]
            sell = str(item['displayProperties']['name'])
            sell = sell.replace('"',"")
        elif '2190858386' == str(vendor_id) and int(id_w) == int(itemHash):
            item = Items[id_w]
            sell = str(item['displayProperties']['name'])
        else:
            for buy_hash in items_buy_cost:
                if int(id_w) == int(buy_hash[0]):
                    item = Items[id_w]
                    buy_items.append([item['displayProperties']['name'],buy_hash[1]])
    return sell, sell_quantity, buy_items

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

def xur_img(vendor_items):
    items_filler()
    global list_h, list_w, list_t, list_we, yp, ys, yt
    im1 = Image.open('resources/Vendors/XUR.png')
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
    im1.save('resources/Vendors/XUR_result.png')
    print("Готово")

def get_vender_info(vendor_id):
    global vandors_idname
    vendor_items= []
    items_buy_cost=[]
    url = 'https://www.bungie.net/Platform/Destiny2/3/Profile/4611686018496871111/Character/2305843009565724374/Vendors/'+str(vendor_id[0])+'/?components=402,401'
    r = requests.get(
        url,
        headers={'X-API-Key': 'b55da1ccd2534f28b913020fe9a91001', 'Authorization': token})
    vendor_save = open("resources/Vendors/vendor.json", "w", encoding="utf8")
    vendor_save.write(r.text)  # записываем содержимое в файл; как видите - content запроса
    vendor_save.close()
    with open("resources/Vendors/vendor.json", "r", encoding="utf8") as vendor_data:
        vendor = json.load(vendor_data)
    cat_vendor = vendor['Response']['categories']['data']['categories']
    vendor = vendor['Response']['sales']['data']
    if 'Паук' == str(vendor_id[1]):
        cat_index = 4
    elif 'Банши-44' == str(vendor_id[1]):
        cat_index = 8
    elif 'Зур' == str(vendor_id[1]):
        cat_index = 0
    elif 'Ада-1' == str(vendor_id[1]):
        cat_index = 2
    for cat_id in cat_vendor:
        if int(cat_id['displayCategoryIndex']) == cat_index:
            for item_index in cat_id['itemIndexes']:
                items_buy_cost = []
                item = vendor[str(item_index)]
                for cost_items in item['costs']:
                    items_buy_cost.append([cost_items['itemHash'],cost_items['quantity']])
                info_items = get_item_info(item['itemHash'], item['quantity'], items_buy_cost, vendor_id)
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
    if 'Зур' != str(vendor_id[1]):
        #emb = build_message(vendor_id)
        print(vendor_items)
        return vendor_items
    else:
        xur_img(vendor_items)
        print('XUR')

def get_manifest():
    url = 'https://www.bungie.net/Platform/Destiny2/Manifest/'
    print (token)
    manifest = requests.get(
        url,
        headers={'X-API-Key': 'b55da1ccd2534f28b913020fe9a91001', 'Authorization': token})
    m = open("resources/manifest.json", "w", encoding="utf8")
    m.write(manifest.text)  # записываем содержимое в файл; как видите - content запроса
    m.close()

def get_vendors():
    with open("resources/manifest.json", "r", encoding="utf8") as vendors_url:
        vendors = json.load(vendors_url)
    vendors_url = vendors['Response']['jsonWorldComponentContentPaths']['ru']['DestinyVendorDefinition']
    url = 'https://www.bungie.net'+vendors_url
    vendors_data = requests.get(
        url,
        headers={'X-API-Key': 'b55da1ccd2534f28b913020fe9a91001', 'Authorization': token})
    m = open("resources/Vendors/vendors.json", "w", encoding="utf8")
    m.write(vendors_data.text)
    m.close()

def get_vendors_ids():
    with open("resources/Vendors/vendors.json", "r", encoding="utf8") as vendors_data:
        vendors = json.load(vendors_data)
    with open("resources/Vendors/Vendors_name.txt", "r", encoding="utf8") as f:
        vendors_names = f.read().splitlines()
    vendors_ids = open("resources/Vendors/Vendors_ids.txt", "w", encoding="utf8")
    for vendor in vendors:
        for vendor_name in vendors_names:
            if vendors[vendor]['displayProperties']['name'] == vendor_name and vendors[vendor]['vendorProgressionType'] == 0 and vendors[vendor]['enabled'] !=False:
                vandors_idname.append([vendor,vendor_name])
                vendors_ids.write(vendor+'\n')
    print(vandors_idname)
    vendors_ids.close()

get_token(refresh_token, 'refresh_token')
get_manifest()
get_vendors()
get_vendors_ids()
hot_cache()
thread = threading.Thread(target=sch)
thread.start()
