#!/usr/bin/env python3

import os
import sys
import json
import shutil
import pathlib
import requests
import hashlib
from datetime import datetime, timedelta
requests.urllib3.disable_warnings()

from configurations import *

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
	API_HEADER["sign"] = dynamic_rules["format"].format(sha_1_sign, abs(checksum))
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
	latest = "0"
	for dirpath, dirs, files in os.walk(profile):
		for f in files:
			if f.startswith('20'):
				latest = f if f > latest else latest
	return latest[:10]


def api_request(endpoint, apiType):
	posts_limit = 50
	age = ''
	getParams = { "limit": str(posts_limit), "order": "publish_date_asc"}
	if apiType == 'messages':
		getParams['order'] = "desc"
	if apiType == 'subscriptions':
		getParams['type'] = 'active'
	if apiType == 'all_subscriptions':
		getParams['type'] = 'all'
	if MAX_AGE and apiType != 'messages' and apiType != 'purchased' and apiType != 'subscriptions': #Cannot be limited by age
		getParams['afterPublishTime'] = str(MAX_AGE) + ".000000"
		age = " age " + str(showAge(getParams['afterPublishTime']))
		#Messages can only be limited by offset or last message ID. This requires its own separate function. TODO
	create_signed_headers(endpoint, getParams)
	if VERBOSITY >= 3: print(API_URL + endpoint + age)

	status = requests.get(API_URL + endpoint, headers=API_HEADER, params=getParams)
	if status.ok:
		list_base = status.json()
	else:
		return json.loads('{"error":{"message":"http '+str(status.status_code)+'"}}')

	# Fixed the issue with the maximum limit of 50 posts by creating a kind of "pagination"
	if (len(list_base) >= posts_limit and apiType != 'user-info') or ('hasMore' in list_base and list_base['hasMore']):
		if apiType == 'messages':
			getParams['id'] = str(list_base['list'][len(list_base['list'])-1]['id'])
		elif apiType == 'purchased' or apiType == 'subscriptions':
			getParams['offset'] = str(posts_limit)
		else:
			getParams['afterPublishTime'] = list_base[len(list_base)-1]['postedAtPrecise']
		while 1:
			create_signed_headers(endpoint, getParams)
			if VERBOSITY >= 3: print(API_URL + endpoint + age)
			status = requests.get(API_URL + endpoint, headers=API_HEADER, params=getParams)
			if status.ok:
				list_extend = status.json()
			if apiType == 'messages':
				list_base['list'].extend(list_extend['list'])
				if list_extend['hasMore'] == False or len(list_extend['list']) < posts_limit or not status.ok:
					break
				getParams['id'] = str(list_base['list'][len(list_base['list'])-1]['id'])
				continue
			list_base.extend(list_extend) # Merge with previous posts
			if len(list_extend) < posts_limit:
				break
			if apiType == 'purchased' or apiType == 'subscriptions':
				getParams['offset'] = str(int(getParams['offset']) + posts_limit)
			else:
				getParams['afterPublishTime'] = list_extend[len(list_extend)-1]['postedAtPrecise']
	return list_base


def get_user_info(profile):
	# <profile> = "me" -> info about yourself
	info = api_request("/users/" + profile, 'user-info')
	if "error" in info:
		print("\nFailed to get user: " + profile + "\n" + info["error"]["message"] + "\n")
	return info


def get_subscriptions():
	subs = api_request("/subscriptions/subscribes", "subscriptions")
	if "error" in subs:
		print("\nSUBSCRIPTIONS ERROR: " + subs["error"]["message"])
		return
	return [row['username'] for row in subs]

def get_all_subscriptions():
	subs = api_request("/subscriptions/subscribes", "all_subscriptions")
	if "error" in subs:
		print("\nSUBSCRIPTIONS ERROR: " + subs["error"]["message"])
		return
	return [row['username'] for row in subs]

def download_media(media, subtype, postdate, album = ''):
	filename = postdate + "_" + str(media["id"])
	if subtype == "stories":
		source = media["files"]["source"]["url"]
	else:
		source = media["source"]["source"]
		if not source:
			if "preview" in media["files"]:
				source = media["files"]["preview"]["url"]
			elif "preview" in media:
				source = media["preview"]

	if (media["type"] != "photo" and media["type"] != "video" and media["type"] != "audio" and media["type"] != "gif") or not media['canView']:
		return
	if (media["type"] == "photo" and not PHOTOS) or (media["type"] == "video" and not VIDEOS) or (media["type"] == "audio" and not AUDIO):
		return

	extension = source.split('?')[0].split('.')
	ext = '.' + extension[len(extension)-1]
	if len(ext) < 3:
		return

	if ALBUMS and album and media["type"] == "photo":
		path = "/photos/" + postdate + "_" + album + "/" + filename + ext
	else:
		path = "/" + media["type"] + "s/" + filename + ext
	if USE_SUB_FOLDERS and subtype != "posts":
		path = "/" + subtype + path
	if not os.path.isdir(PROFILE + os.path.dirname(path)):
		pathlib.Path(PROFILE + os.path.dirname(path)).mkdir(parents=True, exist_ok=True)
	if not os.path.isfile(PROFILE + path):
		if VERBOSITY >= 2 or (MAX_AGE and VERBOSITY >= 1):
			print(PROFILE + path)
		global new_files
		new_files += 1
		try:
			r = requests.get(source, stream=True, timeout=(4,None), verify=False)
		except:
			print('Error getting: ' + source + ' (skipping)')
			return
		if r.status_code != 200:
			print(r.url + ' :: ' + str(r.status_code))
			return
		# Writing to a temp file while downloading, so if we interrupt
		# a file, we will not skip it but re-download it at next time.
		with open(PROFILE + path + '.part', 'wb') as f:
			r.raw.decode_content = True
			shutil.copyfileobj(r.raw, f)
		r.close()
		# Downloading finished, remove temp file.
		shutil.move(PROFILE + path + '.part', PROFILE + path)
	else:
		if VERBOSITY >= 4: print(path + ' ... already exists')


def get_content(MEDIATYPE, API_LOCATION):
	posts = api_request(apiType=MEDIATYPE, endpoint=API_LOCATION)
	if "error" in posts:
		print("\nERROR: " + API_LOCATION + " :: " + posts["error"]["message"])
	if MEDIATYPE == "messages":
		posts = posts['list']
	if len(posts) > 0:
		print("Found " + str(len(posts)) + " " + MEDIATYPE)
		for post in posts:
			if "media" not in post or ("canViewMedia" in post and not post["canViewMedia"]):
				continue
			if MEDIATYPE == "purchased" and ('fromUser' not in post or post["fromUser"]["username"] != PROFILE):
				continue # Only get paid posts from PROFILE
			if 'postedAt' in post: #get post date
				postdate = str(post["postedAt"][:10])
			elif 'createdAt' in post:
				postdate = str(post["createdAt"][:10])
			else:
				postdate = "1970-01-01" #epoc failsafe if date is not present
			if len(post["media"]) > 1: # Don't put single photo posts in a subfolder
				album = str(post["id"]) #album ID
			else:
				album = ""
			for media in post["media"]:
				if MEDIATYPE == "stories":
					postdate = str(media["createdAt"][:10])
				if "source" in media and "source" in media["source"] and media["source"]["source"] and ("canView" not in media or media["canView"]) or "files" in media:
					download_media(media, MEDIATYPE, postdate, album)
		global new_files
		print("Downloaded " + str(new_files) + " new " + MEDIATYPE)
		new_files = 0


if __name__ == "__main__":
	if len(sys.argv) < 2:
		print("\nUsage: " + sys.argv[0] + " <list of profiles / all> <max age (optional)>\n")
		print("max age must be an integer. number of days back from today.\n")
		print("if max age = 0, the script will find the latest date amongst the files for each profile independantly.\n")
		print("Make sure to update the session variables at the top of this script (See readme).\n")
		print("Update Browser User Agent (Every time it updates): https://ipchicken.com/\n")
		exit()
	
	if DL_DIR:
		try: os.chdir(DL_DIR)
		except: print('Unable to use DIR: ' + DL_DIR)
	print("CWD = " + os.getcwd())
	#Get the rules for the signed headers dynamically, so we don't have to update the script every time they change
	dynamic_rules = requests.get('https://raw.githubusercontent.com/DATAHOARDERS/dynamic-rules/main/onlyfans.json').json()
	PROFILE_LIST = sys.argv
	PROFILE_LIST.pop(0)
	if PROFILE_LIST[-1] == "0":
		LATEST = 1
		PROFILE_LIST.pop(-1)
	if len(PROFILE_LIST) > 1 and PROFILE_LIST[-1].isnumeric():
		MAX_AGE = int((datetime.today() - timedelta(int(PROFILE_LIST.pop(-1)))).timestamp())
		print("\nGetting posts newer than " + str(datetime.utcfromtimestamp(int(MAX_AGE))) + " UTC")

	if PROFILE_LIST[0] == "all":
		PROFILE_LIST = get_subscriptions()

	if PROFILE_LIST[0] == "all_subs":
		PROFILE_LIST = get_all_subscriptions()

	if not len(PROFILE_LIST) < 1:
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
				print("\n" + PROFILE + " exists.\nDownloading new media, skipping pre-existing.")
			else:
				print("\nDownloading content to " + PROFILE)

			if POSTS:
				get_content("posts", "/users/" + PROFILE_ID + "/posts")
			if ARCHIVED:
				get_content("archived", "/users/" + PROFILE_ID + "/posts/archived")
			if STORIES:
				get_content("stories", "/users/" + PROFILE_ID + "/stories")
			if MESSAGES:
				get_content("messages", "/chats/" + PROFILE_ID + "/messages")
			if PURCHASED:
				get_content("purchased", "/posts/paid")
	
	else:
		print("No Profile found!")

