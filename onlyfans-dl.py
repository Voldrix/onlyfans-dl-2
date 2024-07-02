#!/usr/bin/env python3

import os
import sys
import json
import shutil
import pathlib
import requests
import hashlib
import aiohttp
import asyncio
from datetime import datetime, timedelta
from config import *

requests.urllib3.disable_warnings()

API_URL = "https://onlyfans.com/api2/v2"
new_files = 0
MAX_AGE = 0
LATEST = 0

# Static dynamic rules
dynamic_rules = {
    "static_param": "RPnq8UadKceN7JNbeh2ApmUxM0A2nU9y",
    "start": "24650",
    "end": "666078a0",
    "checksum_constant": 13,
    "checksum_indexes": [4, 5, 7, 9, 9, 11, 13, 17, 18, 19, 23, 23, 23, 24, 25, 26, 27, 27, 28, 28, 28, 28, 28, 29, 30, 32, 32, 33, 33, 34, 34, 38],
    "app_token": "33d57ade8c02dbc5a333db99ff9ae26a",
    "remove_headers": ["user_id"],
    "revision": "202404181902-08205f45c3",
    "is_current": 0,
    "format": "24650:{}:{:x}:666078a0",
    "prefix": "24650",
    "suffix": "666078a0"
}

API_HEADER = {
    "Accept": "application/json, text/plain, */*",
    "Accept-Encoding": "gzip, deflate",
    "app-token": "33d57ade8c02dbc5a333db99ff9ae26a",
    "User-Agent": USER_AGENT,
    "x-bc": X_BC,
    "user-id": USER_ID,
    "Cookie": f"auh_id={USER_ID}; sess={SESS_COOKIE}"
}

def create_signed_headers(link, queryParams):
    global API_HEADER
    path = f"/api2/v2{link}"
    if queryParams:
        query = '&'.join('='.join((key, val)) for (key, val) in queryParams.items())
        path = f"{path}?{query}"
    unixtime = str(int(datetime.now().timestamp()))
    msg = "\n".join([dynamic_rules["static_param"], unixtime, path, USER_ID])
    message = msg.encode("utf-8")
    hash_object = hashlib.sha1(message)
    sha_1_sign = hash_object.hexdigest()
    sha_1_b = sha_1_sign.encode("ascii")
    checksum = sum([sha_1_b[number] for number in dynamic_rules["checksum_indexes"]]) + dynamic_rules["checksum_constant"]
    format = f'{dynamic_rules["prefix"]}:{{}}:{abs(checksum):x}:{dynamic_rules["suffix"]}'
    API_HEADER["sign"] = format.format(sha_1_sign)
    API_HEADER["time"] = unixtime
    return

def show_age(timestamp):
    timestamp = str(timestamp)
    tmp = timestamp.split('.')
    t = int(tmp[0])
    dt_obj = datetime.fromtimestamp(t)
    return dt_obj.strftime("%Y-%m-%d")

def latest(profile):
    latest_date = "0"
    for dirpath, dirs, files in os.walk(profile):
        for f in files:
            if f.startswith('20'):
                latest_date = f if f > latest_date else latest_date
    return latest_date[:10]

def api_request(endpoint, apiType):
    posts_limit = 50
    age = ''
    getParams = {"limit": str(posts_limit), "order": "publish_date_asc"}
    if apiType == 'messages':
        getParams['order'] = "desc"
    if apiType == 'subscriptions':
        getParams['type'] = 'active'
    if MAX_AGE and apiType not in ['messages', 'purchased', 'subscriptions']:
        getParams['afterPublishTime'] = str(MAX_AGE) + ".000000"
        age = f" age {show_age(getParams['afterPublishTime'])}"
    create_signed_headers(endpoint, getParams)
    if VERBOSITY >= 3:
        print(f"{API_URL}{endpoint}{age}")

    status = requests.get(API_URL + endpoint, headers=API_HEADER, params=getParams)
    if status.ok:
        list_base = status.json()
    else:
        print(f"Error {status.status_code}: {status.text}")
        return {"error": {"message": f"http {status.status_code}"}}

    if (len(list_base) >= posts_limit and apiType != 'user-info') or ('hasMore' in list_base and list_base['hasMore']):
        if apiType == 'messages':
            getParams['id'] = str(list_base['list'][-1]['id'])
        elif apiType in ['purchased', 'subscriptions']:
            getParams['offset'] = str(posts_limit)
        else:
            getParams['afterPublishTime'] = list_base[-1]['postedAtPrecise']
        while True:
            create_signed_headers(endpoint, getParams)
            if VERBOSITY >= 3:
                print(f"{API_URL}{endpoint}{age}")
            status = requests.get(API_URL + endpoint, headers=API_HEADER, params=getParams)
            if status.ok:
                list_extend = status.json()
            else:
                print(f"Error {status.status_code}: {status.text}")
                break
            if apiType == 'messages':
                list_base['list'].extend(list_extend['list'])
                if not list_extend.get('hasMore') or len(list_extend['list']) < posts_limit or not status.ok:
                    break
                getParams['id'] = str(list_base['list'][-1]['id'])
                continue
            list_base.extend(list_extend)
            if len(list_extend) < posts_limit:
                break
            if apiType in ['purchased', 'subscriptions']:
                getParams['offset'] = str(int(getParams['offset']) + posts_limit)
            else:
                getParams['afterPublishTime'] = list_extend[-1]['postedAtPrecise']
    return list_base

def get_user_info(profile):
    info = api_request(f"/users/{profile}", 'user-info')
    if "error" in info:
        print(f"\nFailed to get user: {profile}\n{info['error']['message']}\n")
    return info

def get_subscriptions():
    subs = api_request("/subscriptions/subscribes", "subscriptions")
    if "error" in subs:
        print(f"\nSUBSCRIPTIONS ERROR: {subs['error']['message']}")
        return []
    return [row['username'] for row in subs]

async def download_file(session, url, dest_path):
    temp_path = f"{os.path.dirname(dest_path)}/bad-{os.path.basename(dest_path)}.temp"
    async with session.get(url) as response:
        if response.status != 200:
            return False
        with open(temp_path, 'wb') as f:
            while True:
                chunk = await response.content.read(1024)
                if not chunk:
                    break
                f.write(chunk)
    # Проверяем существование временного файла перед переименованием
    if os.path.exists(temp_path):
        os.rename(temp_path, dest_path)
    else:
        print(f"Temp file {temp_path} not found. Unable to rename.")
    return True


async def download_media(media, subtype, postdate, album=''):
    filename = f"{postdate}_{media['id']}"
    if subtype == "stories":
        source = media["files"]["source"]["url"]
    else:
        source = media["source"]["source"]
        if not source:
            if "preview" in media["files"]:
                source = media["files"]["preview"]["url"]
            elif "preview" in media:
                source = media["preview"]

    if media["type"] not in ["photo", "video", "audio", "gif"] or not media['canView']:
        return
    if (media["type"] == "photo" and not PHOTOS) or (media["type"] == "video" and not VIDEOS) or (media["type"] == "audio" and not AUDIO):
        return

    extension = source.split('?')[0].split('.')[-1]
    ext = f".{extension}"
    if len(ext) < 3:
        return

    if ALBUMS and album and media["type"] == "photo":
        path = f"/photos/{postdate}_{album}/{filename}{ext}"
    else:
        path = f"/{media['type']}s/{filename}{ext}"
    if USE_SUB_FOLDERS and subtype != "posts":
        path = f"/{subtype}{path}"
    if not os.path.isdir(PROFILE + os.path.dirname(path)):
        pathlib.Path(PROFILE + os.path.dirname(path)).mkdir(parents=True, exist_ok=True)
    if not os.path.isfile(PROFILE + path):
        if VERBOSITY >= 2 or (MAX_AGE and VERBOSITY >= 1):
            print(PROFILE + path)
        global new_files
        new_files += 1

        async with aiohttp.ClientSession() as session:
            await download_file(session, source, PROFILE + path)

    else:
        if VERBOSITY >= 4:
            print(path + ' ... already exists')

async def get_content(MEDIATYPE, API_LOCATION):
    posts = api_request(API_LOCATION, MEDIATYPE)
    if "error" in posts:
        print(f"\nERROR: {API_LOCATION} :: {posts['error']['message']}")
        return
    if MEDIATYPE == "messages":
        posts = posts['list']
    if len(posts) > 0:
        print(f"Found {len(posts)} {MEDIATYPE}")
        tasks = []
        semaphore = asyncio.Semaphore(MAX_PARALLEL_DOWNLOADS)  # Ограничение на количество параллельных задач
        for post in posts:
            if "media" not in post or ("canViewMedia" in post and not post["canViewMedia"]):
                continue
            if MEDIATYPE == "purchased" and ('fromUser' not in post or post["fromUser"]["username"] != PROFILE):
                continue
            if 'postedAt' in post:
                postdate = post["postedAt"][:10]
            elif 'createdAt' in post:
                postdate = post["createdAt"][:10]
            else:
                postdate = "1970-01-01"
            album = str(post["id"]) if len(post["media"]) > 1 else ""
            for media in post["media"]:
                if MEDIATYPE == "stories":
                    postdate = media["createdAt"][:10]
                if "source" in media and "source" in media["source"] and media["source"]["source"] and ("canView" not in media or media["canView"]) or "files" in media:
                    tasks.append(download_media_with_semaphore(semaphore, media, MEDIATYPE, postdate, album))
        await asyncio.gather(*tasks)
        global new_files
        print(f"Downloaded {new_files} new {MEDIATYPE}")
        new_files = 0

async def download_media_with_semaphore(semaphore, media, MEDIATYPE, postdate, album):
    async with semaphore:
        await download_media(media, MEDIATYPE, postdate, album)

def delete_temp_files(profile):
    for dirpath, dirs, files in os.walk(profile):
        for file in files:
            if file.startswith('bad-') and file.endswith('.temp'):
                os.remove(os.path.join(dirpath, file))

def print_usage():
    print("\nUsage: onlyfans-dl.py <list of profiles / all> <max age (optional)>\n")
    print("max age must be an integer. number of days back from today.\n")
    print("if max age = 0, the script will find the latest date amongst the files for each profile independently.\n")
    print("Make sure to update the session variables at the top of this script (See readme).\n")
    print("Update Browser User Agent (Every time it updates): https://ipchicken.com/\n")
    print("Use --list to output a list of active subscriptions.\n")
    print("Use -n <number> to select a profile from the list by number.\n")
    print("Use --help to display this text.\n")
    exit()

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print_usage()

    if "--help" in sys.argv:
        print_usage()

    if "--list" in sys.argv:
        subscriptions = get_subscriptions()
        with open("subscriptions_list.txt", "w") as f:
            for idx, sub in enumerate(subscriptions, start=1):
                print(f"{idx}. {sub}")
                f.write(f"{sub}\n")
        exit()

    if DL_DIR:
        try:
            os.chdir(DL_DIR)
        except:
            print('Unable to use DIR: ' + DL_DIR)
    print("CWD = " + os.getcwd())

    PROFILE_LIST = sys.argv
    PROFILE_LIST.pop(0)

    if "-n" in PROFILE_LIST:
        index = PROFILE_LIST.index("-n") + 1
        try:
            with open("subscriptions_list.txt", "r") as f:
                subscriptions = f.readlines()
            PROFILE = subscriptions[int(PROFILE_LIST[index]) - 1].strip()
            PROFILE_LIST = [PROFILE]
        except (IndexError, FileNotFoundError):
            print("Invalid index or subscriptions list not found.")
            exit()

    if PROFILE_LIST[-1] == "0":
        LATEST = 1
        PROFILE_LIST.pop(-1)
    if len(PROFILE_LIST) > 1 and PROFILE_LIST[-1].isnumeric():
        MAX_AGE = int((datetime.today() - timedelta(int(PROFILE_LIST.pop(-1)))).timestamp())
        print("\nGetting posts newer than " + str(datetime.utcfromtimestamp(int(MAX_AGE))) + " UTC")

    if PROFILE_LIST[0] == "all":
        PROFILE_LIST = get_subscriptions()

    loop = asyncio.get_event_loop()

    for PROFILE in PROFILE_LIST:
        if PROFILE in ByPass:
            if VERBOSITY > 0:
                print("skipping " + PROFILE)
            continue
        user_info = get_user_info(PROFILE)

        if "id" in user_info:
            PROFILE_ID = str(user_info["id"])
        else:
            continue

        if LATEST:
            latestDate = latest(PROFILE)
            if latestDate != "0":
                MAX_AGE = int(datetime.strptime(latestDate + ' 00:00:00', '%Y-%m-%d %H:%M:%S').timestamp())
                print("\nGetting posts newer than " + latestDate + " 00:00:00 UTC")

        if os.path.isdir(PROFILE):
            print(f"\n{PROFILE} exists.\nDownloading new media, skipping pre-existing.")
            delete_temp_files(PROFILE)  # Удаление временных файлов перед началом загрузки
        else:
            print(f"\nDownloading content to {PROFILE}")

        tasks = []

        if POSTS:
            tasks.append(get_content("posts", f"/users/{PROFILE_ID}/posts"))
        if ARCHIVED:
            tasks.append(get_content("archived", f"/users/{PROFILE_ID}/posts/archived"))
        if STORIES:
            tasks.append(get_content("stories", f"/users/{PROFILE_ID}/stories"))
        if MESSAGES:
            tasks.append(get_content("messages", f"/chats/{PROFILE_ID}/messages"))
        if PURCHASED:
            tasks.append(get_content("purchased", f"/posts/paid"))

        loop.run_until_complete(asyncio.gather(*tasks))
