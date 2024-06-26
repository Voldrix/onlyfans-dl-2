import os
import re
import asyncio
import subprocess
import logging
from telethon.errors.rpcerrorlist import MessageNotModifiedError, FloodWaitError
from telethon import TelegramClient, events
from telethon.tl.types import BotCommand, BotCommandScopeDefault
from telethon.tl.functions.bots import SetBotCommandsRequest
from telethon.tl.functions.messages import EditMessageRequest, UpdatePinnedMessageRequest
from config import TELEGRAM_BOT_TOKEN, TELEGRAM_USER_ID, API_ID, API_HASH, CACHE_SIZE_LIMIT, update_config, delete_media_from_server
import aiohttp

# path to main script
ONLYFANS_DL_SCRIPT = 'onlyfans-dl.py'

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

client = TelegramClient('bot', API_ID, API_HASH).start(bot_token=TELEGRAM_BOT_TOKEN)

TELEGRAM_FILE_SIZE_LIMIT = 2 * 1024 * 1024 * 1024  # 2 ГБ
TEXT_MESSAGES = []
USER_MESSAGES = []
processes = {}

LAST_MESSAGE_CONTENT = {}  # keep last message content

async def send_file_and_replace_with_empty(chat_id, file_path, tag):
    file_size = os.path.getsize(file_path)
    if file_size > TELEGRAM_FILE_SIZE_LIMIT:
        msg = await client.send_message(chat_id, f"File {os.path.basename(file_path)} is too large ({file_size / (1024 * 1024):.2f} MB) and won't be sent. {tag}")
        TEXT_MESSAGES.append(msg.id)
    elif file_size > 0:
        await client.send_file(chat_id, file_path, caption=tag)
        if delete_media_from_server:
            with open(file_path, 'w') as f:
                pass  # open in write mode to make file empty

def run_script(args):
    process = subprocess.Popen(['python3', ONLYFANS_DL_SCRIPT] + args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    stdout, stderr = [], []
    for line in iter(process.stdout.readline, ''):
        logger.info(line.strip())
        stdout.append(line.strip())
    for line in iter(process.stderr.readline, ''):
        logger.error(line.strip())
        stderr.append(line.strip())
    process.stdout.close()
    process.stderr.close()
    process.wait()
    return '\n'.join(stdout), '\n'.join(stderr)

def get_cache_size(username):
    total_size = 0
    for dirpath, _, filenames in os.walk(username):
        for filename in filenames:
            file_path = os.path.join(dirpath, filename)
            if not filename.endswith('.part'):
                total_size += os.path.getsize(file_path)
    return total_size

async def fetch_url(session, url, path):
    async with session.get(url) as response:
        with open(path, 'wb') as f:
            while True:
                chunk = await response.content.read(1024)
                if not chunk:
                    break
                f.write(chunk)

async def process_file(file_path, chat_id, tag, pinned_message_id, remaining_files_ref, lock):
    try:
        # get media type and data
        file_name = os.path.basename(file_path)
        if file_name.endswith(('jpg', 'jpeg', 'png')):
            media_type = 'photo'
        elif file_name.endswith('mp4'):
            media_type = 'video'
        elif file_name.endswith('mp3'):
            media_type = 'audio'
        elif file_name.endswith('gif'):
            media_type = 'gif'
        else:
            media_type = 'file'
        
        post_date = file_name.split('_')[0]
        full_tag = f"{tag} #{media_type} {post_date}"

        await send_file_and_replace_with_empty(chat_id, file_path, full_tag)

        # decrease counter of remain media files
        async with lock:
            remaining_files_ref[0] -= 1
            message_content = f"Remaining files to send: {remaining_files_ref[0]}. {tag}"
            await client(EditMessageRequest(
                peer=chat_id,
                id=pinned_message_id,
                message=message_content
            ))
            LAST_MESSAGE_CONTENT[pinned_message_id] = message_content
    except MessageNotModifiedError:
        pass

async def download_and_send_media(username, chat_id, tag, pinned_message_id):
    new_files = []
    total_files = 0
    tasks = []

    process = subprocess.Popen(['python3', ONLYFANS_DL_SCRIPT, username], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    processes[chat_id] = process

    while True:
        output = process.stdout.readline().strip()
        if not output and process.poll() is not None:
            break
        if output:
            logger.info(output)
            if "Downloaded" in output and "new" in output:
                for dirpath, _, filenames in os.walk(username):
                    for filename in filenames:
                        file_path = os.path.join(dirpath, filename)
                        if not filename.endswith('.part') and os.path.getsize(file_path) > 0 and file_path not in new_files:
                            new_files.append(file_path)
                            total_files += 1

    process.stdout.close()
    process.stderr.close()
    del processes[chat_id]

    if not new_files:
        msg = await client.send_message(chat_id, f"No new photos or videos found for this user. {tag}")
        TEXT_MESSAGES.append(msg.id)
        return

    await client(EditMessageRequest(
        peer=chat_id,
        id=pinned_message_id,
        message=f"Total new files to send: {total_files}. {tag}"
    ))
    LAST_MESSAGE_CONTENT[pinned_message_id] = f"Total new files to send: {total_files}. {tag}"

    download_complete_msg = await client.send_message(chat_id, f"Download complete. {tag}")
    TEXT_MESSAGES.append(download_complete_msg.id)

    remaining_files = [total_files]  # use list for changing object
    lock = asyncio.Lock()  # create object Lock for synchronisation

    for file_path in new_files:
        tasks.append(process_file(file_path, chat_id, tag, pinned_message_id, remaining_files, lock))

    await asyncio.gather(*tasks)

    # inform user in chat that upload is complete
    upload_complete_msg = await client.send_message(chat_id, f"Upload complete. {tag}")
    TEXT_MESSAGES.append(upload_complete_msg.id)

async def handle_flood_wait_error(event, wait_time):
    msg = await event.respond(f"FloodWaitError: Please wait for {wait_time} seconds before retrying.")
    USER_MESSAGES.append(msg.id)
    while wait_time > 0:
        print(f"Remaining wait time: {wait_time} seconds")
        await asyncio.sleep(min(wait_time, 60))
        wait_time -= 60

@client.on(events.NewMessage(pattern='/list'))
async def list_command(event):
    if event.sender_id != TELEGRAM_USER_ID:
        msg = await event.respond("Unauthorized access.")
        USER_MESSAGES.append(msg.id)
        logger.warning(f"Unauthorized access denied for {event.sender_id}.")
        return

    stdout, stderr = run_script(['--list'])
    if stderr:
        msg = await event.respond(f"Error: {stderr}")
        USER_MESSAGES.append(msg.id)
    else:
        try:
            with open("subscriptions_list.txt", "r") as f:
                subscriptions = f.readlines()
            if not subscriptions:
                msg = await event.respond("No active subscriptions found.")
                USER_MESSAGES.append(msg.id)
                return
            # print subscription list with numbers and markdown format
            markdown_subs = ''.join([f"{i+1}. `{sub.strip()}`\n" for i, sub in enumerate(subscriptions)])
            msg = await event.respond(markdown_subs, parse_mode='md')
            USER_MESSAGES.append(msg.id)
        except FileNotFoundError:
            msg = await event.respond("Error: subscriptions_list.txt not found.")
            USER_MESSAGES.append(msg.id)


@client.on(events.NewMessage(pattern='/get$'))
async def get_command_usage(event):
    if event.sender_id == TELEGRAM_USER_ID:
        msg = await event.respond("Usage: /get <username or subscription number>")
        USER_MESSAGES.append(msg.id)

@client.on(events.NewMessage(pattern='/get (.+)'))
async def get_command(event):
    if event.sender_id != TELEGRAM_USER_ID:
        msg = await event.respond("Unauthorized access.")
        USER_MESSAGES.append(msg.id)
        logger.warning(f"Unauthorized access denied for {event.sender_id}.")
        return

    target = event.pattern_match.group(1).strip()

    try:
        with open("subscriptions_list.txt", "r") as f:
            subscriptions = f.readlines()
        
        if target.isdigit():
            target_index = int(target) - 1
            if target_index < 0 or target_index >= len(subscriptions):
                raise IndexError
            username = subscriptions[target_index].strip()
            tag = f"#{username}"
        else:
            username = target
            tag = f"#{target}"

        if username not in [sub.strip() for sub in subscriptions]:
            msg = await event.respond(f"User {username} not found in the subscriptions list. {tag}")
            USER_MESSAGES.append(msg.id)
            return
    except (IndexError, FileNotFoundError):
        msg = await event.respond("Invalid subscription number or subscriptions list not found.")
        USER_MESSAGES.append(msg.id)
        return

    if not os.path.exists(username):
        os.makedirs(username)
        msg = await event.respond(f"User directory {username} not found. Starting a fresh download. {tag}")
        USER_MESSAGES.append(msg.id)

    try:
        pinned_message = await event.respond(f"Started downloading media for {username} {tag}")
        TEXT_MESSAGES.append(pinned_message.id)
        pinned_message_id = pinned_message.id
        await client(UpdatePinnedMessageRequest(
            peer=event.chat_id,
            id=pinned_message_id,
            silent=True
        ))

        await download_and_send_media(username, event.chat_id, tag, pinned_message_id)
    except FloodWaitError as e:
        wait_time = e.seconds
        await event.respond(f"FloodWaitError: Please wait for {wait_time} seconds before retrying.")


@client.on(events.NewMessage(pattern='/user_id$'))
async def user_id_command_usage(event):
    if event.sender_id == TELEGRAM_USER_ID:
        msg = await event.respond("Usage: /user_id <new_user_id>")
        TEXT_MESSAGES.append(msg.id)

@client.on(events.NewMessage(pattern='/user_id (.+)'))
async def user_id_command(event):
    if event.sender_id == TELEGRAM_USER_ID:
        user_id = event.pattern_match.group(1).strip()
        try:
            update_config('USER_ID', user_id)
            msg = await event.respond(f"USER_ID updated to: {user_id}")
            TEXT_MESSAGES.append(msg.id)
        except ValueError as e:
            msg = await event.respond(str(e))
            TEXT_MESSAGES.append(msg.id)

@client.on(events.NewMessage(pattern='/user_agent$'))
async def user_agent_command_usage(event):
    if event.sender_id == TELEGRAM_USER_ID:
        msg = await event.respond("Usage: /user_agent <new_user_agent>")
        TEXT_MESSAGES.append(msg.id)

@client.on(events.NewMessage(pattern='/user_agent (.+)'))
async def user_agent_command(event):
    if event.sender_id == TELEGRAM_USER_ID:
        user_agent = event.pattern_match.group(1).strip()
        try:
            update_config('USER_AGENT', user_agent)
            msg = await event.respond(f"USER_AGENT updated to: {user_agent}")
            TEXT_MESSAGES.append(msg.id)
        except ValueError as e:
            msg = await event.respond(str(e))
            TEXT_MESSAGES.append(msg.id)

@client.on(events.NewMessage(pattern='/x_bc$'))
async def x_bc_command_usage(event):
    if event.sender_id == TELEGRAM_USER_ID:
        msg = await event.respond("Usage: /x_bc <new_x_bc>")
        TEXT_MESSAGES.append(msg.id)

@client.on(events.NewMessage(pattern='/x_bc (.+)'))
async def x_bc_command(event):
    if event.sender_id == TELEGRAM_USER_ID:
        x_bc = event.pattern_match.group(1).strip()
        try:
            update_config('X_BC', x_bc)
            msg = await event.respond(f"X_BC updated to: {x_bc}")
            TEXT_MESSAGES.append(msg.id)
        except ValueError as e:
            msg = await event.respond(str(e))
            TEXT_MESSAGES.append(msg.id)

@client.on(events.NewMessage(pattern='/sess_cookie$'))
async def sess_cookie_command_usage(event):
    if event.sender_id == TELEGRAM_USER_ID:
        msg = await event.respond("Usage: /sess_cookie <new_sess_cookie>")
        TEXT_MESSAGES.append(msg.id)

@client.on(events.NewMessage(pattern='/sess_cookie (.+)'))
async def sess_cookie_command(event):
    if event.sender_id == TELEGRAM_USER_ID:
        sess_cookie = event.pattern_match.group(1).strip()
        try:
            update_config('SESS_COOKIE', sess_cookie)
            msg = await event.respond(f"SESS_COOKIE updated to: {sess_cookie}")
            TEXT_MESSAGES.append(msg.id)
        except ValueError as e:
            msg = await event.respond(str(e))
            TEXT_MESSAGES.append(msg.id)

@client.on(events.NewMessage(pattern='/clear'))
async def clear_command(event):
    if event.sender_id == TELEGRAM_USER_ID:
        messages_to_delete = []

        # add identificator to clear this message
        messages_to_delete.append(event.id)

        # get all tracked messages
        messages_to_delete.extend(TEXT_MESSAGES)
        messages_to_delete.extend(USER_MESSAGES)

        # delete traced messages
        await client.delete_messages(event.chat_id, messages_to_delete)

        # clear tracked messages ID's
        TEXT_MESSAGES.clear()
        USER_MESSAGES.clear()

@client.on(events.NewMessage())
async def track_user_messages(event):
    if event.sender_id == TELEGRAM_USER_ID:
        USER_MESSAGES.append(event.id)

@client.on(events.NewMessage(pattern='/stop'))
async def stop_command(event):
    if event.sender_id == TELEGRAM_USER_ID:
        if event.chat_id in processes:
            processes[event.chat_id].terminate()
            processes[event.chat_id].wait()  # Wait for the process to terminate
            del processes[event.chat_id]
            msg = await event.respond("Download stopped.")
            TEXT_MESSAGES.append(msg.id)
        else:
            msg = await event.respond("No active download process found.")
            TEXT_MESSAGES.append(msg.id)

@client.on(events.NewMessage(pattern='/del$'))
async def del_command_usage(event):
    if event.sender_id == TELEGRAM_USER_ID:
        msg = await event.respond("Usage: /del <username or subscription number>")
        USER_MESSAGES.append(msg.id)

@client.on(events.NewMessage(pattern='/del (.+)'))
async def del_command(event):
    if event.sender_id != TELEGRAM_USER_ID:
        msg = await event.respond("Unauthorized access.")
        USER_MESSAGES.append(msg.id)
        logger.warning(f"Unauthorized access denied for {event.sender_id}.")
        return

    target = event.pattern_match.group(1).strip()
    tag = f"#{target}"

    try:
        with open("subscriptions_list.txt", "r") as f:
            subscriptions = f.readlines()
        
        if target.isdigit():
            target_index = int(target) - 1
            if target_index < 0 or target_index >= len(subscriptions):
                raise IndexError
            username = subscriptions[target_index].strip()
        else:
            username = target

        if username not in [sub.strip() for sub in subscriptions]:
            msg = await event.respond(f"User {username} not found in the subscriptions list. {tag}")
            USER_MESSAGES.append(msg.id)
            return
    except (IndexError, FileNotFoundError):
        msg = await event.respond("Invalid subscription number or subscriptions list not found.")
        USER_MESSAGES.append(msg.id)
        return

    # delete user folder from server
    if os.path.exists(username):
        subprocess.call(['rm', '-rf', username])
        msg = await event.respond(f"User directory {username} has been deleted. {tag}")
        USER_MESSAGES.append(msg.id)
    else:
        msg = await event.respond(f"User directory {username} not found. {tag}")
        USER_MESSAGES.append(msg.id)


async def setup_bot_commands():
    commands = [
        BotCommand(command='list', description='Show list of active subscriptions'),
        BotCommand(command='get', description='Download media from username or subscription number'),
        BotCommand(command='user_id', description='Update USER_ID'),
        BotCommand(command='user_agent', description='Update USER_AGENT'),
        BotCommand(command='x_bc', description='Update X_BC'),
        BotCommand(command='sess_cookie', description='Update SESS_COOKIE'),
        BotCommand(command='clear', description='Clear non-media messages'),
        BotCommand(command='stop', description='Stop the download process'),
        BotCommand(command='del', description='Delete user folder by username or subscription number')
    ]
    await client(SetBotCommandsRequest(scope=BotCommandScopeDefault(), lang_code='', commands=commands))

def main():
    loop = asyncio.get_event_loop()
    loop.run_until_complete(setup_bot_commands())
    client.run_until_disconnected()

if __name__ == '__main__':
    main()
