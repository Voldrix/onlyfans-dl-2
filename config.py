import re

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
ALBUMS = True
# Use content type subfolders (messages/archived/stories/purchased), or download everything to /profile/photos and /profile/videos
USE_SUB_FOLDERS = True

# Content types to download
VIDEOS = True
PHOTOS = True
AUDIO = True
POSTS = True
STORIES = True
MESSAGES = True
ARCHIVED = True
PURCHASED = True

# Telegram Bot Token
TELEGRAM_BOT_TOKEN = "xxx"

# Your Telegram ID (to restrict access to bot only from your account)
TELEGRAM_USER_ID = xxx

# Your Telegram API apps (because standard BotFather bot has 50mb limit of sended files)
API_KEYS = [
    {'API_ID': 'xxx1', 'API_HASH': 'xxx1'},
    {'API_ID': 'xxx2', 'API_HASH': 'xxx2'},
    # Добавьте столько пар, сколько необходимо
]


# Size of disk space buffer you want to use on your server for temporary media saving
CACHE_SIZE_LIMIT = 10000 * 1024 * 1024  # limit to your free disk space on server you don't want to exceed
TELEGRAM_FILE_SIZE_LIMIT = 2 * 1024 * 1024 * 1024  # 2 GB
ONLYFANS_DL_SCRIPT = 'onlyfans-dl.py'

# Maximum count of parallel downloads from OnlyFans site and uploads to telegram
MAX_PARALLEL_DOWNLOADS = 400 
MAX_PARALLEL_UPLOADS = 100

# Keep or Delete media files on server after posting in Telegram
delete_media_from_server = True  # or False

# Verify lenght and format of cookie's values
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
