# OnlyFans Profile Downloader / Archiver v3 ([Voldrix](https://github.com/Voldrix/onlyfans-dl-2) fork)

## Disclaimer
This script is for educational purposes only. Please respect the content creators' rights and only use the downloaded content for personal use. Do not share or distribute the content without the creator's consent.
OnlyFans is a registered trademark of Fenix International Limited. The contributors of this script isn't in any way affiliated with, sponsored by, or endorsed by Fenix International Limited. The contributors of this script are not responsible for the end users' actions.

## About
This tool downloads all photos/videos from OnlyFans profiles, creating a local archive.\
You must be subscribed to the profile to download their content.\
Add Telegram Bot to interact with script via messanger's interface (You will need 2 bot (2 BotFather TOKEN) and 1 pair of Telegram App API_ID / API_HASH )

`onlyfans-dl.py` will create a directory named after the profile in the current working directory.\
A subdirectory structure will be built depending on the options set.\
Any existing media will be skipped, not redownloaded.\
Content will be named as DATE_ID.EXT (e.g. 2021-04-17_123456.jpg).\
`main_tg_bot.py` will start onlyfans-dl from Telegram and send you downloaded media files.

### Prerequisites (example for APT packet manager)
   ```bash
   sudo apt-get install git
   ```
   ```bash
   git clone https://github.com/chelaxian/onlyfans-dl-3
   cd onlyfans-dl-3
   ```
### Quick Start Instructions for Ubuntu/Debian-like OS

   ```bash
   sudo chmod 777 *.sh
   ```
    
   ```bash
   ./INSTALL.sh
   ```

   ```bash
   ./SETUP.sh
   ```
    
   ```bash
   ./RUN.sh
   ```
    
### Manual Installation Instructions (example for APT packet manager)

To set up the environment and install necessary dependencies, follow these steps:

1. **Update the package list:**

    ```bash
    sudo apt-get update
    ```

2. **Install `ffmpeg`:**

    ```bash
    sudo apt-get install -y ffmpeg
    ```

3. **Install `python3-venv` for creating virtual environments:**

    ```bash
    sudo apt-get install -y python3 python3-pip python3-venv
    ```

4. **Create a virtual environment (if not already created):**

    ```bash
    python3 -m venv myenv
    ```

5. **Activate the virtual environment:**

    ```bash
    source myenv/bin/activate
    ```

6. **Upgrade `pip`:**

    ```bash
    pip install --upgrade pip
    ```

7. **Install dependencies from `requirements.txt`:**

    ```bash
    pip install -r requirements.txt
    ```
8. **Fill in `user_config.py` file with your actual values:**
    ```bash
    USER_ID = "xxx"
    USER_AGENT = "xxx"
    X_BC = "xxx"
    SESS_COOKIE = "xxx"
    TELEGRAM_BOT_TOKENS = ["xxx", "yyy"]
    API_ID = 'xxx'
    API_HASH = 'xxx'
    TELEGRAM_USER_ID = xxx
    ```

 9. **If you are advanced user you can also edit `system_config.py` file to change some script parameters. Do not touch `config.py` file**

## Features
* Choose what type of content to download (photos, videos, posts, stories, messages, purchases, archived)
* Choose to create subfolders for each of the above, or combine them all into one folder
* Choose to sort posts with more than one photo into "albums" (subfolders)
* Download everything, or only the last &lt;integer&gt; days of content
* Specify multiple profiles at once or use "all" keyword to get subscriptions dynamically
* You Can use Telegram Bot to interract with script and get media files via messages

## Run & Usage
First make sure to set your session variables in the `user_config.py` script and configure your options.

To use in command line
`python3 onlyfans-dl.py < --help / --list / profiles / all > < max age (optional) >`
* `<--help>` - print help message
* `<--list>` - print list with usernames of profiles you are subscribed to. 
* `<profiles>` - the usernames of profiles to download. Use "all" to get all currently subscribed profiles
* `<max age>` - Optional: Only get posts from the last &lt;integer&gt; days (Messages/Paid not affected)
* `max age = 0` - sets max age to latest date from the filenames for each profile individually

To use with Telegram Bot:

`source myenv/bin/activate` \
`python3 main_tg_bot.py` 

## Description of Telegram Bot Commands
* `/list`: Show the list of active subscriptions.
* `/load`: Download media files to the server without sending to the chat.
* `/check`: Check downloaded profiles and media file count.
* `/get`: Download media files and send them to this chat.
* `/get_big`: Download and send large media files.
* `/clear`: Clear the chat of non-media messages.
* `/del`: Delete the profile folder from the server.
* `/switch`: Switch to the next bot token.
* `/restart`: Stop the current process and restart the bot.
* `/user_id`: Update USER_ID.
* `/user_agent`: Update USER_AGENT.
* `/x_bc`: Update X_BC.
* `/sess_cookie`: Update SESS_COOKIE.
* `/erase`: Erase chat messages with a specific hashtag.

**Notes**: Telegram API not allow fast messeage flood, so telegram bot can't send all files at once. If you see message "FloodWaitError: A wait of XXX seconds is required." - just use `/switch` to switch to your second BotFather bot.

## Session Variables
You need your browser's __user-agent__, onlyfans **sess**ion cookie, __x-bc__ HTTP header, and **user-id**. Here's how to get them

- Get your browser's user-agent here [ipchicken](https://ipchicken.com/) __You must update this every time your browser updates__
- Session Cookie
  - Login to OnlyFans as normal
  - Open the dev console Storage Inspector (`SHIFT+F9` on FireFox). or the __Application__ tab of Chrome DevTools
  - Click Cookies -> https://onlyfans.com
  - Copy the value of the `sess` cookie
- x-bc and user-id
  - Login to OnlyFans, goto home page
  - Open dev console `F12` -> Network tab (`Ctrl+Shift+E` in FireFox)
  - Click __Headers__ sub-tab (default)
  - Click on one of the JSON elements (may need to refresh page) and look under __request headers__ on the right

There are variables for each of these values at the top of the script. Make sure to update them every time you login or your browser updates.

## Obtaining API ID and Hash (and BotFather token)
* Go to my.telegram.org.
* Log in with your phone number and login code.
* Go to the API development tools section.
* Create a new application and obtain the api_id and api_hash.
* For BotFather bot and token use telegram bot - [@BotFather](https://t.me/BotFather)

#### ToDo
A post with a single photo and video shouldn't be considered an album.\
Allow messages to be limited by age through a separate mechanism/function.


