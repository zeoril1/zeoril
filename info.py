import discord
import json
import requests
refresh_token = open("resources/token.txt", "r", encoding="utf8")

members_destiny =[]
url = "https://www.bungie.net/Platform/GroupV2/4075707/members"
members = requests.get(url, headers={'X-API-Key': 'b55da1ccd2534f28b913020fe9a91001', 'Authorization': str(refresh_token)})
members_save = open("resources/members.json", "w", encoding="utf8")
members_save.write(members.text)  # записываем содержимое в файл; как видите - content запроса
members_save.close()
with open("resources/members.json", "r", encoding="utf8") as members_data:
    members = json.load(members_data)
for member in members['Response']['results']:
    print (member)
    members_destiny.append([member['destinyUserInfo']['membershipType'], member['destinyUserInfo']['membershipId'], member['destinyUserInfo']['displayName']])
print(members_destiny)