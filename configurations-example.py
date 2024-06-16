######################
# CONFIGURATIONS     #
######################

#Session Variables (update every time you login or your browser updates)
# USER_ID aka auth_id coockie
USER_ID = ""
USER_AGENT = ""
# X_BC aka fp
X_BC = ""
SESS_COOKIE = ""

#0 = do not print file names or api calls
#1 = print filenames only when max_age is set
#2 = always print filenames
#3 = print api calls
#4 = print skipped files that already exist
VERBOSITY = 2
#Download Directory. Uses CWD if null
DL_DIR = ''
#List of accounts to skip
ByPass = ['']

#Separate photos into subdirectories by post/album (Single photo posts are not put into subdirectories)
ALBUMS = True
#Use content type subfolders (messgaes/archived/stories/purchased), or download everything to /profile/photos and /profile/videos
USE_SUB_FOLDERS = True

#Content types to download
VIDEOS = True
PHOTOS = True
AUDIO = True
POSTS = True
STORIES = True
MESSAGES = True
ARCHIVED = True
PURCHASED = True

######################
# END CONFIGURATIONS #
######################