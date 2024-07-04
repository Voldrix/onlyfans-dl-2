# system_config.py

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

# Size of disk space buffer you want to use on your server for temporary media saving
CACHE_SIZE_LIMIT = 25000 * 1024 * 1024

# Maximum count of parallel downloads from OnlyFans site and uploads to telegram (do not change it if no need)
MAX_PARALLEL_DOWNLOADS = 400 
MAX_PARALLEL_UPLOADS = 100

# Keep or Delete media files on server after posting in Telegram
delete_media_from_server = True  #False
