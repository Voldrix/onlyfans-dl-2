# config.py
#====================
# DO NOT TOUCH IT ↓↓↓
#====================
import re
import logging
#====================
# DO NOT TOUCH IT ↑↑↑
#====================

# Session Variables (update every time you login or your browser updates)
USER_ID = "xxx"
USER_AGENT = "xxx"
X_BC = "xxx"
SESS_COOKIE = "xxx"

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

# Content types to download
VIDEOS = True #False
PHOTOS = True #False
AUDIO = True #False
POSTS = True #False
STORIES = True #False
MESSAGES = True #False
ARCHIVED = True #False
PURCHASED = True #False

# Telegram Bot Tokens
TELEGRAM_BOT_TOKENS = ["xxx", "yyy"]  # добавьте столько токенов, сколько необходимо

# Current active bot index
current_bot_index = 0  # по умолчанию активен первый бот

# Your Telegram API app
API_ID = 'xxx'
API_HASH = 'xxx'

# Your Telegram ID (to restrict access to bot only from your account)
TELEGRAM_USER_ID = xxx

# Size of disk space buffer you want to use on your server for temporary media saving
CACHE_SIZE_LIMIT = 10000 * 1024 * 1024  # limit to your free disk space on server you don't want to exceed

# Maximum count of parallel downloads from OnlyFans site and uploads to telegram
MAX_PARALLEL_DOWNLOADS = 400 
MAX_PARALLEL_UPLOADS = 100

# Keep or Delete media files on server after posting in Telegram
delete_media_from_server = True  #False

#====================
# DO NOT TOUCH IT ↓↓↓
#====================
# Verify length and format of cookie's values
def update_config(key, value):
    if key == "USER_ID":
        if not re.match(r'^\d{1,16}$', value):
            raise ValueError("Invalid USER_ID format")
    elif key == "USER_AGENT":
        if not (16 <= len(value) <= 512) or not re.match(r'^Mozilla\/\d+\.\d+ \([^)]+\) .+', value):
            raise ValueError("Invalid USER_AGENT format")
    elif key == "X_BC":
        if not re.match(r'^[a-f0-9]{32,48}$', value):
            raise ValueError("Invalid X_BC format")
    elif key == "SESS_COOKIE":
        if not re.match(r'^[a-zA-Z0-9]{16,32}$', value): 
            raise ValueError("Invalid SESS_COOKIE format")

    # Write new cookies to this file
    with open(__file__, 'r') as f:
        config_content = f.read()

    new_content = re.sub(f'{key} = ".*?"', f'{key} = "{value}"', config_content)

    with open(__file__, 'w') as f:
        f.write(new_content)
#====================
# DO NOT TOUCH IT ↑↑↑
#====================
