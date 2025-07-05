# config.py

import re

#########################
# USER CONFIG (START) #
#########################
USER_ID = "xxx"
USER_AGENT = "xxx"
X_BC = "xxx"
SESS_COOKIE = "xxx"
#########################
# USER CONFIG (START) #
#########################

#====================================================

#########################
# SYSTEM CONFIG (START) #
#########################

dynamic_rules = {"static_param":"r0COhCenVY6tUCrcnkbwz727f1m0UHsv","start":"36587","end":"67a0ec50","checksum_constant":118,"checksum_indexes":[1,1,1,2,2,5,5,6,6,7,7,11,12,12,13,14,14,16,17,20,20,20,21,23,24,25,25,25,29,30,31,39],"app_token":"33d57ade8c02dbc5a333db99ff9ae26a","remove_headers":["user_id"],"revision":"202404181902-08205f45c3","is_current":0,"format":"36587:{}:{:x}:67a0ec50","prefix":"36587","suffix":"67a0ec50"}  

# Maximum count of onlyfans profiles to list
POSTS_LIMIT = 100

# 0 = do not print file names or api calls
# 1 = print filenames only when max_age is set
# 2 = always print filenames
# 3 = print api calls
# 4 = print skipped files that already exist
VERBOSITY = 2

# Download Directory. Uses CWD if null
DL_DIR = ''

# List of accounts to skip
ByPass = ['']

# Separate photos into subdirectories by post/album (Single photo posts are not put into subdirectories)
ALBUMS = False #True

# Use content type subfolders (messages/archived/stories/purchased), or download everything to /profile/photos and /profile/videos
USE_SUB_FOLDERS = False #True

#Content types to download
VIDEOS = True
PHOTOS = True
AUDIO = True
POSTS = True
STORIES = True
MESSAGES = True
ARCHIVED = True
PURCHASED = True
#########################
# SYSTEM CONFIG (END)   #
#########################
