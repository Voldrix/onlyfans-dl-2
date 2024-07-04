import re
import logging
from user_config import *

# path to script onlyfans-dl.py
ONLYFANS_DL_SCRIPT = 'onlyfans-dl.py'

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

# Current active bot index (do not change it)
current_bot_index = 0

# Size of disk space buffer you want to use on your server for temporary media saving
CACHE_SIZE_LIMIT = 25000 * 1024 * 1024
# Maximum size of file that Telegram can handle (do not change it)
TELEGRAM_FILE_SIZE_LIMIT = 2000 * 1024 * 1024

# Maximum count of parallel downloads from OnlyFans site and uploads to telegram (do not change it if no need)
MAX_PARALLEL_DOWNLOADS = 400 
MAX_PARALLEL_UPLOADS = 100

# Keep or Delete media files on server after posting in Telegram
delete_media_from_server = True  #False

# Verify length and format of cookie's values and update user_config.py
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

    # Load current config
    with open('user_config.py', 'r') as f:
        config_content = f.read()

    # Update the value
    new_content = re.sub(f'{key} = ".*?"', f'{key} = "{value}"', config_content)

    # Write updated config back to file
    with open('user_config.py', 'w') as f:
        f.write(new_content)

    # Update global variable
    globals()[key] = value
