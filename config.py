import re
import json
import logging

# Session Variables loaded from user_config.json
with open('user_config.json', 'r') as f:
    user_config = json.load(f)

# Идентификатор пользователя для сессии
USER_ID = user_config["USER_ID"]
# User-Agent браузера для имитации запросов
USER_AGENT = user_config["USER_AGENT"]
# Параметр X-BC, используемый для аутентификации
X_BC = user_config["X_BC"]
# Сессионный куки для аутентификации
SESS_COOKIE = user_config["SESS_COOKIE"]
# Токены Telegram-ботов для отправки сообщений
TELEGRAM_BOT_TOKENS = user_config["TELEGRAM_BOT_TOKENS"]
# Идентификатор приложения Telegram API
API_ID = user_config["API_ID"]
# Хэш приложения Telegram API
API_HASH = user_config["API_HASH"]
# Идентификатор пользователя Telegram для ограничения доступа к боту
TELEGRAM_USER_ID = user_config["TELEGRAM_USER_ID"]

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

# Current active bot index
current_bot_index = 0  # по умолчанию активен первый бот

# Size of disk space buffer you want to use on your server for temporary media saving
CACHE_SIZE_LIMIT = 10000 * 1024 * 1024  # limit to your free disk space on server you don't want to exceed

# Maximum count of parallel downloads from OnlyFans site and uploads to telegram
MAX_PARALLEL_DOWNLOADS = 400 
MAX_PARALLEL_UPLOADS = 100

# Keep or Delete media files on server after posting in Telegram
delete_media_from_server = True  #False

# Verify length and format of cookie's values and update user_config.json
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
    with open('user_config.json', 'r') as f:
        config = json.load(f)

    # Update the value
    config[key] = value

    # Write updated config back to file
    with open('user_config.json', 'w') as f:
        json.dump(config, f, indent=4)

    # Update global variable
    globals()[key] = value
