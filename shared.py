# shared.py
import os
import re
import logging
import sys
from aiogram import Bot, Dispatcher
from telethon import TelegramClient
from config import TELEGRAM_BOT_TOKENS, API_ID, API_HASH, current_bot_index

# Initialize aiogram bot
aiogram_bot = Bot(token=TELEGRAM_BOT_TOKENS[current_bot_index])
dp = Dispatcher(aiogram_bot)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

client = TelegramClient('bot', API_ID, API_HASH).start(bot_token=TELEGRAM_BOT_TOKENS[current_bot_index])

TEXT_MESSAGES = []
USER_MESSAGES = []
LAST_MESSAGE_CONTENT = {}  # store the last content of messages
processes = {}  # Add this line

def switch_bot_token():
    global current_bot_index, client, aiogram_bot, dp
    current_bot_index = (current_bot_index + 1) % len(TELEGRAM_BOT_TOKENS)
    
    # Update current bot index in config file
    with open('config.py', 'r') as f:
        config_content = f.read()
    new_content = re.sub(r'current_bot_index = \d+', f'current_bot_index = {current_bot_index}', config_content)
    with open('config.py', 'w') as f:
        f.write(new_content)
    
    # Remove session files
    if os.path.exists('bot.session'):
        os.remove('bot.session')
    if os.path.exists('bot.session-journal'):
        os.remove('bot.session-journal')
    
    # Restart the bot
    os.execv(sys.executable, ['python3'] + sys.argv)

    logger.info(f"Switched to Bot token index: {current_bot_index}")
