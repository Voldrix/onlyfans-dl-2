# OnlyFans Profile Downloader / Archiver v3 ([Voldrix](https://github.com/Voldrix/onlyfans-dl-2) fork)
This tool downloads all photos/videos from OnlyFans profiles, creating a local archive.\
You must be subscribed to the profile to download their content.\
Add Telegram Bot to interact with script via messanger's interface (You will need 2 bot (2 BotFather TOKEN) and 1 pair of Telegram App API_ID / API_HASH )

`onlyfans-dl.py` will create a directory named after the profile in the current working directory.\
A subdirectory structure will be built depending on the options set.\
Any existing media will be skipped, not redownloaded.\
Content will be named as DATE_ID.EXT (e.g. 2021-04-17_123456.jpg).\
`telegram_bot.py` will start onlyfans-dl from Telegram and send you downloaded media files.

### Installation Instructions

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
    sudo apt-get install -y python3-venv
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
These commands will help you install all the necessary packages and programs for the correct operation of your script. Make sure you are working in the activated virtual environment to avoid conflicts with system packages.


## Features
* Choose what type of content to download (photos, videos, posts, stories, messages, purchases, archived)
* Choose to create subfolders for each of the above, or combine them all into one folder
* Choose to sort posts with more than one photo into "albums" (subfolders)
* Download everything, or only the last &lt;integer&gt; days of content
* Specify multiple profiles at once or use "all" keyword to get subscriptions dynamically
* You Can use Telegram Bot to interract with script and get media files via messages

## Usage
First make sure to set your session variables in the `config.py` script and configure your options.

To use in command line
`python3 onlyfans-dl.py < --help / --list / profiles / all > < max age (optional) >`
* `<--help>` - print help message
* `<--list>` - print list with usernames of profiles you are subscribed to. 
* `<profiles>` - the usernames of profiles to download. Use "all" to get all currently subscribed profiles
* `<max age>` - Optional: Only get posts from the last &lt;integer&gt; days (Messages/Paid not affected)
  * `max age = 0` - sets max age to latest date from the filenames for each profile individually

To use with Telegram Bot:
`python3 main_tg_bot.py` \
**Notes**: Telegram API not allow fast messeage flood, so telethon can't send all files at once. If you see in pinned message "Remaining files to send: XXX (not 0)" - just rerun /get XXX command.

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

#### ToDo
A post with a single photo and video shouldn't be considered an album.\
Allow messages to be limited by age through a separate mechanism/function.


