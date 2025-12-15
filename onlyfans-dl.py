#!/usr/bin/env python3

import getopt
import hashlib
import json
import os
import pathlib
import pprint
import random
import re
import requests
import session_vars
import shutil
import sys
import time

from datetime import datetime, timezone, timedelta
from typing import List

requests.urllib3.disable_warnings()

start_time = time.time()
script_path = sys.path[0]

class OFDownloader():
	def __init__(self, user_id: str, user_agent: str, sess_cookie: str, x_bc: str, rulesurl: str, ignorelist: List[str]) -> None:
		# from session_vars, imported
		self.user_id = user_id
		self.user_agent = user_agent
		self.sess_cookie = sess_cookie
		self.x_bc = x_bc
		self.ignorelist = ignorelist

		# Sane defaults that can be overridden by command-line options
		#Content types to download
		self.get_videos = True
		self.get_photos = True
		self.get_audio = True
		self.get_posts = True
		self.get_stories = True
		self.get_messages = True
		self.get_archives = True
		self.get_purchased = True

		self.antispam = False
		self.shuffle_users = False
		self.verbosity = 1		# 0-6
						#0 = Be quiet about everything
						#1 = do not print file names or api calls, alert when sleeping
						#2 = print filenames only when max_age is set
						#3 = always print filenames
						#4 = print api calls
						#5 = print skipped files that already exist
		## Options
		self.albums = False ## Separate photos into subdirectories by post/album (Single photo posts are not put into subdirectories)
		self.use_subfolders = True ## Use content type subfolders (messgaes/archived/stories/purchased), or download everything to /profile/photos and /profile/videos

		# Other global vars
		self.processed_count = 0
		self.max_age = 0
		self.days = None
		self.directory = None
		self.latest = 0
		self.fetched = False

		# DEBUGGING ONLY
		self.DownloadEnabled = True

		## API Info
		self.api_url = "https://onlyfans.com/api2/v2"
		self.new_files = 0
		self.api_headers = {
			"Accept": "application/json, text/plain, */*",
			"Accept-Encoding": "gzip, deflate",
			"app-token": "33d57ade8c02dbc5a333db99ff9ae26a",
			"User-Agent": self.user_agent,
			"x-bc": self.x_bc,
			"user-id": self.user_id,
			"Cookie": "auh_id=" + self.user_id + "; sess=" + self.sess_cookie,
			"Referer" : "https://onlyfans.com/"
		}

		## Get the rules for the signed headers dynamically, so we don't have to update the script every time they change
		self.dynamic_rules = requests.get(rulesurl).json()


	def create_signed_headers(self, link, queryParams):
		path = "/api2/v2" + link
		if queryParams:
			query = '&'.join('='.join((key,val)) for (key,val) in queryParams.items())
			path = f"{path}?{query}"
		unixtime = str(int(datetime.now().timestamp()))
		msg = "\n".join([self.dynamic_rules["static_param"], unixtime, path, self.user_id])
		message = msg.encode("utf-8")
		hash_object = hashlib.sha1(message)
		sha_1_sign = hash_object.hexdigest()
		sha_1_b = sha_1_sign.encode("ascii")
		checksum = sum([sha_1_b[number] for number in self.dynamic_rules["checksum_indexes"]])+self.dynamic_rules["checksum_constant"]
		self.api_headers["sign"] = self.dynamic_rules["format"].format(sha_1_sign, abs(checksum))
		self.api_headers["time"] = unixtime
		return


	def showAge(self, myStr):
		myStr = str(myStr)
		tmp = myStr.split('.')
		t = int(tmp[0])
		dt_obj = datetime.fromtimestamp(t)
		strOut = dt_obj.strftime("%Y-%m-%d")
		return(strOut)


	def latestMedia(self, profile):
		latest = "0";
		for dirpath, dirs, files in os.walk(profile):
			for f in files:
				if f.startswith('20'):
					latest = f if f > latest else latest
		return latest[:10]


	def api_request(self, endpoint, apiType):
		posts_limit = 50
		age = ''
		getParams = { "limit": str(posts_limit), "order": "publish_date_asc"}
		if apiType == 'messages':
			getParams['order'] = "desc"
		if apiType == 'subscriptions':
			getParams['type'] = 'active'
			getParams['offset'] = '0'
			getParams['format'] = 'infinite'
		if self.max_age and apiType != 'messages' and apiType != 'purchased' and apiType != 'subscriptions': #Cannot be limited by age
			getParams['afterPublishTime'] = str(self.max_age) + ".000000"
			age = " age " + str(self.showAge(getParams['afterPublishTime']))
			#Messages can only be limited by offset or last message ID. This requires its own separate function. TODO
		self.create_signed_headers(endpoint, getParams)
		if self.verbosity > 5:
			print(self.api_url + endpoint + age, self.api_headers, getParams)
		elif self.verbosity > 3:
			print(self.api_url + endpoint + age)


		status = requests.get(self.api_url + endpoint, headers=self.api_headers, params=getParams)
		if status.ok:
			list_base = status.json()
			if self.verbosity > 4:
				print(f"API request is okay..., returned list base length={0}",len(list_base))
		else:
			if self.verbosity > 4:
				print("API request failed...")
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
				self.create_signed_headers(endpoint, getParams)
				if self.verbosity > 3: print(self.api_url + endpoint + age)
				status = requests.get(self.api_url + endpoint, headers=self.api_headers, params=getParams)
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


	def get_user_info(self, profile):
		# <profile> = "me" -> info about yourself
		info = self.api_request("/users/" + profile, 'user-info')
		if "error" in info:
			print(f"\nERROR: Failed to get user: {profile}\n" + info["error"]["message"] + "\n")
			return False
		return info


	def get_subscriptions(self):
		subs = self.api_request("/subscriptions/subscribes", "subscriptions")
		if "error" in subs:
			print("\nERROR: Subscription issue: " + subs["error"]["message"])
			return ""

		if "list" in subs:
			if self.verbosity > 0: print("This run saw subs as a list")
			return [row['username'] for row in subs["list"]]
		else:
			if self.verbosity > 0: print("This run saw subs as unlisted")
			return [row['username'] for row in subs]


	def download_media(self, profile, media, subtype, postdate, album = ''):
		source = None
		if postdate is not None:
			filename = postdate + "_" + str(media["id"])
		else:
			filename = str(media["id"])

		if (media["type"] == "video"):
			if ("files" in media and "drm" in media["files"]):
				if ( "manifest" in media["files"]["drm"] ):
					if ( "dash" in media["files"]["drm"]["manifest"] ):
						if self.verbosity > 1: print("found DASH manifest, but we can't process it")
					if ( "hls" in media["files"]["drm"]["manifest"] ):
						if self.verbosity > 1: print("found HLS manifest, but we can't process it")
				# if there's no unprotected source to our video, we'll grab the preview image if there's one available
				if source is None:
					if self.verbosity > 0: print("...attempting to download preview image instead")
					if "preview" in media["files"]:
						source = media["files"]["preview"]["url"]
					elif "preview" in media:
						source = media["preview"]

		if source is None:
			if subtype == "stories":
				if "files" in media and "full" in media["files"]:
					source = media["files"]["full"]["url"]
				else:
					print("ERROR: stories: media[files] missing full.url: ")
					pprint.pprint(media["files"])
					return False
			else:
				if self.verbosity > 2: print(media)
				if "source" in media and "source" in media["source"]:
					source = media["source"]["source"]
				else:
					if "files" in media and "full" in media["files"]:
						source = media["files"]["full"]["url"]
		if source is None:
			if "canView" in media and not media["canView"]:
				return False
			else:
				print("WARN: No source found for media:")
				pprint.pprint(media)
				return False

		if (media["type"] != "photo" and media["type"] != "video" and media["type"] != "audio" and media["type"] != "gif") or not media['canView']:
			return False
		if (media["type"] == "photo" and not self.get_photos) or (media["type"] == "video" and not self.get_videos) or (media["type"] == "audio" and not self.get_audio):
			return False

		extension = source.split('?')[0].split('.')
		ext = '.' + extension[len(extension)-1]
		if len(ext) < 3:
			return False

		if self.albums and album and media["type"] == "photo":
			if postdate is not None:
				path = "/photos/" + postdate + "_" + album + "/" + filename + ext
			else:
				path = "/photos/" + album + "/" + filename + ext
		else:
			path = "/" + media["type"] + "s/" + filename + ext
		if self.use_subfolders and subtype != "posts":
			path = "/" + subtype + path
		if not os.path.isdir(profile + os.path.dirname(path)):
			pathlib.Path(profile + os.path.dirname(path)).mkdir(parents=True, exist_ok=True)
		if not os.path.isfile(profile + path):
			if self.verbosity > 2 or ((self.latest or self.max_age) and self.verbosity > 1):
				print(profile + path)
			self.new_files += 1
			try:
				if self.DownloadEnabled:
					r = requests.get(source, stream=True, timeout=(4,None), verify=False)
				else:
					r.status_code = 404
					r.url = source
					if self.verbosity > 3: print(f"would have fetched: {source}")
			except:
				bareurl = source.split("?")[0]
				if self.verbosity > 2: print(f"INFO: skipping existing file: {bareurl}")
				return False
			if r.status_code != 200:
				if self.verbosity > 1: print(f"WARN: {r.url} :: " + str(r.status_code))
				return False
			# Writing to a temp file while downloading, so if we interrupt
			# a file, we will not skip it but re-download it at next time.
			with open(profile + path + '.part', 'wb') as f:
				r.raw.decode_content = True
				shutil.copyfileobj(r.raw, f)
			r.close()
			# Downloading finished, remove temp file.
			shutil.move(profile + path + '.part', profile + path)
			if self.verbosity > 2: print(f"INFO: saved media to {profile}{path}")
			self.fetched = True
		else:
			if self.verbosity > 4: print(path + ' ... already exists')
			return False
		return True


	def get_content(self, profile, mediatype, api_location):
		np = 1
		posts = self.api_request(api_location, mediatype)
		if "error" in posts:
			if self.verbosity > 1: print(f"\nERROR: {api_location} :: " + posts["error"]["message"])
			return False

		if mediatype == "messages":
			posts = posts['list']
		if len(posts) > 0:
			if self.verbosity > 0: print("Found " + str(len(posts)) + " " + mediatype)
			for post in posts:
				if "media" not in post or ("canViewMedia" in post and not post["canViewMedia"]):
					continue
				if mediatype == "purchased" and ('fromUser' not in post or post["fromUser"]["username"] != profile):
					continue # Only get paid posts from profile

				if 'postedAt' in post: #get post date
					postdate = str(post["postedAt"][:10])
				elif 'createdAt' in post:
					postdate = str(post["createdAt"][:10])
				else:
					postdate = self.user_epoch #epoc failsafe if date is not present

				if len(post["media"]) > 1: # Don't put single photo posts in a subfolder
					album = str(post["id"]) #album ID
				else:
					album = ""
				for media in post["media"]:
					result = False
					if mediatype == "stories" and "createdAt" in media:
						if 'postedAt' in media: #get post date
							postdate = str(post["postedAt"][:10])
						elif 'createdAt' in media and  media["createdAt"] is not None:
							postdate = str(post["createdAt"][:10])
						else:
							postdate = self.user_epoch #epoc failsafe if date is not present

					if "source" in media and "source" in media["source"] and media["source"]["source"] and ("canView" not in media or media["canView"]) or "files" in media:
						result = self.download_media(profile, media, mediatype, postdate, album)
						if result == True:
							np += 1
						if self.antispam == True:
							rn = random.randint(0, 120)
							if np % 500 == 0:
								st=840+rn
							elif np % 100 == 0:
								st=240+rn
							else:
								#st=(random.randint(1,100)/10)
								st=0
							if st > 10 and self.fetched == True:
								if self.verbosity > 0:print(f"{np}: Sleeping about {st}s...", end="", flush=True)
								time.sleep(st)
								if self.verbosity > 0: print("resuming")
								self.fetched = False
				#done Media
			# done Posts
			if self.verbosity > 0: print("INFO: Downloaded " + str(self.new_files) + " new " + mediatype)
			if self.new_files > 0:
				self.fetched = True
			self.new_files = 0


	def run(self, profile_list):
		if self.days is not None:
			self.max_age = int((datetime.today() - timedelta( int(self.days) )).timestamp() )
			if self.verbosity > 0: print("\nGetting posts newer than " + str(datetime.fromtimestamp(int(self.max_age), timezone.utc)) + " UTC")

		if profile_list[0] == "all":
			profile_list = self.get_subscriptions()

		pll = len(profile_list)
		if pll == 0:
			print("\nWARN: No profiles to download, exiting...")
			exit(1)


		if self.shuffle_users == True:
			random.shuffle(profile_list)

		if self.verbosity > 1:
			print(f"\nRunning with headers: {self.api_headers}\n")

		pi = 0
		pe = 0
		il = len(self.ignorelist)

		for profile in profile_list:
			if self.verbosity > 0: print(f"\n attempting to grab profile {profile}")

			if profile in self.ignorelist:
				if self.verbosity > 0: print(f"\n*** skipping ignored user: {profile}")
				continue

			user_info = self.get_user_info(profile)

			if user_info is False:
				print(f"\n*** get_user_info({profile}) returned false!\n")
				continue

			if self.verbosity > 1: print(f"\nDEBUG: user_info is {user_info}\n")

			if "id" in user_info:
				profile_id = str(user_info["id"])
			else:
				if self.verbosity > 0: print(f"\n*** skipping disabled user: {profile}")
				pe += 1
				continue


			# Grab some date to use later
			if "joinDate" in user_info:
				tempdate = re.sub(r"(\+\d{2}):?(\d{2})$", r"\1\2", user_info["joinDate"])
				self.user_epoch = datetime.strptime(tempdate, '%Y-%m-%dT%H:%M:%S%z').strftime('%Y-%m-%d')
			else:
				self.user_epoch = "1970-01-01" # Last ditch epoch date

			totl = pll - il - pe

			if self.verbosity > 0: print(f"\nINFO: {pi}/{totl}: Getting {profile}'s content")
			if "mediasCount" in user_info:
				if self.verbosity > 0: print(f"INFO: user has {user_info['mediasCount']} media files" )

			if self.latest and self.max_age is None:
				latestDate = self.latestMedia(profile)
				if latestDate != "0":
					self.max_age = int(datetime.strptime(latestDate + ' 00:00:00', '%Y-%m-%d %H:%M:%S').timestamp())
				if self.verbosity > 0: print(f"INFO: Limiting to content newer than {latestDate} 00:00:00 UTC")

			if os.path.isdir(profile):
				if self.verbosity > 1: print("\nINFO: Downloading new media, skipping pre-existing.")

			if self.get_posts:
				if self.verbosity > 1: print(f"INFO: Fetching content from posts")
				self.get_content(profile, "posts", "/users/" + profile_id + "/posts")
			if self.get_archives:
				if self.verbosity > 1: print(f"INFO: Fetching content from archives")
				self.get_content(profile, "archived", "/users/" + profile_id + "/posts/archived")
			if self.get_stories:
				if self.verbosity > 1: print(f"INFO: Fetching content from stories")
				self.get_content(profile, "stories", "/users/" + profile_id + "/stories")
			if self.get_messages:
				if self.verbosity > 1: print(f"INFO: Fetching content from messages")
				self.get_content(profile, "messages", "/chats/" + profile_id + "/messages")
			if self.get_purchased:
				if self.verbosity > 1: print(f"INFO: Fetching PPV content")
				self.get_content(profile, "purchased", "/posts/paid/all")
			pi += 1

			if self.antispam == True:
				if self.fetched == True and pi < totl:
					rn = 120 + random.randint(0, 120)
					if self.verbosity > 0: print(f"\n*** Sleeping {rn}s before next profile...", end="", flush=True)
					time.sleep(rn)
					if self.verbosity > 0: print(" ...resuming")
					self.fetched = False

		if ( pe > 0 ):
			if self.verbosity > 0: print(f"\nINFO: {pe} issues accessing {pi} profiles")
			return(1)
		else:
			return(0)


	def usage(self):
		print("\nUsage: " + sys.argv[0] + " [opts] <list of profiles | all>")
		print("Options:")
		print(" -t #/--timestamp=#	Integer number of days # before today as max age to scan.")
		print("				  The script will default to the latest date amongst the files for each profile independantly.")
		print(" -d X/--directory=X	Use directory X as the parent for all downloads")
		print("				  defaults to the current working direcory")
		print(" -v #/--verbose=#	Increase the self.verbosity/debugging of the script (0-6, default is 0)")
		print(" -a/--antispam		Enable anti-dl-spam detection delays (default no)\n")
		print(" -s/--shuffle		Shuffle the user-list (default no)\n")
		print(" -l/--latest		Fetch only the latest media (default no)\n")
		print(" --videos=[yes,no]	Include videos in downloaded content (default yes)")
		print(" --photos=[yes,no]	Include fotos in downloaded content (default yes)")
		print(" --audio=[yes,no]	Include audio in downloaded content (default yes)")
		#
		print(" --posts=[yes,no]	Include posts in downloaded content (default yes)")
		print(" --stories=[yes,no]	Include stories in downloaded content (default yes)")
		print(" --messages=[yes,no]	Include messages in downloaded content (default yes)")
		print(" --archived=[yes,no]	Include old archives in downloaded content (default yes)")
		print(" --purchased=[yes,no]	Include bought/purchased in downloaded content (default yes)\n")
		#
		print(" * Make sure to update the session variables in session_vars.py if you experience issues logging in.")
		print(" * Update Browser (Every time it updates) User-Agent using: https://ipchicken.com/\n")


def main(argv):
	latest = 0

	if len(session_vars.USER_ID) == 0:
		print("ERROR: USER_ID not set in session_vars_local.py")
		exit(2)

	if len(session_vars.USER_AGENT) == 0:
		print("ERROR: USER_AGENT not set in session_vars_local.py")
		exit(2)

	if len(session_vars.SESS_COOKIE) == 0:
		print("ERROR: SESS_COOKIE not set in session_vars_local.py")
		exit(2)

	if len(session_vars.X_BC) == 0:
		print("ERROR: X_BC not set in session_vars_local.py")
		exit(2)

	if len(session_vars.RULESURL) == 0:
		print("ERROR: RULESURL not set in session_vars_local.py")
		exit(2)

	ofd = OFDownloader(session_vars.USER_ID, session_vars.USER_AGENT, session_vars.SESS_COOKIE, session_vars.X_BC, session_vars.RULESURL, session_vars.IGNORELIST)

	try:
		opts, args = getopt.getopt(argv,"lhsad:t:v:",
			["latest", "help", "shuffle", "antispam", "directory=", "timestamp=", "verbose=", "videos=",
			 "photos=", "audio=", "posts=", "stories=", "messages=", "archived=", "purchased=", ])
	except getopt.GetoptError as e:
		ofd.usage()
		exit(2)

	for opt, arg in opts:
		if opt in ("-h", "--help"):
			ofd.usage()
			exit(0)
		elif opt in ("-a", "--antispam"):
			ofd.antispam = True
			print("    * Enabling anti-dl-spam detection delays")
		elif opt in ("-s", "--shuffle"):
			ofd.shuffle_users = True
			print("    * Shuffling profile list")
		elif opt in ("-l", "--latest"):
			ofd.latest = 1
			print("    * Fetching latest posts")
		elif opt in ("-t", "--timestamp"):
			ofd.days = arg
			print(f"    * Limiting to last {arg} days")
		elif opt in ("-d", "--directory"):
			ofd.directory = arg
		elif opt in ("-v", "--verbose"):
			ofd.verbosity = int(arg)
		elif opt in ("--videos"):
			if arg == "no":
				ofd.get_videos = False
		elif opt in ("--photos"):
			if arg == "no":
				ofd.get_photos = False
		elif opt in ("--audio"):
			if arg == "no":
				ofd.get_audio = False
		elif opt in ("--posts"):
			if arg == "no":
				ofd.get_posts = False
		elif opt in ("--stories"):
			if arg == "no":
				ofd.get_stories = False
		elif opt in ("--messages"):
			if arg == "no":
				ofd.get_messages = False
		elif opt in ("--archived"):
			if arg == "no":
				ofd.get_archives = False
		elif opt in ("--purchased"):
			if arg == "no":
				ofd.get_purchased = False
		else:
			usage
			exit(1)

	if args is None or len(args) == 0:
		print("\nNo profiles to download, exiting...")
		exit()

	if ofd.directory is not None:
		try:
			os.chdir(ofd.directory)
		except:
			print('ERROR: Unable to use DIR: ' + ofd.directory)
			exit(1)

	cdir = os.getcwd()

	print(f"Downloading all media files to {cdir}/")

	# Done setting up, now process everything
	status = ofd.run(args)

	exit(status)


######################################

if __name__ == "__main__":
	 main(sys.argv[1:])
