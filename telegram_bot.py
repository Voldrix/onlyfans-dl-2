import os
import re
import math
import time
import asyncio
import subprocess
import requests
import logging
import concurrent.futures
from aiogram import Bot, Dispatcher
from aiogram.types import BotCommand
from aiogram.utils import exceptions as aiogram_exceptions
from telethon.errors.rpcerrorlist import MessageNotModifiedError, FloodWaitError
from telethon import TelegramClient, events
from telethon.tl.types import BotCommand, BotCommandScopeDefault
from telethon.tl.functions.bots import SetBotCommandsRequest
from telethon.tl.functions.messages import EditMessageRequest, UpdatePinnedMessageRequest, DeleteMessagesRequest
from config import TELEGRAM_BOT_TOKEN, TELEGRAM_USER_ID, API_KEYS, CACHE_SIZE_LIMIT, update_config, delete_media_from_server, MAX_PARALLEL_UPLOADS
import aiohttp
from PIL import Image
from moviepy.editor import VideoFileClip

# Initialize aiogram bot
aiogram_bot = Bot(token=TELEGRAM_BOT_TOKEN)
dp = Dispatcher(aiogram_bot)

current_split_process = None
last_flood_wait_message_time = None

# Path to the main script
ONLYFANS_DL_SCRIPT = 'onlyfans-dl.py'

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

current_api_index = 0
client = TelegramClient('bot', API_KEYS[current_api_index]['API_ID'], API_KEYS[current_api_index]['API_HASH']).start(bot_token=TELEGRAM_BOT_TOKEN)

TELEGRAM_FILE_SIZE_LIMIT = 2 * 1024 * 1024 * 1024  # 2 GB
TEXT_MESSAGES = []
USER_MESSAGES = []
processes = {}

LAST_MESSAGE_CONTENT = {}  # store the last content of messages


# Load sent files from sent_files.txt
def load_sent_files(profile_dir):
    sent_files = set()
    sent_files_path = os.path.join(profile_dir, 'sent_files.txt')
    if os.path.exists(sent_files_path):
        with open(sent_files_path, 'r') as f:
            for line in f:
                sent_files.add(line.strip())
    return sent_files

# Save sent files to sent_files.txt
def save_sent_file(profile_dir, file_name):
    sent_files_path = os.path.join(profile_dir, 'sent_files.txt')
    with open(sent_files_path, 'a') as f:
        f.write(file_name + '\n')


async def send_message_with_retry(chat_id, message):
    attempts = 0
    while attempts < 5:
        try:
            msg = await aiogram_bot.send_message(chat_id, message)
            TEXT_MESSAGES.append(msg.message_id)
            break
        except aiogram_exceptions.RetryAfter as e:
            logger.error(f"Target [ID:{chat_id}]: Flood wait of {e.timeout} sec.")
            await asyncio.sleep(e.timeout)
            attempts += 1
        except aiogram_exceptions.TelegramAPIError:
            logger.exception(f"Target [ID:{chat_id}]: failed")
            attempts += 1
            await asyncio.sleep(5)

# Код в начале файла для смены API ключа
def switch_api_key():
    global current_api_index, client
    current_api_index = (current_api_index + 1) % len(API_KEYS)
    client = TelegramClient('bot', API_KEYS[current_api_index]['API_ID'], API_KEYS[current_api_index]['API_HASH']).start(bot_token=TELEGRAM_BOT_TOKEN)
    logger.info(f"Switched to API key index: {current_api_index}")


async def send_file_and_replace_with_empty(chat_id, file_path, tag):
    if 'sent_files.txt' in file_path:
        return
    file_size = os.path.getsize(file_path)
    if file_size > TELEGRAM_FILE_SIZE_LIMIT:
        await split_and_send_large_file(chat_id, file_path, tag)
    elif file_size > 0:
        attempts = 0
        while attempts < 5:
            try:
                msg = await client.send_file(chat_id, file_path, caption=tag)
                USER_MESSAGES.append(msg.id)  # Сохраняем ID сообщения в USER_MESSAGES, а не в TEXT_MESSAGES
                if delete_media_from_server:
                    with open(file_path, 'w') as f:
                        pass  # Открываем в режиме записи, чтобы сделать файл пустым
                break
            except FloodWaitError as e:
                await handle_flood_wait(chat_id, e.seconds)
                attempts += 1
            except ValueError as e:
                logger.error(f"Attempt {attempts + 1}: Failed to send file {file_path}. Error: {str(e)}")
                attempts += 1
                await asyncio.sleep(5)  # Ждем перед повторной попыткой
        else:
            await aiogram_bot.send_message(chat_id, f"Failed to send file {os.path.basename(file_path)} after multiple attempts. {tag}")

# Обработка FloodWaitError
async def handle_flood_wait(chat_id, wait_time):
    global last_flood_wait_message_time
    current_time = time.time()

    if last_flood_wait_message_time is None or current_time - last_flood_wait_message_time > 60:
        last_flood_wait_message_time = current_time
        message = f"FloodWaitError: Please wait for {wait_time} seconds. Switching API key."
        try:
            msg = await aiogram_bot.send_message(chat_id, message)
            TEXT_MESSAGES.append(msg.message_id)
        except aiogram_exceptions.BotBlocked:
            logger.error(f"Target [ID:{chat_id}]: blocked by user")
        except aiogram_exceptions.ChatNotFound:
            logger.error(f"Target [ID:{chat_id}]: invalid user ID")
        except aiogram_exceptions.RetryAfter as e:
            logger.error(f"Target [ID:{chat_id}]: Flood wait of {e.timeout} sec.")
            await asyncio.sleep(e.timeout)
            return await handle_flood_wait(chat_id, wait_time)
        except aiogram_exceptions.TelegramAPIError:
            logger.exception(f"Target [ID:{chat_id}]: failed")
    await asyncio.sleep(wait_time)
    switch_api_key()

def send_fallback_message(chat_id, message):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    data = {
        "chat_id": chat_id,
        "text": message
    }
    response = requests.post(url, data=data)
    if response.status_code != 200:
        logger.error(f"Failed to send fallback message: {response.text}")


def split_video_with_ffmpeg(input_file, output_file, start_time, duration):
    global current_split_process
    command = [
        'ffmpeg', '-y', '-i', input_file,
        '-ss', str(start_time), '-t', str(duration),
        '-c:v', 'libx264', '-preset', 'ultrafast', '-c:a', 'aac', output_file
    ]
    current_split_process = subprocess.Popen(command)
    current_split_process.wait()  # Wait for the process to finish

async def split_and_send_large_file(chat_id, file_path, tag):
    global current_split_process
    video = VideoFileClip(file_path)
    duration = video.duration
    file_size = os.path.getsize(file_path)
    num_parts = math.ceil(file_size / TELEGRAM_FILE_SIZE_LIMIT)
    part_duration = duration / num_parts

    base_name, ext = os.path.splitext(file_path)

    await client.send_message(chat_id, f"Detected large file: {os.path.basename(file_path)}, Size: {file_size/(1024*1024):.2f} MB, Splitting into {num_parts} parts")

    for i in range(num_parts):
        start_time = i * part_duration
        end_time = min(start_time + part_duration, duration)
        part_path = f"{base_name}.part{i + 1}{ext}"

        command = [
            'ffmpeg', '-y', '-i', file_path, '-ss', str(start_time), '-t', str(end_time - start_time),
            '-c:v', 'libx264', '-preset', 'ultrafast', '-threads', '4', '-c:a', 'aac', part_path
        ]

        current_split_process = subprocess.Popen(command)
        current_split_process.wait()  # Wait for the process to finish

        if current_split_process.returncode != 0:  # Check if the process was terminated
            await client.send_message(chat_id, "Splitting process was stopped.")
            break

        await send_file_and_replace_with_empty(chat_id, part_path, f"{tag} Part {i + 1}")
        os.remove(part_path)  # Remove part file after sending

    if delete_media_from_server:
        with open(file_path, 'w') as f:
            pass  # Открываем в режиме записи, чтобы сделать файл пустым
    else:
        os.remove(file_path)  # Удаляем оригинальный большой файл

    current_split_process = None  # Reset the process variable

async def process_large_file(profile_dir, file_path, chat_id, tag, pinned_message_id, remaining_files, lock):
    try:
        await split_and_send_large_file(chat_id, file_path, tag)
        if delete_media_from_server:
            with open(file_path, 'w') as f:
                pass  # Open in write mode to make file empty
        else:
            os.remove(file_path)
    except MessageNotModifiedError:
        pass

@client.on(events.NewMessage(pattern='/get$'))
async def get_command_usage(event):
    if event.sender_id == TELEGRAM_USER_ID:
        msg = await event.respond("Usage: /get <username or subscription number> <max_age (optional)>")
        TEXT_MESSAGES.append(msg.id)

@client.on(events.NewMessage(pattern='/get (.+)'))
async def get_command(event):
    if event.sender_id != TELEGRAM_USER_ID:
        msg = await event.respond("Unauthorized access.")
        USER_MESSAGES.append(msg.id)
        logger.warning(f"Unauthorized access denied for {event.sender_id}.")
        return

    args = event.pattern_match.group(1).strip().split()
    target = args[0]
    max_age = int(args[1]) if len(args) > 1 and args[1].isdigit() else 0
    tag = f"#{target}"

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

        await download_and_send_media(username, event.chat_id, tag, pinned_message_id, max_age, event)
    except FloodWaitError as e:
        wait_time = e.seconds
        await handle_flood_wait(event.chat_id, wait_time)
    except Exception as e:
        await event.respond(f"Unexpected error occurred: {str(e)}")

@client.on(events.NewMessage(pattern='/get_big$'))
async def get_big_command_usage(event):
    if event.sender_id == TELEGRAM_USER_ID:
        msg = await event.respond("Usage: /get_big <username or subscription number>")
        TEXT_MESSAGES.append(msg.id)

@client.on(events.NewMessage(pattern='/get_big (.+)'))
async def get_big_command(event):
    if event.sender_id != TELEGRAM_USER_ID:
        msg = await event.respond("Unauthorized access.")
        USER_MESSAGES.append(msg.id)
        logger.warning(f"Unauthorized access denied for {event.sender_id}.")
        return

    args = event.pattern_match.group(1).strip().split()
    target = args[0]
    max_age = int(args[1]) if len(args) > 1 and args[1].isdigit() else 0
    tag = f"#{target}"

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
        pinned_message = await event.respond(f"Started downloading large media for {username} {tag}")
        TEXT_MESSAGES.append(pinned_message.id)
        pinned_message_id = pinned_message.id
        await client(UpdatePinnedMessageRequest(
            peer=event.chat_id,
            id=pinned_message_id,
            silent=True
        ))

        await download_and_send_large_media(username, event.chat_id, tag, pinned_message_id, max_age, event)
    except FloodWaitError as e:
        wait_time = e.seconds
        await handle_flood_wait(event.chat_id, wait_time)
    except Exception as e:
        await event.respond(f"Unexpected error occurred: {str(e)}")

async def download_and_send_large_media(username, chat_id, tag, pinned_message_id, max_age, event):
    profile_dir = username
    large_files = []
    tasks = []

    command = ['python3', ONLYFANS_DL_SCRIPT, username, str(max_age)]
    global current_split_process
    current_split_process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    processes[chat_id] = current_split_process

    while True:
        output = current_split_process.stdout.readline().strip()
        if not output and current_split_process.poll() is not None:
            break
        if output:
            logger.info(output)
            if "Downloaded" in output and "new" in output:
                for dirpath, _, filenames in os.walk(profile_dir):
                    for filename in filenames:
                        file_path = os.path.join(dirpath, filename)
                        if not filename.endswith('.part') and os.path.getsize(file_path) > 0 and file_path not in large_files and 'sent_files.txt' not in file_path:
                            if os.path.getsize(file_path) > TELEGRAM_FILE_SIZE_LIMIT:
                                large_files.append(file_path)

    current_split_process.stdout.close()
    current_split_process.stderr.close()
    current_split_process = None
    del processes[chat_id]

    if not large_files:
        msg = await client.send_message(chat_id, f"No large files found for this user. {tag}")
        TEXT_MESSAGES.append(msg.id)
        return

    download_complete_msg = await client.send_message(chat_id, f"Download complete. {tag}")
    TEXT_MESSAGES.append(download_complete_msg.id)

    semaphore = asyncio.Semaphore(MAX_PARALLEL_UPLOADS)
    lock = asyncio.Lock()  # Создайте объект Lock для синхронизации
    remaining_files = [len(large_files)]  # Используйте список для изменяемого объекта

    for file_path in large_files:
        tasks.append(upload_with_semaphore(semaphore, process_large_file, profile_dir, file_path, chat_id, tag, pinned_message_id, remaining_files, lock))

    await asyncio.gather(*tasks)

    # inform user in chat that upload is complete
    upload_complete_msg = await client.send_message(chat_id, f"Upload of large files complete. {tag}")
    TEXT_MESSAGES.append(upload_complete_msg.id)

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

async def fetch_url(session, url, path):
    async with session.get(url) as response:
        with open(path, 'wb') as f:
            while True:
                chunk = await response.content.read(1024)
                if not chunk:
                    break
                f.write(chunk)

async def process_file(profile_dir, file_path, chat_id, tag, pinned_message_id, remaining_files_ref, lock):
    try:
        # get media type and data
        file_name = os.path.basename(file_path)
        sent_files = load_sent_files(profile_dir)
        if file_name in sent_files or file_name.startswith('bad-'):
            return

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

        if is_valid_file(file_path):
            await send_file_and_replace_with_empty(chat_id, file_path, full_tag)
            save_sent_file(profile_dir, file_name)
        else:
            os.remove(file_path)

        # decrease counter of remaining media files
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

def get_cache_size(username):
    total_size = 0
    for dirpath, _, filenames in os.walk(username):
        for filename in filenames:
            file_path = os.path.join(dirpath, filename)
            if not filename.endswith('.part'):
                total_size += os.path.getsize(file_path)
    return total_size

def is_valid_file(file_path):
    if file_path.endswith(('jpg', 'jpeg', 'png')):
        try:
            with Image.open(file_path) as img:
                img.verify()
            return True
        except Exception as e:
            logger.error(f"Invalid image file {file_path}: {e}")
            return False
    elif file_path.endswith('mp4'):
        try:
            with VideoFileClip(file_path) as video:
                return video.duration > 1
        except Exception as e:
            logger.error(f"Invalid video file {file_path}: {e}")
            return False
    return True

def estimate_download_size(profile_dir):
    total_size = 0
    for dirpath, _, filenames in os.walk(profile_dir):
        for filename in filenames:
            file_path = os.path.join(dirpath, filename)
            if file_path.lower().endswith(('jpg', 'jpeg', 'png', 'mp4', 'mp3', 'gif')):
                total_size += os.path.getsize(file_path)
    return total_size

async def download_and_send_media(username, chat_id, tag, pinned_message_id, max_age, event):
    profile_dir = username
    new_files = []
    total_files = 0
    large_files = []
    tasks = []

    estimated_size = estimate_download_size(profile_dir)
    if estimated_size > CACHE_SIZE_LIMIT:
        await client.send_message(chat_id, f"Estimated download size ({estimated_size / (1024 * 1024):.2f} MB) exceeds the cache size limit ({CACHE_SIZE_LIMIT / (1024 * 1024):.2f} MB). Please increase the limit or use the max_age parameter to reduce the volume of data.")
        return

    command = ['python3', ONLYFANS_DL_SCRIPT, username, str(max_age)]
    global current_split_process
    current_split_process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    processes[chat_id] = current_split_process

    while True:
        output = current_split_process.stdout.readline().strip()
        if not output and current_split_process.poll() is not None:
            break
        if output:
            logger.info(output)
            if "Downloaded" in output and "new" in output:
                for dirpath, _, filenames in os.walk(profile_dir):
                    for filename in filenames:
                        file_path = os.path.join(dirpath, filename)
                        if not filename.endswith('.part') and os.path.getsize(file_path) > 0 and file_path not in new_files and 'sent_files.txt' not in file_path:
                            if os.path.getsize(file_path) <= TELEGRAM_FILE_SIZE_LIMIT:
                                new_files.append(file_path)
                                total_files += 1
                            else:
                                large_files.append(file_path)

    current_split_process.stdout.close()
    current_split_process.stderr.close()
    current_split_process = None
    del processes[chat_id]

    # Filter out already sent files
    sent_files = load_sent_files(profile_dir)
    new_files = [file for file in new_files if os.path.basename(file) not in sent_files]
    large_files = [file for file in large_files if os.path.basename(file) not in sent_files]
    total_files = len(new_files)

    if not new_files and not large_files:
        msg = await client.send_message(chat_id, f"No new photos or videos found for this user. {tag}")
        TEXT_MESSAGES.append(msg.id)
        return

    try:
        await client(EditMessageRequest(
            peer=chat_id,
            id=pinned_message_id,
            message=f"Total new files to send: {total_files}. {tag}"
        ))
        LAST_MESSAGE_CONTENT[pinned_message_id] = f"Total new files to send: {total_files}. {tag}"
    except FloodWaitError as e:
        wait_time = e.seconds
        await handle_flood_wait_error(event, wait_time)

    download_complete_msg = await client.send_message(chat_id, f"Download complete. {tag}")
    TEXT_MESSAGES.append(download_complete_msg.id)

    remaining_files = [total_files]  # use list for changing object
    lock = asyncio.Lock()  # create object Lock for synchronization

    semaphore = asyncio.Semaphore(MAX_PARALLEL_UPLOADS)

    for file_path in new_files:
        tasks.append(upload_with_semaphore(semaphore, process_file, profile_dir, file_path, chat_id, tag, pinned_message_id, remaining_files, lock))

    await asyncio.gather(*tasks)

    # Notify about large files
    for file_path in large_files:
        file_name = os.path.basename(file_path)
        msg = await client.send_message(chat_id, f"Large file detected: {file_name}. Use /get_big to download.")
        TEXT_MESSAGES.append(msg.id)

    # inform user in chat that upload is complete
    upload_complete_msg = await client.send_message(chat_id, f"Upload complete. {tag}")
    TEXT_MESSAGES.append(upload_complete_msg.id)


async def upload_with_semaphore(semaphore, process_file, *args):
    async with semaphore:
        await process_file(*args)

async def download_media_without_sending(username, chat_id, tag, max_age):
    profile_dir = username
    initial_file_count = 0
    for dirpath, _, filenames in os.walk(profile_dir):
        initial_file_count += len([f for f in filenames if not f.endswith('.part') and 'sent_files.txt' not in f])

    estimated_size = estimate_download_size(profile_dir)
    if estimated_size > CACHE_SIZE_LIMIT:
        await send_message_with_retry(chat_id, f"Estimated download size ({estimated_size / (1024 * 1024):.2f} MB) exceeds the cache size limit ({CACHE_SIZE_LIMIT / (1024 * 1024):.2f} MB). Please increase the limit or use the max_age parameter to reduce the volume of data.")
        return

    command = ['python3', ONLYFANS_DL_SCRIPT, username, str(max_age)]
    global current_split_process
    current_split_process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    processes[chat_id] = current_split_process

    while True:
        output = current_split_process.stdout.readline().strip()
        if not output and current_split_process.poll() is not None:
            break
        if output:
            logger.info(output)

    current_split_process.stdout.close()
    current_split_process.stderr.close()
    current_split_process = None
    del processes[chat_id]

    final_file_count = 0
    for dirpath, _, filenames in os.walk(profile_dir):
        final_file_count += len([f for f in filenames if not f.endswith('.part') and 'sent_files.txt' not in f])

    total_files_downloaded = final_file_count - initial_file_count
    await send_message_with_retry(chat_id, f"Download complete. {total_files_downloaded} files downloaded for {username}. {tag}")


@client.on(events.NewMessage(pattern='/load$'))
async def load_command_usage(event):
    if event.sender_id == TELEGRAM_USER_ID:
        await send_message_with_retry(event.chat_id, "Usage: /load <username or subscription number> <max_age (optional)>")

@dp.message_handler(commands=['load'])
async def load_command(message):
    if message.from_user.id != TELEGRAM_USER_ID:
        await send_message_with_retry(message.chat.id, "Unauthorized access.")
        logger.warning(f"Unauthorized access denied for {message.from_user.id}.")
        return

    args = message.text.split()[1:]
    if not args:
        await send_message_with_retry(message.chat.id, "Usage: /load <username or subscription number> <max_age (optional)>")
        return

    target = args[0]
    max_age = int(args[1]) if len(args) > 1 and args[1].isdigit() else 0
    tag = f"#{target}"

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
            await send_message_with_retry(message.chat.id, f"User {username} not found in the subscriptions list. {tag}")
            return
    except (IndexError, FileNotFoundError):
        await send_message_with_retry(message.chat.id, "Invalid subscription number or subscriptions list not found.")
        return

    if not os.path.exists(username):
        os.makedirs(username)
        await send_message_with_retry(message.chat.id, f"User directory {username} not found. Starting a fresh download. {tag}")

    try:
        await send_message_with_retry(message.chat.id, f"Started downloading media to server for {username} {tag}")
        await download_media_without_sending(username, message.chat.id, tag, max_age)
    except aiogram_exceptions.RetryAfter as e:
        await asyncio.sleep(e.timeout)
        await download_media_without_sending(username, message.chat.id, tag, max_age)


@client.on(events.NewMessage(pattern='/check$'))
async def check_command(event):
    if event.sender_id != TELEGRAM_USER_ID:
        msg = await event.respond("Unauthorized access.")
        USER_MESSAGES.append(msg.id)
        logger.warning(f"Unauthorized access denied for {event.sender_id}.")
        return

    try:
        header = "**__profile (sent/total)__**\n"
        separator = "--------------------------\n"
        response = header + separator  # Adding the header and separator to the response

        with open("subscriptions_list.txt", "r") as f:
            subscriptions = f.readlines()

        for profile in subscriptions:
            profile = profile.strip()
            profile_dir = os.path.join('.', profile)
            if os.path.exists(profile_dir) and os.path.isdir(profile_dir):
                sent_files = load_sent_files(profile_dir)
                total_files = 0
                for root, _, files in os.walk(profile_dir):
                    for file in files:
                        if file != 'sent_files.txt' and file.lower().endswith(('jpg', 'jpeg', 'png', 'mp4', 'mp3', 'gif')):
                            total_files += 1
                response += f"`{profile}` ({len(sent_files)}/**{total_files}**)\n"

        if response.strip() == header + separator:
            msg = await event.respond("No downloaded profiles found.")
            USER_MESSAGES.append(msg.id)
        else:
            msg = await event.respond(response)
            TEXT_MESSAGES.append(msg.id)
    except Exception as e:
        logger.error(f"Error checking profiles: {str(e)}")
        msg = await event.respond("Error checking profiles.")
        USER_MESSAGES.append(msg.id)

@client.on(events.NewMessage(pattern='/erase$'))
async def erase_command_usage(event):
    if event.sender_id == TELEGRAM_USER_ID:
        msg = await event.respond("Usage: /erase <username or subscription number>")
        TEXT_MESSAGES.append(msg.id)

@client.on(events.NewMessage(pattern='/erase (.+)'))
async def erase_command(event):
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

    message_ids_to_delete = []

    for msg_id in TEXT_MESSAGES:
        message = await client.get_messages(event.chat_id, ids=msg_id)
        if message and f"#{username}" in message.message:
            message_ids_to_delete.append(msg_id)

    if message_ids_to_delete:
        try:
            await client.delete_messages(event.chat_id, message_ids_to_delete)
            msg = await event.respond(f"All messages with tag #{username} have been erased.")
            USER_MESSAGES.append(msg.id)
        except Exception as e:
            logger.error(f"Failed to delete messages: {str(e)}")
            msg = await event.respond("Failed to delete messages.")
            USER_MESSAGES.append(msg.id)
    else:
        msg = await event.respond(f"No messages with tag #{username} found.")
        USER_MESSAGES.append(msg.id)

@client.on(events.NewMessage(pattern='/del$'))
async def del_command_usage(event):
    if event.sender_id == TELEGRAM_USER_ID:
        msg = await event.respond("Usage: /del <username or subscription number>")
        TEXT_MESSAGES.append(msg.id)

@client.on(events.NewMessage(pattern='/del (.+)'))
async def del_command(event):
    if event.sender_id != TELEGRAM_USER_ID:
        msg = await event.respond("Unauthorized access.")
        TEXT_MESSAGES.append(msg.id)
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
            TEXT_MESSAGES.append(msg.id)
            return
    except (IndexError, FileNotFoundError):
        msg = await event.respond("Invalid subscription number or subscriptions list not found.")
        TEXT_MESSAGES.append(msg.id)
        return

    # delete user folder from server
    if os.path.exists(username):
        subprocess.call(['rm', '-rf', username])
        msg = await event.respond(f"User directory {username} has been deleted. {tag}")
        TEXT_MESSAGES.append(msg.id)
    else:
        msg = await event.respond(f"User directory {username} not found. {tag}")
        TEXT_MESSAGES.append(msg.id)

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

@client.on(events.NewMessage())
async def track_user_messages(event):
    if event.sender_id == TELEGRAM_USER_ID:
        if not event.message.media:  # Проверяем, что сообщение не содержит медиа
            USER_MESSAGES.append(event.id)
            TEXT_MESSAGES.append(event.id)  # Отслеживаем только текстовые сообщения
        else:
            USER_MESSAGES.append(event.id)  # Отслеживаем все сообщения для удаления по команде /clear

@client.on(events.NewMessage(pattern='/clear'))
async def clear_command(event):
    if event.sender_id == TELEGRAM_USER_ID:
        messages_to_delete = []

        # Добавляем идентификатор, чтобы удалить это сообщение
        messages_to_delete.append(event.id)

        # Удаляем только текстовые сообщения, отслеживаемые в TEXT_MESSAGES
        for msg_id in TEXT_MESSAGES:
            try:
                message = await client.get_messages(event.chat_id, ids=msg_id)
                if message and not message.media:  # Удаляем только текстовые сообщения
                    messages_to_delete.append(msg_id)
            except:
                continue

        # Удаляем отслеживаемые сообщения
        try:
            await client.delete_messages(event.chat_id, messages_to_delete)
        except FloodWaitError as e:
            await handle_flood_wait(event.chat_id, e.seconds)

        # Очищаем отслеживаемые ID сообщений
        TEXT_MESSAGES.clear()
        USER_MESSAGES.clear()
        global last_flood_wait_message_time
        last_flood_wait_message_time = None  # Сбрасываем таймер FloodWaitError

@client.on(events.NewMessage(pattern='/stop'))
async def stop_command(event):
    global current_split_process
    try:
        if event.sender_id == TELEGRAM_USER_ID:
            if current_split_process:
                current_split_process.terminate()
                current_split_process.wait()
                current_split_process = None
                await event.respond("Splitting process stopped.")
            else:
                await event.respond("No splitting process running.")
            # Restart the bot by restarting the script
            os.system("pkill -f telegram_bot.py")  # Kills the script
            os.system("python3 telegram_bot.py &")  # Restarts the script
    except FloodWaitError as e:
        wait_time = e.seconds
        await handle_flood_wait(event.chat_id, wait_time)


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
        TEXT_MESSAGES.append(msg.id)
    else:
        try:
            with open("subscriptions_list.txt", "r") as f:
                subscriptions = f.readlines()
            if not subscriptions:
                msg = await event.respond("No active subscriptions found.")
                TEXT_MESSAGES.append(msg.id)
                return
            # print subscription list with numbers and markdown format
            markdown_subs = ''.join([f"{i+1}. `{sub.strip()}`\n" for i, sub in enumerate(subscriptions)])
            msg = await event.respond(markdown_subs, parse_mode='md')
            TEXT_MESSAGES.append(msg.id)
        except FileNotFoundError:
            msg = await event.respond("Error: subscriptions_list.txt not found.")
            TEXT_MESSAGES.append(msg.id)


async def setup_aiogram_bot_commands(dp: Dispatcher):
    commands = [
        {"command": "list", "description": "Show list of active subscriptions"},
        {"command": "get", "description": "Download media and send to this chat"},
        {"command": "get_big", "description": "Download and send large media files"},
        {"command": "load", "description": "Download media to server without sending"},
        {"command": "check", "description": "Check downloaded profiles and media count"},
        {"command": "erase", "description": "Erase chat messages with a specific hashtag"},
        {"command": "del", "description": "Delete profile folder from server"},
        {"command": "clear", "description": "Clear non-media messages in chat"},
        {"command": "stop", "description": "Stop current process and restart bot"},
        {"command": "user_id", "description": "Update USER_ID"},
        {"command": "user_agent", "description": "Update USER_AGENT"},
        {"command": "x_bc", "description": "Update X_BC"},
        {"command": "sess_cookie", "description": "Update SESS_COOKIE"}
    ]

    await dp.bot.set_my_commands(commands)


async def on_startup(dp):
    await setup_aiogram_bot_commands(dp)

def main():
    loop = asyncio.get_event_loop()
    loop.run_until_complete(setup_bot_commands())
    client.run_until_disconnected()

if __name__ == '__main__':
    from aiogram import executor
    executor.start_polling(dp, skip_updates=True, on_startup=on_startup)
