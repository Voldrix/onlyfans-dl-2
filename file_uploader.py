import os
import re
import math
import time
import asyncio
import requests
import subprocess
import logging
from PIL import Image
from datetime import datetime
from moviepy.editor import VideoFileClip
from telethon.tl.types import InputFile, InputPhoto, InputMediaUploadedPhoto, InputMediaDocument, InputMediaUploadedDocument, DocumentAttributeVideo
from telethon.errors.rpcerrorlist import FloodWaitError, MessageNotModifiedError
from telethon.tl.functions.messages import UpdatePinnedMessageRequest, EditMessageRequest, DeleteMessagesRequest
from config import *
from aiogram import types
from aiogram.utils import exceptions as aiogram_exceptions
from shared import aiogram_bot, TEXT_MESSAGES, USER_MESSAGES, switch_bot_token, logger, LAST_MESSAGE_CONTENT, processes

last_flood_wait_message_time = None

def is_valid_file(file_path):
    try:
        if not os.path.isfile(file_path):
            logger.error(f"File does not exist: {file_path}")
            return False

        if file_path.endswith(('jpg', 'jpeg', 'png')):
            try:
                with Image.open(file_path) as img:
                    img.verify()
                return True
            except (Image.DecompressionBombError, Image.UnidentifiedImageError) as e:
                logger.error(f"Image file {file_path} is invalid: {e}")
                return False

        elif file_path.endswith(('mp4', 'm4v', 'MOV', 'webm')):
            try:
                with VideoFileClip(file_path) as video:
                    return video.duration > 1
            except Exception as e:
                logger.error(f"Video file {file_path} is invalid: {e}")
                return False

        return True

    except Exception as e:
        logger.error(f"Unexpected error for file {file_path}: {e}")
        return False

async def process_photo_batch(profile_dir, photo_batch, chat_id, tag, pinned_message_id, remaining_files_ref, lock, client):
    media_group = []
    captions = []

    for i, file_path in enumerate(photo_batch):
        try:
            if not is_valid_file(file_path):
                logger.error(f"Invalid file skipped: {file_path}")
                continue

            uploaded_photo = await client.upload_file(file_path)
            media_group.append(InputMediaUploadedPhoto(file=uploaded_photo))

            file_name = os.path.basename(file_path)
            post_date = get_date_from_filename(file_name)
            if not post_date:
                post_date = get_file_creation_date(file_path).strftime('%Y-%m-%d')
            else:
                post_date = post_date.strftime('%Y-%m-%d')

            captions.append(f"{i + 1}. {post_date}")
        except Exception as e:
            logger.error(f"Error processing file {file_path}: {str(e)}")
            continue

    if media_group:
        try:
            caption = f"{tag} #photo\n" + "\n".join(captions)
            await client.send_file(chat_id, media_group, caption=caption)

            for file_path in photo_batch:
                save_sent_file(profile_dir, os.path.basename(file_path))
                if delete_media_from_server:
                    nullify_file(file_path)

            async with lock:
                remaining_files_ref[0] -= len(photo_batch)
                message_content = f"Remaining files to send: {remaining_files_ref[0]}. {tag}"
                await client.edit_message(chat_id, pinned_message_id, message_content)
                LAST_MESSAGE_CONTENT[pinned_message_id] = message_content
        except Exception as e:
            logger.error(f"Failed to send photo batch: {str(e)}")
    else:
        logger.info("No valid photos to send in this batch.")

async def process_video_batch(profile_dir, video_batch, chat_id, tag, pinned_message_id, remaining_files_ref, lock, client):
    media_group = []
    captions = []
    video_batch_size = 0

    for file_path in video_batch:
        try:
            if not is_valid_file(file_path):
                logger.error(f"Invalid file skipped: {file_path}")
                continue

            file_size = os.path.getsize(file_path)
            if video_batch_size + file_size > 100 * 1024 * 1024:
                if media_group:
                    await client.send_file(chat_id, file=media_group, caption=f"{tag} #video\n" + "\n".join(captions), supports_streaming=True)
                    media_group = []
                    captions = []
                    video_batch_size = 0

            uploaded_video = await client.upload_file(file_path)
            duration, width, height = get_video_metadata(file_path)
            thumb_path = create_thumbnail(file_path)

            attributes = [DocumentAttributeVideo(duration=duration, w=width, h=height, supports_streaming=True)]
            media = InputMediaUploadedDocument(
                file=uploaded_video,
                mime_type='video/mp4',
                attributes=attributes,
                thumb=await client.upload_file(thumb_path),
                nosound_video=True
            )

            media_group.append(media)
            file_name = os.path.basename(file_path)
            post_date = get_date_from_filename(file_name)
            if not post_date:
                post_date = get_file_creation_date(file_path).strftime('%Y-%m-%d')
            else:
                post_date = post_date.strftime('%Y-%m-%d')

            captions.append(f"{len(media_group)}. {post_date}")
            video_batch_size += file_size
        except Exception as e:
            logger.error(f"Error processing file {file_path}: {str(e)}")
            continue

    if media_group:
        try:
            await client.send_file(chat_id, file=media_group, caption=f"{tag} #video\n" + "\n".join(captions), supports_streaming=True)

            for file_path in video_batch:
                save_sent_file(profile_dir, os.path.basename(file_path))
                if delete_media_from_server:
                    nullify_file(file_path)
                thumb_path = file_path.replace(".mp4", ".jpg").replace(".m4v", ".jpg").replace(".MOV", ".jpg").replace(".webm", ".jpg")
                if os.path.exists(thumb_path):
                    os.remove(thumb_path)

            async with lock:
                remaining_files_ref[0] -= len(video_batch)
                message_content = f"Remaining files to send: {remaining_files_ref[0]}. {tag}"
                await client.edit_message(chat_id, pinned_message_id, message_content)
                LAST_MESSAGE_CONTENT[pinned_message_id] = message_content
        except Exception as e:
            logger.error(f"Failed to send video batch: {str(e)}")
    else:
        logger.info("No valid videos to send in this batch.")

async def send_existing_media(username, chat_id, tag, pinned_message_id, client):
    profile_dir = username
    new_files = []
    large_files = []
    tasks = []

    for dirpath, _, filenames in os.walk(profile_dir):
        for filename in filenames:
            file_path = os.path.join(dirpath, filename)
            if not filename.endswith('.part') and os.path.getsize(file_path) > 0 and 'sent_files.txt' not in file_path:
                if not is_valid_file(file_path):
                    logger.error(f"Invalid file skipped: {file_path}")
                    continue
                if file_path.endswith(('jpg', 'jpeg', 'png')) and os.path.getsize(file_path) <= TELEGRAM_FILE_SIZE_LIMIT:
                    new_files.append(file_path)
                elif file_path.endswith(('mp4', 'm4v', 'MOV', 'webm')) and os.path.getsize(file_path) <= TELEGRAM_FILE_SIZE_LIMIT:
                    new_files.append(file_path)
                elif os.path.getsize(file_path) > TELEGRAM_FILE_SIZE_LIMIT:
                    large_files.append(file_path)

    sent_files = load_sent_files(profile_dir)
    new_files = [file for file in new_files if os.path.basename(file) not in sent_files]
    large_files = [file for file in large_files if os.path.basename(file) not in sent_files]

    if sort_by_date_not_by_size:
        new_files = sort_files_by_date(new_files)
    else:
        new_files.sort(key=os.path.getsize)

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
    except FloodWait as e:
        await handle_flood_wait(chat_id, e.seconds, client)

    download_complete_msg = await client.send_message(chat_id, f"Download was performed. {tag}")
    TEXT_MESSAGES.append(download_complete_msg.id)

    remaining_files = [total_files]
    lock = asyncio.Lock()
    semaphore = asyncio.Semaphore(MAX_PARALLEL_UPLOADS)

    if merge_media_to_album:
        photo_batch = []
        for file_path in new_files:
            if file_path.endswith(('jpg', 'jpeg', 'png')):
                photo_batch.append(file_path)
                if len(photo_batch) == 10:
                    await process_photo_batch(profile_dir, photo_batch, chat_id, tag, pinned_message_id, remaining_files, lock, client)
                    photo_batch = []

        if photo_batch:
            await process_photo_batch(profile_dir, photo_batch, chat_id, tag, pinned_message_id, remaining_files, lock, client)

        video_batch = []
        video_batch_size = 0

        for file_path in new_files:
            if file_path.endswith(('mp4', 'm4v', 'MOV', 'webm')):
                file_size = os.path.getsize(file_path)
                if video_batch_size + file_size > TELEGRAM_FILE_SIZE_LIMIT:
                    await process_video_batch(profile_dir, video_batch, chat_id, tag, pinned_message_id, remaining_files, lock, client)
                    video_batch = []
                    video_batch_size = 0

                video_batch.append(file_path)
                video_batch_size += file_size

                if len(video_batch) == 10:
                    await process_video_batch(profile_dir, video_batch, chat_id, tag, pinned_message_id, remaining_files, lock, client)
                    video_batch = []
                    video_batch_size = 0

        if video_batch:
            await process_video_batch(profile_dir, video_batch, chat_id, tag, pinned_message_id, remaining_files, lock, client)

    else:
        for file_path in new_files:
            tasks.append(upload_with_semaphore(semaphore, process_file, profile_dir, file_path, chat_id, tag, pinned_message_id, remaining_files, lock, client, delete_media_from_server))

        await asyncio.gather(*tasks)

    for file_path in large_files:
        file_name = os.path.basename(file_path)
        msg = await client.send_message(chat_id, f"Large file detected: {file_name}. Use /get_big to download.")
        TEXT_MESSAGES.append(msg.id)

    upload_complete_msg = await client.send_message(chat_id, f"Upload complete. {tag}")
    TEXT_MESSAGES.append(upload_complete_msg.id)

async def process_large_file(profile_dir, file_path, chat_id, tag, pinned_message_id, remaining_files, lock, client):
    try:
        if not is_valid_file(file_path):
            os.remove(file_path)
            return

        file_size = os.path.getsize(file_path)
        if file_size > TELEGRAM_FILE_SIZE_LIMIT:
            await split_and_send_large_file(chat_id, file_path, tag, client)
        else:
            uploaded_video = await client.upload_file(file_path)
            duration, width, height = get_video_metadata(file_path)
            if duration is None:
                logger.error(f"Skipping invalid video file: {file_path}")
                return

            thumb_path = create_thumbnail(file_path)
            if thumb_path is None:
                logger.error(f"Skipping video file due to thumbnail creation failure: {file_path}")
                return

            file_name = os.path.basename(file_path)
            post_date = get_date_from_filename(file_name)
            if not post_date:
                post_date = get_file_creation_date(file_path).strftime('%Y-%m-%d')
            else:
                post_date = post_date.strftime('%Y-%m-%d')

            attributes = [DocumentAttributeVideo(duration=duration, w=width, h=height, supports_streaming=True)]

            media = InputMediaUploadedDocument(
                file=uploaded_video,
                mime_type='video/mp4',
                attributes=attributes,
                thumb=await client.upload_file(thumb_path),
                nosound_video=True
            )

            attempts = 0
            while attempts < 5:
                try:
                    msg = await client.send_file(chat_id, file=media, caption=f"{tag} #video {post_date}", supports_streaming=True)
                    USER_MESSAGES.append(msg.id)
                    break
                except asyncio.exceptions.TimeoutError:
                    attempts += 1
                    await asyncio.sleep(5)
                except FloodWait as e:
                    await handle_flood_wait(chat_id, e.seconds, client)
                    attempts += 1
                except Exception as e:
                    logger.error(f"Failed to send file {file_path} on attempt {attempts + 1}: {str(e)}")
                    attempts += 1
                    await asyncio.sleep(5)
            else:
                logger.error(f"Failed to send file {file_path} after multiple attempts")
                return

            if delete_media_from_server:
                with open(file_path, 'w') as f:
                    pass

            os.remove(thumb_path)

        save_sent_file(profile_dir, os.path.basename(file_path))

        async with lock:
            remaining_files[0] -= 1
            message_content = f"Remaining files to send: {remaining_files[0]}. {tag}"
            await client(EditMessageRequest(
                peer=chat_id,
                id=pinned_message_id,
                message=message_content
            ))
            LAST_MESSAGE_CONTENT[pinned_message_id] = message_content
    except MessageNotModifiedError:
        pass
    except Exception as e:
        logger.error(f"Failed to process large file {file_path}: {str(e)}")

async def process_file(profile_dir, file_path, chat_id, tag, pinned_message_id, remaining_files_ref, lock, client, delete_media_from_server):
    try:
        file_name = os.path.basename(file_path)
        sent_files = load_sent_files(profile_dir)
        if file_name in sent_files or file_name.startswith('bad-'):
            return

        if file_name.endswith(('jpg', 'jpeg', 'png')):
            media_type = 'photo'
        elif file_name.endswith(('mp4', 'm4v', 'MOV', 'webm')):
            media_type = 'video'
        elif file_name.endswith('mp3'):
            media_type = 'audio'
        elif file_name.endswith('gif'):
            media_type = 'gif'
        else:
            media_type = 'file'

        post_date = get_date_from_filename(file_name)
        if not post_date:
            post_date = get_file_creation_date(file_path).strftime('%Y-%m-%d')
        else:
            post_date = post_date.strftime('%Y-%m-%d')

        full_tag = f"{tag} #{media_type} {post_date}"

        if is_valid_file(file_path):
            try:
                if file_name.endswith(('mp4', 'm4v', 'MOV', 'webm')):
                    thumb_path = create_thumbnail(file_path)
                    media = InputMediaUploadedDocument(
                        file=await client.upload_file(file_path),
                        mime_type='video/mp4',
                        attributes=[DocumentAttributeVideo(duration=get_video_metadata(file_path)[0], w=1920, h=1080, supports_streaming=True)],
                        thumb=await client.upload_file(thumb_path),
                        nosound_video=True
                    )
                    msg = await client.send_file(chat_id, file=media, caption=full_tag, supports_streaming=True)
                    os.remove(thumb_path)
                else:
                    await send_file_and_replace_with_empty(chat_id, file_path, full_tag, client)
                save_sent_file(profile_dir, file_name)
            except Exception as e:
                logger.error(f"Failed to send file {file_path}: {e}")
        else:
            logger.error(f"Invalid file skipped: {file_path}")
            os.remove(file_path)

        async with lock:
            remaining_files_ref[0] -= 1
            message_content = f"Remaining files to send: {remaining_files_ref[0]}. {tag}"
            await client.edit_message(chat_id, pinned_message_id, message_content)
            LAST_MESSAGE_CONTENT[pinned_message_id] = message_content
    except MessageNotModifiedError:
        pass
    except Exception as e:
        logger.error(f"Failed to process file {file_path}: {str(e)}")


async def send_existing_large_media(username, chat_id, tag, pinned_message_id, client):
    profile_dir = username
    large_files = []
    tasks = []

    for dirpath, _, filenames in os.walk(profile_dir):
        for filename in filenames:
            file_path = os.path.join(dirpath, filename)
            if not filename.endswith('.part') and os.path.getsize(file_path) > 0 and 'sent_files.txt' not in file_path:
                if os.path.getsize(file_path) > TELEGRAM_FILE_SIZE_LIMIT:
                    large_files.append(file_path)

    sent_files = load_sent_files(profile_dir)
    large_files = [file for file in large_files if os.path.basename(file) not in sent_files]

    if not large_files:
        msg = await client.send_message(chat_id, f"No large files found for this user. {tag}")
        TEXT_MESSAGES.append(msg.id)
        return

    download_complete_msg = await client.send_message(chat_id, f"Download complete. {tag}")
    TEXT_MESSAGES.append(download_complete_msg.id)

    semaphore = asyncio.Semaphore(MAX_PARALLEL_UPLOADS)
    lock = asyncio.Lock()
    remaining_files = [len(large_files)]

    for file_path in large_files:
        tasks.append(upload_with_semaphore(semaphore, process_large_file, profile_dir, file_path, chat_id, tag, pinned_message_id, remaining_files, lock, client))

    await asyncio.gather(*tasks)

    upload_complete_msg = await client.send_message(chat_id, f"Upload of large files complete. {tag}")
    TEXT_MESSAGES.append(upload_complete_msg.id)


def split_video_with_ffmpeg(input_file, output_file, start_time, duration):
    global current_split_process
    command = [
        'ffmpeg', '-y', '-i', input_file,
        '-ss', str(start_time), '-t', str(duration),
        '-c:v', 'libx264', '-preset', 'ultrafast', '-c:a', 'aac', output_file
    ]
    current_split_process = subprocess.Popen(command)
    current_split_process.wait()
    
async def split_and_send_large_file(chat_id, file_path, tag, client):
    global current_split_process
    try:
        video = VideoFileClip(file_path)
        duration = video.duration
        file_size = os.path.getsize(file_path)
        num_parts = math.ceil(file_size / TELEGRAM_FILE_SIZE_LIMIT)
        part_duration = duration / num_parts

        base_name, ext = os.path.splitext(file_path)

        post_date = get_date_from_filename(os.path.basename(file_path))
        if not post_date:
            post_date = get_file_creation_date(file_path).strftime('%Y-%m-%d')
        else:
            post_date = post_date.strftime('%Y-%m-%d')

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
            current_split_process.wait()

            if current_split_process.returncode != 0:
                await client.send_message(chat_id, "Splitting process was stopped.")
                break

            if not is_valid_file(part_path):
                logger.error(f"Invalid part file skipped: {part_path}")
                continue

            thumb_path = create_thumbnail(part_path)
            media = InputMediaUploadedDocument(
                file=await client.upload_file(part_path),
                mime_type='video/mp4',
                attributes=[DocumentAttributeVideo(duration=part_duration, w=video.size[0], h=video.size[1], supports_streaming=True)],
                thumb=await client.upload_file(thumb_path),
                nosound_video=True
            )

            await client.send_file(chat_id, file=media, caption=f"{tag} Part {i + 1} #video {post_date}", supports_streaming=True)
            os.remove(part_path)
            os.remove(thumb_path)

        if delete_media_from_server:
            with open(file_path, 'w') as f:
                pass

        current_split_process = None
    except Exception as e:
        logger.error(f"Error in splitting and sending large file {file_path}: {str(e)}")


async def send_file_and_replace_with_empty(chat_id, file_path, tag, client):
    try:
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
                    USER_MESSAGES.append(msg.id)
                    if delete_media_from_server:
                        nullify_file(file_path)
                    break
                except FloodWaitError as e:
                    await handle_flood_wait(chat_id, e.seconds, client)
                    attempts += 1
                except ValueError as e:
                    logger.error(f"Attempt {attempts + 1}: Failed to send file {file_path}. Error: {str(e)}")
                    attempts += 1
                    await asyncio.sleep(5)
            else:
                await client.send_message(chat_id, f"Failed to send file {os.path.basename(file_path)} after multiple attempts. {tag}")
    except Exception as e:
        logger.error(f"Error in sending file {file_path}: {str(e)}")

    

def get_video_metadata(file_path):
    try:
        video = VideoFileClip(file_path)
        duration = int(video.duration)
        width, height = video.size
        return duration, width, height
    except Exception as e:
        logger.error(f"Error getting video metadata for {file_path}: {e}")
        return None, None, None

def create_thumbnail(file_path):
    try:
        video = VideoFileClip(file_path)
        thumb_path = file_path.replace(".mp4", ".jpg").replace(".m4v", ".jpg").replace(".MOV", ".jpg").replace(".webm", ".jpg")
        video.save_frame(thumb_path, t=1.0)
        return thumb_path
    except Exception as e:
        logger.error(f"Error creating thumbnail for {file_path}: {e}")
        return None


def nullify_file(file_path):
    with open(file_path, 'w') as f:
        pass

def send_fallback_message(chat_id, message):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKENS[current_bot_index]}/sendMessage"
    data = {
        "chat_id": chat_id,
        "text": message
    }
    response = requests.post(url, data=data)
    if response.status_code != 200:
        logger.error(f"Failed to send fallback message: {response.text}")

async def handle_flood_wait(chat_id, wait_time, client):
    message = f"FloodWaitError: A wait of {wait_time} seconds is required. Please use /switch to switch to another bot."
    try:
        await client.send_message(chat_id, message)
    except FloodWaitError:
        send_fallback_message(chat_id, message)
    except Exception as e:
        send_fallback_message(chat_id, f"Error handling FloodWait: {str(e)}")

async def handle_too_many_requests(chat_id, response, client):
    retry_after = response.json().get("parameters", {}).get("retry_after", 60)
    message = f"Too Many Requests: retry after {retry_after} seconds. Please use /switch to switch to another bot."
    try:
        await client.send_message(chat_id, message)
    except FloodWaitError:
        send_fallback_message(chat_id, message)
    except Exception as e:
        send_fallback_message(chat_id, f"Error handling Too Many Requests: {str(e)}")

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
        except (asyncio.exceptions.TimeoutError, aiohttp.ClientError, aiogram_exceptions.TelegramAPIError):
            logger.exception(f"Target [ID:{chat_id}]: failed on attempt {attempts + 1}")
            attempts += 1
            await asyncio.sleep(5)

def load_sent_files(profile_dir):
    sent_files_path = os.path.join(profile_dir, 'sent_files.txt')
    if not os.path.exists(sent_files_path):
        return set()
    with open(sent_files_path, 'r') as f:
        sent_files = set(line.strip() for line in f if line.strip() and not line.startswith('sent_files.txt'))
    return sent_files

def save_sent_file(profile_dir, file_name):
    sent_files_path = os.path.join(profile_dir, 'sent_files.txt')
    with open(sent_files_path, 'a') as f:
        f.write(file_name + '\n')

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


def estimate_download_size(profile_dir):
    total_size = 0
    for dirpath, _, filenames in os.walk(profile_dir):
        for filename in filenames:
            if filename.lower().endswith(('jpg', 'jpeg', 'png', 'mp4', 'm4v', 'MOV', 'webm', 'mp3', 'gif')):
                total_size += os.path.getsize(os.path.join(dirpath, filename))
    return total_size

def get_file_creation_date(file_path):
    return datetime.fromtimestamp(os.path.getctime(file_path))

def get_date_from_filename(file_name):
    date_part = file_name.split('_')[0]
    if re.match(r'\d{4}-\d{2}-\d{2}', date_part):
        try:
            return datetime.strptime(date_part, '%Y-%m-%d').date()
        except ValueError:
            return None
    return None

def is_resolution_string(string):
    parts = string.split('x')
    if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
        return True
    return False


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

def count_files(profile_dir):
    total_files = 0
    for dirpath, _, filenames in os.walk(profile_dir):
        total_files += len([f for f in filenames if not f.endswith('.part') and 'sent_files.txt' not in f])
    return total_files

def total_files_estimated(profile_dir, max_age):
    command = ['python3', ONLYFANS_DL_SCRIPT, profile_dir, str(max_age)]
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    total_files = 0
    while True:
        output = process.stdout.readline().strip()
        if not output and process.poll() is not None:
            break
        if output:
            logger.info(output)
            if "Downloaded" in output and "new" in output:
                total_files += int(output.split()[1])
    return total_files
