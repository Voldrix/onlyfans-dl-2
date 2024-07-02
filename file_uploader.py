# file_uploader.py
import os
import re
import math
import time
import asyncio
import subprocess
import logging
from PIL import Image
from moviepy.editor import VideoFileClip
from telethon.errors.rpcerrorlist import FloodWaitError, MessageNotModifiedError
from telethon.tl.functions.messages import UpdatePinnedMessageRequest, EditMessageRequest, DeleteMessagesRequest
from config import *
from aiogram.utils import exceptions as aiogram_exceptions
from shared import aiogram_bot, TEXT_MESSAGES, USER_MESSAGES, switch_bot_token, logger, LAST_MESSAGE_CONTENT, processes  # Add processes here


# Остальной код без изменений


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

def load_sent_files(profile_dir):
    sent_files = set()
    sent_files_path = os.path.join(profile_dir, 'sent_files.txt')
    if os.path.exists(sent_files_path):
        with open(sent_files_path, 'r') as f:
            for line in f:
                sent_files.add(line.strip())
    return sent_files

def save_sent_file(profile_dir, file_name):
    sent_files_path = os.path.join(profile_dir, 'sent_files.txt')
    with open(sent_files_path, 'a') as f:
        f.write(file_name + '\n')

async def handle_flood_wait(chat_id, wait_time, client):
    global last_flood_wait_message_time
    current_time = time.time()

    if last_flood_wait_message_time is None or current_time - last_flood_wait_message_time > 60:
        last_flood_wait_message_time = current_time
        message = f"FloodWaitError: Please wait for {wait_time} seconds. Switching bot token."
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
            return await handle_flood_wait(chat_id, wait_time, client)
        except aiogram_exceptions.TelegramAPIError:
            logger.exception(f"Target [ID:{chat_id}]: failed")
    await asyncio.sleep(wait_time)
    switch_bot_token()

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
            if filename.lower().endswith(('jpg', 'jpeg', 'png', 'mp4', 'mp3', 'gif')):
                total_size += os.path.getsize(os.path.join(dirpath, filename))
    return total_size

async def send_file_and_replace_with_empty(chat_id, file_path, tag, client):
    if 'sent_files.txt' in file_path:
        return
    file_size = os.path.getsize(file_path)
    if file_size > TELEGRAM_FILE_SIZE_LIMIT:
        await split_and_send_large_file(chat_id, file_path, tag, client)
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
                await handle_flood_wait(chat_id, e.seconds, client)
                attempts += 1
            except ValueError as e:
                logger.error(f"Attempt {attempts + 1}: Failed to send file {file_path}. Error: {str(e)}")
                attempts += 1
                await asyncio.sleep(5)  # Ждем перед повторной попыткой
        else:
            await aiogram_bot.send_message(chat_id, f"Failed to send file {os.path.basename(file_path)} after multiple attempts. {tag}")

def split_video_with_ffmpeg(input_file, output_file, start_time, duration):
    global current_split_process
    command = [
        'ffmpeg', '-y', '-i', input_file,
        '-ss', str(start_time), '-t', str(duration),
        '-c:v', 'libx264', '-preset', 'ultrafast', '-c:a', 'aac', output_file
    ]
    current_split_process = subprocess.Popen(command)
    current_split_process.wait()  # Wait for the process to finish

async def split_and_send_large_file(chat_id, file_path, tag, client):
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

        await send_file_and_replace_with_empty(chat_id, part_path, f"{tag} Part {i + 1}", client)
        os.remove(part_path)  # Remove part file after sending

    if delete_media_from_server:
        with open(file_path, 'w') as f:
            pass  # Открываем в режиме записи, чтобы сделать файл пустым
    else:
        os.remove(file_path)  # Удаляем оригинальный большой файл

    current_split_process = None  # Reset the process variable

async def process_large_file(profile_dir, file_path, chat_id, tag, pinned_message_id, remaining_files, lock, client):
    try:
        await split_and_send_large_file(chat_id, file_path, tag, client)
        if delete_media_from_server:
            with open(file_path, 'w') as f:
                pass  # Open in write mode to make file empty
        else:
            os.remove(file_path)
    except MessageNotModifiedError:
        pass

async def process_file(profile_dir, file_path, chat_id, tag, pinned_message_id, remaining_files_ref, lock, client):
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
            await send_file_and_replace_with_empty(chat_id, file_path, full_tag, client)
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

async def upload_with_semaphore(semaphore, process_file, *args):
    async with semaphore:
        await process_file(*args)

async def download_and_send_media(username, chat_id, tag, pinned_message_id, max_age, event, client):
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
        await handle_flood_wait(event.chat_id, wait_time, client)

    download_complete_msg = await client.send_message(chat_id, f"Download complete. {tag}")
    TEXT_MESSAGES.append(download_complete_msg.id)

    remaining_files = [total_files]  # use list for changing object
    lock = asyncio.Lock()  # create object Lock for synchronization

    semaphore = asyncio.Semaphore(MAX_PARALLEL_UPLOADS)

    for file_path in new_files:
        tasks.append(upload_with_semaphore(semaphore, process_file, profile_dir, file_path, chat_id, tag, pinned_message_id, remaining_files, lock, client))

    await asyncio.gather(*tasks)

    # Notify about large files
    for file_path in large_files:
        file_name = os.path.basename(file_path)
        msg = await client.send_message(chat_id, f"Large file detected: {file_name}. Use /get_big to download.")
        TEXT_MESSAGES.append(msg.id)

    # inform user in chat that upload is complete
    upload_complete_msg = await client.send_message(chat_id, f"Upload complete. {tag}")
    TEXT_MESSAGES.append(upload_complete_msg.id)

async def download_and_send_large_media(username, chat_id, tag, pinned_message_id, max_age, event, client):
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
        tasks.append(upload_with_semaphore(semaphore, process_large_file, profile_dir, file_path, chat_id, tag, pinned_message_id, remaining_files, lock, client))

    await asyncio.gather(*tasks)

    # inform user in chat that upload is complete
    upload_complete_msg = await client.send_message(chat_id, f"Upload of large files complete. {tag}")
    TEXT_MESSAGES.append(upload_complete_msg.id)

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
