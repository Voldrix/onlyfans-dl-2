# config.py
#==========================================#
# ↓↓↓↓↓↓↓↓↓↓↓↓ DO NOT TOUCH IT ↓↓↓↓↓↓↓↓↓↓↓↓#
#==========================================#
import re
import logging
from user_config import *
from system_config import *

# path to script onlyfans-dl.py
ONLYFANS_DL_SCRIPT = 'onlyfans-dl.py'

# Maximum size of file that Telegram can handle (do not change it)
TELEGRAM_FILE_SIZE_LIMIT = 2000 * 1024 * 1024

# Current active bot index (do not change it)
current_bot_index = 0

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
#==========================================#
# ↑↑↑↑↑↑↑↑↑↑↑↑ DO NOT TOUCH IT ↑↑↑↑↑↑↑↑↑↑↑↑#
#==========================================#
