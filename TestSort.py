import json
import requests

list_h = []
list_w = []
list_t = []
list_prew = []

f=open("response.json","w", encoding="utf8")
down_mani = requests.get("https://www.bungie.net/common/destiny2_content/json/ru/DestinyInventoryItemLiteDefinition-1a7d8d39-ca62-40af-becd-98bca27ed617.json") #делаем запрос
f.write(down_mani.text) #записываем содержимое в файл; как видите - content запроса
f.close()

with open("response.json", "r", encoding="utf8") as read_file:
    Items = json.load(read_file)
for id_w in Items:
    try:
        sale = Items[id_w]
        if sale['inventory']['tierTypeName'] == 'Экзотический':
            list_prew.append(str(sale['loreHash']))
            list_prew.append(sale['displayProperties']['name'])
            list_prew.append(sale['displayProperties']['icon'])
            if sale['classType'] == 1:
                list_h.append(list_prew)
            elif sale['classType'] == 2:
                list_w.append(list_prew)
            elif sale['classType'] == 0:
                list_t.append(list_prew)
            list_prew = []
    except KeyError:
        x=1
    else:
        y=1
print (list_h[0])
print (list_w[0])
print (list_t[0])