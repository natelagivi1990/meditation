import sys
import unittest

# --- Check SSL module ---
try:
    import ssl
except ImportError:
    print("[ERROR] ssl module is not available in this environment. aiogram requires ssl.")
    print("Please install or enable the ssl module, or use a Python environment that includes it.")
    sys.exit(1)

# --- Check multiprocessing module ---
try:
    import multiprocessing
except ImportError:
    print("[ERROR] _multiprocessing module is missing. APScheduler may require it for ProcessPoolExecutor.")
    print("Please install or enable the multiprocessing module, or use a Python environment that includes it.")
    sys.exit(1)

import asyncio
import time
import json
import os
import logging

from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart
from aiogram.types import (
    Message, CallbackQuery,
    ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton,
    ContentType
)
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

API_TOKEN = "7787463545:AAH6M-_sYua5CsIgr3L1eq1hTuQfWGIynk4"

bot = Bot(token=API_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()
scheduler = AsyncIOScheduler()

STATS_FILE = "stats.json"
MEDITATIONS_FILE = "meditations.json"

user_meditations = {}   # {user_id: [ {title, file_id, type}, ... ]}
user_uploading = {}     # {user_id: {step, file_id, default_title, type}}
user_stats = {}         # {user_id: { 'Общее время':X, 'Медитация1':Y, ... }}
user_active_sessions = {} # {user_id: {start_time, title}}

###########################################################
# JSON LOADING/SAVING
###########################################################
def load_json():
    global user_meditations, user_stats
    if os.path.exists(MEDITATIONS_FILE):
        with open(MEDITATIONS_FILE, "r", encoding="utf-8") as f:
            user_meditations.update(json.load(f))
    if os.path.exists(STATS_FILE):
        with open(STATS_FILE, "r", encoding="utf-8") as f:
            try:
                user_stats.update(json.load(f))
            except json.JSONDecodeError:
                logger.warning("stats.json is corrupted, resetting.")
                user_stats.clear()

def save_json():
    with open(MEDITATIONS_FILE, "w", encoding="utf-8") as f:
        json.dump(user_meditations, f, ensure_ascii=False)
    with open(STATS_FILE, "w", encoding="utf-8") as f:
        json.dump(user_stats, f, ensure_ascii=False)

###########################################################
# KEEP-ALIVE PING
###########################################################
async def keep_alive():
    while True:
        try:
            await bot.get_me()  # простой запрос к Telegram API
            logging.info("✅ Keep-alive ping successful")
        except Exception as e:
            logging.warning(f"⚠️ Keep-alive ping failed: {e}")
        await asyncio.sleep(30)  # каждые 30 секунд

###########################################################
# MAIN
###########################################################
async def main():
    load_json()
    print("✅ Запущен бот (aiogram 3.x).")
    asyncio.create_task(keep_alive())  # запускаем keep-alive
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())


###########################################################
# TESTS
###########################################################
class TestSSLModule(unittest.TestCase):
    def test_ssl_import(self):
        self.assertIsNotNone(ssl)

class TestMultiprocessingModule(unittest.TestCase):
    def test_multiprocessing_import(self):
        self.assertIsNotNone(multiprocessing)

class TestScheduler(unittest.TestCase):
    def test_scheduler_init(self):
        try:
            s = AsyncIOScheduler()
            self.assertIsNotNone(s)
        except Exception as e:
            self.fail(f"Scheduler initialization failed unexpectedly: {e}")
