import schedule
import requests
import threading
import datetime
import discord
import time
import json
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
vendors_ids = []
discord_hook_token = "https://discord.com/api/webhooks/865526515344212018/GJNKyPj9dAVLluVcA3_CZs49u52P64XLWCIa2C4t-xju0M36Uo-PQcTp_qst8XGK5xz1"
refresh_token = 'CNiyAxKGAgAgTPqkAW/Q/jFA9CILmvKKkexfY1k5Mdt3ziztgOZShDDgAAAAqfJUVIrhhPayhelVM7LaDa3+uFFW/gwVKqPACYsewUojiliAuXDuci1tPHQUQK/pEt/kwxQJHdY3RxKFy2CtTVCZTRuWIAe1ooNtLNnVCAOdL9jKx9QkEBJkfM13ux/6kfKb2bNcR6kzhmXqfk9ybTT5pEL4rquB8udPNChwkPc/xRWk/FjNjO6NpOESY0LeGqKYd9eZqiK0wt/vLRv9/sl9rdVy8A/uYFwVf6DDN17jtrjgyHVrx82eSqNwP8fZ2JdpTutnEdng4+6g91fqY+2u0fnV1ZgwGdeBdckR4ic='


def items_filler():
    global list_h, list_w, list_t, list_w, list_prew
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


def download_config_cookie():
    cookies_url = "https://www.zeoril.ru/zaebala/cookie.txt"
    cookies_config = requests.get(cookies_url)
    with open('resources/cookies.txt', 'w', encoding="utf8") as f:
        f.write(cookies_config.text)
    return (cookies_config.text)


def hot_cache():
    print("Заполнение кэша")
    get_token(refresh_token, 'refresh_token')
    global vendors_ids
    day = datetime.datetime.today().weekday()
    hour = datetime.datetime.now().hour
    print(hour)
    for vendor_id in vendors_ids:
        if vendor_id == '2190858386' and (day != 2 or day != 3):
            if (day == 1 and hour > 17) or (day == 4 and hour < 17):
                x= 0
            else:
               cache= get_vender_info(vendor_id)
               print(cache)
        else:
            cache = get_vender_info(vendor_id)
            with open('resources/Vendors/' + vendor_id + '.txt', 'w+', encoding="utf8") as f:
                f.write(str(cache))
        print (vendor_id+" Готов")


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
    with open('resources/token.txt', 'w', encoding="utf8") as f:
        f.write(refresh_token)


def sch():
    schedule.every().hours.do(hot_cache)
    while True:
        schedule.run_pending()
        time.sleep(10)


def get_item_info(itemHash,sell_quantity,items_buy_cost, vendor_id):
    buy_items = []
    with open("resources/Items.json", "r", encoding="utf8") as read_file:
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
    elif '350061650' == str(vendor_id):
        cat_index = 1
    elif '350061651' == str(vendor_id):
        cat_index = 1
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
    if '2190858386' != str(vendor_id):
        #emb = build_message(vendor_id)
        return vendor_items
    else:
        xur_img(vendor_items)

def config():
    global name_items,vendors_ids
    x=0
    configs = open('resources/Vendors/config_vendors.txt', 'r', encoding="utf8").read()
    configs_split = configs.split("\n")
    for line in configs_split:
        name_config = line.split("=")
        name_config[0]=name_config[0].replace(" ", "")
        if name_config[0] == "name":
            config_prev = name_config[1].split(",")
            for form in config_prev:
                if x == 0:
                    one = form.replace("[","")
                    one = one.replace("]","")
                    one = one.replace('"', "")
                    x=1
                elif x == 1:
                    two = form.replace("[", "")
                    two = two.replace("]", "")
                    two = two.replace('"', "")
                    name_items.append([one,two])
                    x=0
        elif name_config[0] == "ids":
            config_prev = name_config[1].split(",")
            for form in config_prev:
                item = form.replace("[", "")
                item = item.replace("]", "")
                item = item.replace("'", "")
                vendors_ids.append(item)
    #vendor_items = ast.literal_eval(vendor_items)


config()
hot_cache()
thread = threading.Thread(target=sch)
thread.start()
