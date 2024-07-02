
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
