#!/usr/bin/env python3

######################
# ASYNC IMPORTS      #
######################
import os
import sys
import json
import shutil
import pathlib
import hashlib
import asyncio
import aiohttp
from datetime import datetime, timedelta
from aiohttp import ClientTimeout
from typing import List, Dict, Any, Optional

# Disable warnings for requests (leave for backward compatibility)
import requests
requests.urllib3.disable_warnings()
######################
# END ASYNC IMPORTS  #
######################


######################
# CONFIGURATIONS     #
######################
from config import *
######################
# END CONFIGURATIONS #
######################

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
	"Cookie": "auh_id=" + USER_ID + "; sess=" + SESS_COOKIE
}

######################
# ASYNC SESSION      #
######################
# Global aiohttp session
session: Optional[aiohttp.ClientSession] = None

async def init_session():
	global session
	timeout = ClientTimeout(total=30, connect=10)
	session = aiohttp.ClientSession(timeout=timeout)

async def close_session():
	if session:
		await session.close()
######################
# END ASYNC SESSION  #
######################

def create_signed_headers(link, queryParams):
	global API_HEADER
	path = "/api2/v2" + link
	if queryParams:
		query = '&'.join('='.join((key,val)) for (key,val) in queryParams.items())
		path = f"{path}?{query}"
	unixtime = str(int(datetime.now().timestamp()))
	msg = "\n".join([dynamic_rules["static_param"], unixtime, path, USER_ID])
	message = msg.encode("utf-8")
	hash_object = hashlib.sha1(message)
	sha_1_sign = hash_object.hexdigest()
	sha_1_b = sha_1_sign.encode("ascii")
	checksum = sum([sha_1_b[number] for number in dynamic_rules["checksum_indexes"]])+dynamic_rules["checksum_constant"]
	format = dynamic_rules["prefix"] + ":{}:{:x}:" + dynamic_rules["suffix"]
	API_HEADER["sign"] = format.format(sha_1_sign, abs(checksum))
	API_HEADER["time"] = unixtime
	return

def showAge(myStr):
	myStr = str(myStr)
	tmp = myStr.split('.')
	t = int(tmp[0])
	dt_obj = datetime.fromtimestamp(t)
	strOut = dt_obj.strftime("%Y-%m-%d")
	return(strOut)

def latest(profile):
	latest = "0";
	for dirpath, dirs, files in os.walk(profile):
		for f in files:
			if f.startswith('20'):
				latest = f if f > latest else latest
	return latest[:10]

######################
# ASYNC API REQUEST  #
######################
async def api_request(endpoint: str, apiType: str) -> Dict[str, Any]:
	posts_limit = 50
	age = ''
	getParams = {"limit": str(posts_limit), "order": "publish_date_asc"}
	if apiType == 'messages':
		getParams['order'] = "desc"
	if apiType == 'subscriptions':
		getParams['type'] = 'active'
	if MAX_AGE and apiType not in ['messages', 'purchased', 'subscriptions']:
		getParams['afterPublishTime'] = f"{MAX_AGE}.000000"
		age = f" age {showAge(getParams['afterPublishTime'])}"

	create_signed_headers(endpoint, getParams)
	if VERBOSITY >= 3:
		print(API_URL + endpoint + age)

	try:
		async with session.get(API_URL + endpoint, headers=API_HEADER, params=getParams, ssl=False) as response:
			if response.status == 200:
				list_base = await response.json()
			else:
				return {"error": {"message": f"http {response.status}"}}

		if (len(list_base) >= posts_limit and apiType != 'user-info') or ('hasMore' in list_base and list_base['hasMore']):
			if apiType == 'messages':
				getParams['id'] = str(list_base['list'][len(list_base['list'])-1]['id'])
			elif apiType in ['purchased', 'subscriptions']:
				getParams['offset'] = str(posts_limit)
			else:
				getParams['afterPublishTime'] = list_base[len(list_base)-1]['postedAtPrecise']

			while True:
				create_signed_headers(endpoint, getParams)
				if VERBOSITY >= 3:
					print(API_URL + endpoint + age)

				async with session.get(API_URL + endpoint, headers=API_HEADER, params=getParams, ssl=False) as response:
					if response.status == 200:
						list_extend = await response.json()
					else:
						break

				if apiType == 'messages':
					list_base['list'].extend(list_extend['list'])
					if not list_extend['hasMore'] or len(list_extend['list']) < posts_limit:
						break
					getParams['id'] = str(list_base['list'][len(list_base['list'])-1]['id'])
					continue

				list_base.extend(list_extend)
				if len(list_extend) < posts_limit:
					break

				if apiType in ['purchased', 'subscriptions']:
					getParams['offset'] = str(int(getParams['offset']) + posts_limit)
				else:
					getParams['afterPublishTime'] = list_extend[len(list_extend)-1]['postedAtPrecise']

		return list_base
	except Exception as e:
		return {"error": {"message": str(e)}}
######################
# END ASYNC REQUEST  #
######################

######################
# ASYNC DOWNLOAD     #
######################
async def download_media(media: Dict[str, Any], subtype: str, postdate: str, album: str = '') -> None:
	filename = f"{postdate}_{media['id']}"

	if "source" in media:
		source = media["source"]["source"]
	elif "files" in media:
		if "full" in media["files"]:
			source = media["files"]["full"]["url"] if media["files"]["full"]["url"] else media["files"]["preview"]["url"]
		elif "preview" in media:
			source = media["preview"]
		else:
			return
	else:
		return

	if not source or not media.get('canView'):
		return

	if media["type"] not in ["photo", "video", "audio", "gif"]:
		return

	if (media["type"] == "photo" and not PHOTOS) or \
	   (media["type"] == "video" and not VIDEOS) or \
	   (media["type"] == "audio" and not AUDIO):
		return

	extension = source.split('?')[0].split('.')[-1]
	ext = f'.{extension}'
	if len(ext) < 3:
		return

	if ALBUMS and album and media["type"] == "photo":
		path = f"/photos/{postdate}_{album}/{filename}{ext}"
	else:
		path = f"/{media['type']}s/{filename}{ext}"

	if USE_SUB_FOLDERS and subtype != "posts":
		path = f"/{subtype}{path}"

	full_path = PROFILE + path
	if not os.path.isdir(os.path.dirname(full_path)):
		pathlib.Path(os.path.dirname(full_path)).mkdir(parents=True, exist_ok=True)

	if os.path.isfile(full_path):
		if VERBOSITY >= 4:
			print(f"{path} ... already exists")
		return

	if VERBOSITY >= 2 or (MAX_AGE and VERBOSITY >= 1):
		print(full_path)

	global new_files
	new_files += 1

	try:
		async with session.get(source, ssl=False) as response:
			if response.status != 200:
				print(f"{source} :: {response.status}")
				return

			# Download to temporary file
			temp_path = full_path + '.part'
			with open(temp_path, 'wb') as f:
				async for chunk in response.content.iter_chunked(8192):
					f.write(chunk)

			# Move temporary file
			shutil.move(temp_path, full_path)

	except Exception as e:
		print(f'Error downloading {source}: {str(e)} (skipping)')
		if os.path.exists(full_path + '.part'):
			os.remove(full_path + '.part')
######################
# END ASYNC DOWNLOAD #
######################

######################
# ASYNC CONTENT      #
######################
async def get_content(MEDIATYPE: str, API_LOCATION: str) -> None:
	posts = await api_request(API_LOCATION, MEDIATYPE)
	if "error" in posts:
		print(f"\nERROR: {API_LOCATION} :: {posts['error']['message']}")
		return

	if MEDIATYPE == "messages":
		posts = posts['list']

	if not posts:
		return

	print(f"Found {len(posts)} {MEDIATYPE}")
	
	# Create list of tasks for asynchronous download
	tasks = []
	for post in posts:
		if "media" not in post or ("canViewMedia" in post and not post["canViewMedia"]):
			continue
			
		if MEDIATYPE == "purchased" and ('fromUser' not in post or post["fromUser"]["username"] != PROFILE):
			continue

		postdate = (post.get("postedAt") or post.get("createdAt") or "1970-01-01")[:10]
		album = str(post["id"]) if len(post["media"]) > 1 else ""

		for media in post["media"]:
			if MEDIATYPE == "stories":
				postdate = media["createdAt"][:10] if media["createdAt"] else str(media["id"])

			if (("source" in media and "source" in media["source"] and media["source"]["source"] and 
				 ("canView" not in media or media["canView"])) or 
				("files" in media and "canView" in media and media["canView"])):
				tasks.append(download_media(media, MEDIATYPE, postdate, album))

	# Start parallel download with limit
	chunk_size = 5  # Number of simultaneous downloads
	for i in range(0, len(tasks), chunk_size):
		chunk = tasks[i:i + chunk_size]
		await asyncio.gather(*chunk)

	global new_files
	print(f"Downloaded {new_files} new {MEDIATYPE}")
	new_files = 0
######################
# END ASYNC CONTENT  #
######################

######################
# ASYNC USER INFO    #
######################
async def get_user_info(profile):
	# <profile> = "me" -> info about yourself
	info = await api_request("/users/" + profile, 'user-info')
	if "error" in info:
		print("\nFailed to get user: " + profile + "\n" + info["error"]["message"] + "\n")
	return info

async def get_subscriptions():
	subs = await api_request("/subscriptions/subscribes", "subscriptions")
	if "error" in subs:
		print("\nSUBSCRIPTIONS ERROR: " + subs["error"]["message"])
		return []  # Return empty list instead of None
	return [row['username'] for row in subs]
######################
# END ASYNC USER INFO#
######################

######################
# ASYNC MAIN         #
######################
async def main():
	# Initialize global variables
	global MAX_AGE, LATEST, PROFILE
	MAX_AGE = 0
	LATEST = 0
	PROFILE = ""

	await init_session()
	try:
		#####################
		# CONFIGURATIONS     #
		#####################
		if "--help" in sys.argv:
			print("\nUsage: " + sys.argv[0] + " <list of profiles / all> <max age (optional)>\n")
			print("max age must be an integer. number of days back from today.\n")
			print("if max age = 0, the script will find the latest date amongst the files for each profile independently.\n")
			print("Make sure to update the session variables at the top of this script (See readme).\n")
			print("Update Browser User Agent (Every time it updates): https://ipchicken.com/\n")
			print("Use --list to output a list of active subscriptions.\n")
			#print("Use -n <number> to select a profile from the list by number.\n")
			print("Use --help to display this text.\n")
			exit()

		
		if "--list" in sys.argv:
			subscriptions = await get_subscriptions()
			with open("subscriptions_list.txt", "w") as f:
				for idx, sub in enumerate(subscriptions, start=1):
					print(f"{idx}. {sub}")
					f.write(f"{sub}\n")
			exit()

	
		
		if len(sys.argv) < 2:
			print("\nUsage: " + sys.argv[0] + " <list of profiles / all> <max age (optional)>\n")
			print("max age must be an integer. number of days back from today.\n")
			print("if max age = 0, the script will find the latest date amongst the files for each profile independently.\n")
			print("Make sure to update the session variables at the top of this script (See readme).\n")
			print("Update Browser User Agent (Every time it updates): https://ipchicken.com/\n")
			print("Use --list to output a list of active subscriptions.\n")
			#print("Use -n <number> to select a profile from the list by number.\n")
			print("Use --help to display this text.\n")
			exit()

		#####################
		# END CONFIGURATIONS #
		#####################  
		
		if DL_DIR:
			try: os.chdir(DL_DIR)
			except: print('Unable to use DIR: ' + DL_DIR)
		print("CWD = " + os.getcwd())
		#rules for the signed headers are imported from config.py
		#dynamic_rules = {"static_param":"r0COhCenVY6tUCrcnkbwz727f1m0UHsv","start":"36587","end":"67a0ec50","checksum_constant":118,"checksum_indexes":[1,1,1,2,2,5,5,6,6,7,7,11,12,12,13,14,14,16,17,20,20,20,21,23,24,25,25,25,29,30,31,39],"app_token":"33d57ade8c02dbc5a333db99ff9ae26a","remove_headers":["user_id"],"revision":"202404181902-08205f45c3","is_current":0,"format":"36587:{}:{:x}:67a0ec50","prefix":"36587","suffix":"67a0ec50"}
		PROFILE_LIST = sys.argv
		PROFILE_LIST.pop(0)
		if PROFILE_LIST[-1] == "0":
			LATEST = 1
			PROFILE_LIST.pop(-1)
		if len(PROFILE_LIST) > 1 and PROFILE_LIST[-1].isnumeric():
			MAX_AGE = int((datetime.today() - timedelta(int(PROFILE_LIST.pop(-1)))).timestamp())
			print("\nGetting posts newer than " + str(datetime.utcfromtimestamp(int(MAX_AGE))) + " UTC")

		if PROFILE_LIST[0] == "all":
			PROFILE_LIST = await get_subscriptions()

		for PROFILE in PROFILE_LIST:
			if PROFILE in ByPass:
				if VERBOSITY > 0:
					print("skipping " + PROFILE)
				continue
			user_info = await get_user_info(PROFILE)

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
				print("\n" + PROFILE + " exists.\nDownloading new media, skipping pre-existing.")
			else:
				print("\nDownloading content to " + PROFILE)

			if POSTS:
				await get_content("posts", "/users/" + PROFILE_ID + "/posts")
			if ARCHIVED:
				await get_content("archived", "/users/" + PROFILE_ID + "/posts/archived")
			if STORIES:
				await get_content("stories", "/users/" + PROFILE_ID + "/stories")
			if MESSAGES:
				await get_content("messages", "/chats/" + PROFILE_ID + "/messages")
			if PURCHASED:
				await get_content("purchased", "/posts/paid")

	finally:
		await close_session()

if __name__ == "__main__":
	# Start asynchronous code
	asyncio.run(main())
######################
# END ASYNC MAIN     #
######################
