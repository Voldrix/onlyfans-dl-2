# OnlyFans Profile Downloader / Archiver v2

This tool downloads all photos/videos from OnlyFans profiles, creating a local archive.\
You must be subscribed to the profile to download their content.

onlyfans-dl will create a directory named after the profile in the current working directory.\
A subdirectory structure will be built depending on the options set.\
Any existing media will be skipped, not redownloaded.\
Content will be named as DATE_ID.EXT (e.g. 2021-04-17_123456.jpg)

## Requires

Requires Python3, 'requests' and 'python-dotenv': `python -m pip install -r requirements.txt`

## Features

* Choose what type of content to download (photos, videos, posts, stories, messages, purchases, archived)
* Choose to create subfolders for each of the above, or combine them all into one folder
* Choose to sort posts with more than one photo into "albums" (subfolders)
* Download everything, or only the last &lt;integer&gt; days of content
* Specify multiple profiles at once or use "all" keyword to get subscriptions dynamically

## Usage

First make sure to set your session variables in the environment and configure your options. We recommend copying a .env file from the .env.example file and costumizing it to your needs.

Then execute:

```sh
python onlyfans-dl.py <profiles / all> <max age (optional)>
```

* `<profiles>` - the usernames of profiles to download. Use "all" to get all currently subscribed profiles
* `<max age>` - Optional: Only get posts from the last &lt;integer&gt; days (Messages/Paid not affected)
  * `max age = 0` - sets max age to latest date from the filenames for each profile individually

## Session Variables

You need your browser's __user-agent__, onlyfans **sess**ion cookie, __x-bc__ HTTP header, and __user-id__. Here's how to get them

* Get your browser's user-agent (OF_USER_AGENT) here [ipchicken](https://ipchicken.com/) __You must update this every time your browser updates__
* Session Cookie (OF_SESS_COOKIE)
  * Login to OnlyFans as normal
  * Open the dev console Storage Inspector (`SHIFT+F9` on FireFox). or the __Application__ tab of Chrome DevTools
  * Click Cookies -> <https://onlyfans.com>
  * Copy the value of the `sess` cookie
* x-bc (OF_X_BC) and user-id (OF_USER_ID)
  * Login to OnlyFans, goto home page
  * Open dev console `F12` -> Network tab (`Ctrl+Shift+E` in FireFox)
  * Click __Headers__ sub-tab (default)
  * Click on one of the JSON elements (may need to refresh page) and look under __request headers__ on the right

There are variables for each of these values at the top of the script. Make sure to update them every time you login or your browser updates.

### To-do

* A post with a single photo and video shouldn't be considered an album.
* Allow messages to be limited by age through a separate mechanism/function.
