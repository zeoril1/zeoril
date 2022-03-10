import requests
import json
import sqlite3
import datetime
import ast

global token

def update_token(code_token, type_get_token):
    global token
    token_url = 'https://www.bungie.net/Platform/App/OAuth/Token/'
    autorization = "Basic MzcxNDg6Rlo4eDItdEFBZ2x4NjBXT1lPeUNBSXMyTTZHQ2ZHVVBMV1NDTVZrdVpBOA=="

    with open('resources/cookies.txt', 'r', encoding="utf8") as f:
        cookies_bungie=f.read()

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
    with open('resources/token.txt', 'w', encoding="utf8") as f:
        f.write(refresh_token)

def get_manifest():
    update_token(open("resources/token.txt", "r", encoding="utf8"), 'refresh_token')
    url = 'https://www.bungie.net/Platform/Destiny2/Manifest/'
    manifest = requests.get(
        url,
        headers={'X-API-Key': 'b55da1ccd2534f28b913020fe9a91001', 'Authorization': token})
    m = open("resources/manifest.json", "w", encoding="utf8")
    m.write(manifest.text)  # записываем содержимое в файл; как видите - content запроса
    m.close()

def get_items():
    update_token(open("resources/token.txt", "r", encoding="utf8"), 'refresh_token')
    with open("resources/manifest.json", "r", encoding="utf8") as items_url:
        items = json.load(items_url)
    items_url = items['Response']['jsonWorldComponentContentPaths']['ru']['DestinyInventoryItemLiteDefinition']
    url = 'https://www.bungie.net' + items_url
    items_data = requests.get(
        url,
        headers={'X-API-Key': 'b55da1ccd2534f28b913020fe9a91001', 'Authorization': token})
    m = open("resources/Vendors/items.json", "w", encoding="utf8")
    m.write(items_data.text.replace("'"," "))
    m.close()
    with open("resources/Vendors/items.json", "r", encoding="utf8") as items:
        items = json.load(items)
    conn = sqlite3.connect('resources/discord.sqlite3', check_same_thread=False)
    cur = conn.cursor()
    for item in items:
        cur.execute('SELECT count(ID) FROM Items WHERE ID = '+item)
        index = cur.fetchall()[0][0]
        if items[item]['displayProperties']['name'] !="":
            if index <= 0:
                cur.execute(f"INSERT INTO Items (ID, Name) VALUES ("+item+",'"+items[item]['displayProperties']['name']+"');")
                conn.commit()
            else:
                cur.execute(f"UPDATE Vendors SET Name = '"+items[item]['displayProperties']['name']+"' WHERE ID = "+item+";")
                conn.commit()
    cur.close()

def insert_info():
    conn = sqlite3.connect('resources/discord.sqlite3', check_same_thread=False)
    cur = conn.cursor()
    update_token(open("resources/token.txt", "r", encoding="utf8"), 'refresh_token')
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
    with open("resources/Vendors/vendors.json", "r", encoding="utf8") as vendors:
        vendors = json.load(vendors)
    for vendor in vendors:
        if vendors[vendor]['enabled'] == True and vendors[vendor]["itemList"] and vendors[vendor]["displayCategories"]:
            values = {'ID': vendor, 'Name': vendors[vendor]["displayProperties"]["name"], 'Items': '"itemList":'+str(vendors[vendor]["itemList"]), 'Categories': str(vendors[vendor]["displayCategories"])}
            cur.execute(f'INSERT INTO Vendors (ID, Name, Items, Categories) VALUES (:ID,:Name,:Items,:Categories);', values)
            conn.commit()
    cur.close()

def get_vendors(name_vendor):
    conn = sqlite3.connect('resources/discord.sqlite3', check_same_thread=False)
    cur = conn.cursor()
    cur.execute("Select * from Vendors WHERE Name = '"+name_vendor+"'")
    vendors = cur.fetchall()
    for vendor in vendors:
        break
    if not vendor[3]:
        get_manifest()
        with open("resources/manifest.json", "r", encoding="utf8") as vendors_url:
            vendors = json.load(vendors_url)
        vendors_url = vendors['Response']['jsonWorldComponentContentPaths']['ru']['DestinyVendorDefinition']
        url = 'https://www.bungie.net' + vendors_url
        vendors_data = requests.get(
            url,
            headers={'X-API-Key': 'b55da1ccd2534f28b913020fe9a91001', 'Authorization': token})
        m = open("resources/Vendors/vendors.json", "w", encoding="utf8")
        m.write(vendors_data.text)
        m.close()
        with open("resources/Vendors/vendors.json", "r", encoding="utf8") as vendors:
            vendors = json.load(vendors)
        id = str(vendor[0])
        items = str(vendors[id]["itemList"]).replace("'", '"')
        items = items.replace("True", 'true')
        items = items.replace("False", 'false')
        Categories = str(vendors[id]["displayCategories"]).replace("'", '"')
        Categories = Categories.replace("True", 'true')
        Categories = Categories.replace("False", 'false')
        icon =str(vendors[id]["displayProperties"]["originalIcon"])
        values = {'ID': id, 'Items': '{"itemList":'+items+'}',
                  'Categories': '{"displayCategories":'+Categories+'}', 'Up_date': str(datetime.datetime.now())
                  , 'Icon': icon}
        cur.execute(f'UPDATE Vendors SET Items = :Items,Categories = :Categories, Up_date = :Up_date, Icon = :Icon WHERE ID = :ID', values)
        conn.commit()
        cur.close()
        print (vendor[1])

def get_vender_info(vendor_id):
    update_token(open("resources/token.txt", "r", encoding="utf8"), 'refresh_token')
    url = 'https://www.bungie.net/Platform/Destiny2/3/Profile/4611686018496871111/Character/2305843009565724374/Vendors/'+str(vendor_id)+'/?components=402,401'
    r = requests.get(
        url,
        headers={'X-API-Key': 'b55da1ccd2534f28b913020fe9a91001', 'Authorization': token})
    return r.text

