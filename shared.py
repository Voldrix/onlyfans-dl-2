# shared.py
import logging
from aiogram import Bot, Dispatcher
from telethon import TelegramClient

from config import TELEGRAM_BOT_TOKEN, API_KEYS

# Initialize aiogram bot
aiogram_bot = Bot(token=TELEGRAM_BOT_TOKEN)
dp = Dispatcher(aiogram_bot)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

current_api_index = 0
client = TelegramClient('bot', API_KEYS[current_api_index]['API_ID'], API_KEYS[current_api_index]['API_HASH']).start(bot_token=TELEGRAM_BOT_TOKEN)

TEXT_MESSAGES = []
USER_MESSAGES = []

def switch_api_key():
    global current_api_index, client
    current_api_index = (current_api_index + 1) % len(API_KEYS)
    client = TelegramClient('bot', API_KEYS[current_api_index]['API_ID'], API_KEYS[current_api_index]['API_HASH']).start(bot_token=TELEGRAM_BOT_TOKEN)
    logger.info(f"Switched to API key index: {current_api_index}")
