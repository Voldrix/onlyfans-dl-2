#!/usr/bin/env python3

import os
import sys
import json
import shutil
import pathlib
import requests
import hashlib
import argparse
from datetime import datetime, timedelta

requests.urllib3.disable_warnings()

from configurations import *
from globals import dynamic_rules

API_URL = "https://onlyfans.com/api2/v2"
new_files = 0
MAX_AGE = 0
LATEST = 0
API_HEADER = {
    "Accept": "application/json, text/plain, */*",
    "Accept-Encoding": "gzip, deflate",
    "app-token": "33d57ade8c02dbc5a333db99ff9ae26a",
    "User-Agent": USER_AGENT,
    "x-bc": X_BC,
    "user-id": USER_ID,
    "Cookie": "auh_id=" + USER_ID + "; sess=" + SESS_COOKIE,
}


def create_signed_headers(link, queryParams):
    global API_HEADER
    path = "/api2/v2" + link
    if queryParams:
        query = "&".join("=".join((key, val)) for (key, val) in queryParams.items())
        path = f"{path}?{query}"
    unixtime = str(int(datetime.now().timestamp()))
    msg = "\n".join([dynamic_rules["static_param"], unixtime, path, USER_ID])
    message = msg.encode("utf-8")
    hash_object = hashlib.sha1(message)
    sha_1_sign = hash_object.hexdigest()
    sha_1_b = sha_1_sign.encode("ascii")
    checksum = (
        sum([sha_1_b[number] for number in dynamic_rules["checksum_indexes"]])
        + dynamic_rules["checksum_constant"]
    )
    format = dynamic_rules["prefix"] + ":{}:{:x}:" + dynamic_rules["suffix"]
    API_HEADER["sign"] = format.format(sha_1_sign, abs(checksum))
    API_HEADER["time"] = unixtime
    return


def showAge(myStr):
    myStr = str(myStr)
    tmp = myStr.split(".")
    t = int(tmp[0])
    dt_obj = datetime.fromtimestamp(t)
    strOut = dt_obj.strftime("%Y-%m-%d")
    return strOut


def latest(profile):
    latest = "0"
    for dirpath, dirs, files in os.walk(profile):
        for f in files:
            if f.startswith("20"):
                latest = f if f > latest else latest
    return latest[:10]


def api_request(endpoint, apiType):
    posts_limit = 50
    age = ""
    getParams = {"limit": str(posts_limit), "order": "publish_date_asc"}
    if apiType == "messages":
        getParams["order"] = "desc"
    if apiType == "subscriptions":
        getParams["type"] = "active"
    if (
        MAX_AGE
        and apiType != "messages"
        and apiType != "purchased"
        and apiType != "subscriptions"
    ):  # Cannot be limited by age
        getParams["afterPublishTime"] = str(MAX_AGE) + ".000000"
        age = " age " + str(showAge(getParams["afterPublishTime"]))
        # Messages can only be limited by offset or last message ID. This requires its own separate function. TODO
    create_signed_headers(endpoint, getParams)
    if VERBOSITY >= 3:
        print(API_URL + endpoint + age)

    status = requests.get(API_URL + endpoint, headers=API_HEADER, params=getParams)
    if status.ok:
        list_base = status.json()
    else:
        return json.loads(
            '{"error":{"message":"http ' + str(status.status_code) + '"}}'
        )

    # Fixed the issue with the maximum limit of 50 posts by creating a kind of "pagination"
    if (len(list_base) >= posts_limit and apiType != "user-info") or (
        "hasMore" in list_base and list_base["hasMore"]
    ):
        if apiType == "messages":
            getParams["id"] = str(list_base["list"][len(list_base["list"]) - 1]["id"])
        elif apiType == "purchased" or apiType == "subscriptions":
            getParams["offset"] = str(posts_limit)
        else:
            getParams["afterPublishTime"] = list_base[len(list_base) - 1][
                "postedAtPrecise"
            ]
        while 1:
            create_signed_headers(endpoint, getParams)
            if VERBOSITY >= 3:
                print(API_URL + endpoint + age)
            status = requests.get(
                API_URL + endpoint, headers=API_HEADER, params=getParams
            )
            if status.ok:
                list_extend = status.json()
            if apiType == "messages":
                list_base["list"].extend(list_extend["list"])
                if (
                    list_extend["hasMore"] == False
                    or len(list_extend["list"]) < posts_limit
                    or not status.ok
                ):
                    break
                getParams["id"] = str(
                    list_base["list"][len(list_base["list"]) - 1]["id"]
                )
                continue
            list_base.extend(list_extend)  # Merge with previous posts
            if len(list_extend) < posts_limit:
                break
            if apiType == "purchased" or apiType == "subscriptions":
                getParams["offset"] = str(int(getParams["offset"]) + posts_limit)
            else:
                getParams["afterPublishTime"] = list_extend[len(list_extend) - 1][
                    "postedAtPrecise"
                ]
    return list_base


def get_user_info(profile):
    # <profile> = "me" -> info about yourself
    info = api_request("/users/" + profile, "user-info")
    if "error" in info:
        print(
            "\nFailed to get user: " + profile + "\n" + info["error"]["message"] + "\n"
        )
    return info


def get_subscriptions():
    subs = api_request("/subscriptions/subscribes", "subscriptions")
    if "error" in subs:
        print("\nSUBSCRIPTIONS ERROR: " + subs["error"]["message"])
        return
    return [row["username"] for row in subs]


def download_media(media, subtype, postdate, album="", profile_dir=None):
    if profile_dir is None:
        profile_dir = PROFILE
    filename = postdate + "_" + str(media["id"])

    if "source" in media:
        source = media["source"]["source"]
    elif "files" in media:
        if "full" in media["files"]:
            if media["files"]["full"]["url"] is not None:
                source = media["files"]["full"]["url"]
            else:
                source = media["files"]["preview"]["url"]
        elif "preview" in media:
            source = media["preview"]
        else:
            return
    else:
        return

    if source is None:
        return

    if (
        media["type"] != "photo"
        and media["type"] != "video"
        and media["type"] != "audio"
        and media["type"] != "gif"
    ) or not media["canView"]:
        return
    if (
        (media["type"] == "photo" and not PHOTOS)
        or (media["type"] == "video" and not VIDEOS)
        or (media["type"] == "audio" and not AUDIO)
    ):
        return

    # Ignore short videos if IGNORE_SHORT_VIDEOS is enabled
    if media["type"] == "video" and IGNORE_SHORT_VIDEOS:
        if "duration" in media and media["duration"] is not None:
            if media["duration"] < 60:
                if VERBOSITY >= 2:
                    print(
                        f"Skipping short video (duration: {media['duration']}s): {filename}"
                    )
                return

    extension = source.split("?")[0].split(".")[-1]
    ext = "." + extension
    if len(ext) < 3:
        return

    if ALBUMS and album and media["type"] == "photo":
        path = "/photos/" + postdate + "_" + album + "/" + filename + ext
    else:
        path = "/" + media["type"] + "s/" + filename + ext
    if USE_SUB_FOLDERS and subtype != "posts":
        path = "/" + subtype + path
    if not os.path.isdir(profile_dir + os.path.dirname(path)):
        pathlib.Path(profile_dir + os.path.dirname(path)).mkdir(
            parents=True, exist_ok=True
        )
    if not os.path.isfile(profile_dir + path):
        if VERBOSITY >= 2 or (MAX_AGE and VERBOSITY >= 1):
            print(profile_dir + path)
        global new_files
        new_files += 1
        try:
            r = requests.get(source, stream=True, timeout=(4, None), verify=False)
        except:
            print("Error getting: " + source + " (skipping)")
            return
        if r.status_code != 200:
            print(r.url + " :: " + str(r.status_code))
            return
        # Writing to a temp file while downloading, so if we interrupt
        # a file, we will not skip it but re-download it at next time.
        with open(profile_dir + path + ".part", "wb") as f:
            r.raw.decode_content = True
            shutil.copyfileobj(r.raw, f)
        r.close()
        # Downloading finished, remove temp file.
        shutil.move(profile_dir + path + ".part", profile_dir + path)
    else:
        if VERBOSITY >= 4:
            print(path + " ... already exists")


def get_content(MEDIATYPE, API_LOCATION, profile_dir=None):
    if profile_dir is None:
        profile_dir = PROFILE
    posts = api_request(API_LOCATION, MEDIATYPE)
    if "error" in posts:
        print("\nERROR: " + API_LOCATION + " :: " + posts["error"]["message"])
    if MEDIATYPE == "messages":
        posts = posts["list"]
    if len(posts) > 0:
        print("Found " + str(len(posts)) + " " + MEDIATYPE)
        for post in posts:
            if "media" not in post or (
                "canViewMedia" in post and not post["canViewMedia"]
            ):
                continue
            if MEDIATYPE == "purchased" and (
                "fromUser" not in post or post["fromUser"]["username"] != PROFILE
            ):
                continue  # Only get paid posts from PROFILE
            if "postedAt" in post:  # get post date
                postdate = str(post["postedAt"][:10])
            elif "createdAt" in post:
                postdate = str(post["createdAt"][:10])
            else:
                postdate = "1970-01-01"  # epoc failsafe if date is not present
            if len(post["media"]) > 1:  # Don't put single photo posts in a subfolder
                album = str(post["id"])  # album ID
            else:
                album = ""
            for media in post["media"]:
                if MEDIATYPE == "stories":
                    if media["createdAt"] is None:
                        postdate = str(media["id"])
                    else:
                        postdate = str(media["createdAt"][:10])
                if (
                    "source" in media
                    and "source" in media["source"]
                    and media["source"]["source"]
                    and ("canView" not in media or media["canView"])
                ) or ("files" in media and "canView" in media and media["canView"]):
                    download_media(media, MEDIATYPE, postdate, album, profile_dir)
        global new_files
        print("Downloaded " + str(new_files) + " new " + MEDIATYPE)
        new_files = 0


# ===========================
# MAIN
# ===========================

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="OnlyFans Downloader",
        epilog="Examples:\n"
               "  python onlyfans-dl.py                      # Download all subscribed profiles\n"
               "  python onlyfans-dl.py -a                   # Download all subscribed profiles (short form)\n"
               "  python onlyfans-dl.py username1 username2  # Download specific profiles\n"
               "  python onlyfans-dl.py -a --days 7          # Download all profiles from last 7 days\n"
               "  python onlyfans-dl.py -a --latest          # Download all with latest per profile\n"
               "  python onlyfans-dl.py -h                   # Show this help message",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "profiles", nargs="*", help="Profiles to download (leave empty or use -a/--all for all)"
    )
    parser.add_argument(
        "-a", "--all", action="store_true", help="Download all subscribed profiles (same as no arguments)"
    )
    parser.add_argument("--days", type=int, help="Download content newer than N days")
    parser.add_argument(
        "--latest", action="store_true", help="Use latest downloaded date per profile"
    )

    args = parser.parse_args()

    # Download all profiles if no specific profiles given or --all/-a is used
    if args.all or not args.profiles:
        PROFILE_LIST = get_subscriptions()
    else:
        PROFILE_LIST = args.profiles

    if args.days:
        MAX_AGE = int((datetime.today() - timedelta(args.days)).timestamp())

    LATEST = args.latest

    for PROFILE in PROFILE_LIST:
        if PROFILE in ByPass:
            continue

        # Combine DL_DIR with PROFILE path if DL_DIR is set
        profile_path = os.path.join(DL_DIR, PROFILE) if DL_DIR else PROFILE

        user = get_user_info(PROFILE)
        if "id" not in user:
            continue

        PROFILE_ID = str(user["id"])

        if LATEST:
            ld = latest(profile_path)
            if ld != "0":
                MAX_AGE = int(datetime.strptime(ld, "%Y-%m-%d").timestamp())

        if POSTS:
            get_content("posts", f"/users/{PROFILE_ID}/posts", profile_path)
        if ARCHIVED:
            get_content("archived", f"/users/{PROFILE_ID}/posts/archived", profile_path)
        if STORIES:
            get_content("stories", f"/users/{PROFILE_ID}/stories", profile_path)
        if MESSAGES:
            get_content("messages", f"/chats/{PROFILE_ID}/messages", profile_path)
        if PURCHASED:
            get_content("purchased", "/posts/paid", profile_path)
