# OnlyFans Profile Downloader / Archiver v2

- [OnlyFans Profile Downloader / Archiver v2](#onlyfans-profile-downloader--archiver-v2)
  - [About](#about)
  - [Requirements](#requirements)
  - [Features](#features)
  - [ToDo](#todo)
  - [Usage](#usage)
  - [Session Variables](#session-variables)
  - [Contributing](#contributing)

## About

This tool downloads all photos/videos from an OnlyFans profile that you are subscribed to, creating a local archive.

onlyfans-dl will create a directory named after the profile in the current working directory.

A subdirectory structure will be built depending on the options set.

Any existing media will be skipped, not redownloaded.

Content will be named as DATE_ID.EXT (e.g. 2021-04-17_123456.jpg)

## Requirements

Requires Python3 and 'requests': `python -m pip install requests`

## Features

- Choose what type of content to download (photos, videos, posts, stories, messages, purchases, archived)
- Choose to create subfolders for each of the above, or combine them all into one folder
- Choose to sort posts with more than one photo into "albums" (subfolders)
- Download everything, or only the last \<integer> days of content
- Specify multiple profiles at once or use "all" keyword to get subscriptions dynamically

## ToDo

- A post with a single photo and video shouldn't be considered an album.
- Allow messages to be limited by age through a separate mechanism/function.

## Usage

First make sure to set your session variables in the script and configure your options.

`./onlyfans-dl.py <profiles / all> [optional: max age (integer)]`

- `<profiles>` - the usernames of profiles to download. Use "all" to get all currently subscribed profiles
- `[max age]` - Optional: Only get posts from the last \<integer> days (Messages/Paid not affected)

## Session Variables

Requests to the API now need to be signed. This is an obfuscation technique from the developers to discourage scraping. Thanks for the most recent patch goes to [DIGITALCRIMINAL](https://github.com/DIGITALCRIMINAL/OnlyFans).

You need your browser's __user-agent__, onlyfans **sess**ion cookie, __x-bc__ HTTP header, and __user-id__. Here's how to get them

- Get your browser's user-agent here [ipchicken](https://ipchicken.com/) (You must update this every time your browser updates)

- Session Cookie:
  - Login to OnlyFans as normal
  - Open the dev console Storage Inspector (`SHIFT+F9` on FireFox) or the __Application__ tab of Chrome DevTools
  - Click Cookies -> `https://onlyfans.com`
  - Copy the value of the `sess` cookie

- x-bc and user-id:
  - Login to OnlyFans, go to the home page
  - Open dev console `F12` -> Network tab (`Ctrl+Shift+E` in FireFox)
  - Click __Headers__ sub-tab (default)
  - Click on one of the JSON elements (may need to refresh page) and look under __request headers__ on the right

There are variables for each of these values at the top of the script, make sure to update them every time you login or your browser updates.

## Contributing

PRs are welcome; be sure to take some time to familiarize yourself with OnlyFans' API if you would like to extend/modify the functionality of this script.
