import sys
import unittest

# --- Check SSL module ---
try:
    import ssl
except ImportError:
    print("[ERROR] ssl module is not available in this environment. aiogram requires ssl.")
    sys.exit(1)

# --- Check multiprocessing module ---
try:
    import multiprocessing
except ImportError:
    print("[ERROR] _multiprocessing module is missing. APScheduler may require it for ProcessPoolExecutor.")
    sys.exit(1)

import asyncio
import time
import json
import os
import logging

from aiogram import Bot, Dispatcher, F
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart
from aiogram.types import (
    Message, CallbackQuery,
    ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton,
    ContentType,
    Update
)
from aiohttp import web

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

API_TOKEN = "7787463545:AAH6M-_sYua5CsIgr3L1eq1hTuQfWGIynk4"
WEBHOOK_PATH = "/webhook"
WEBHOOK_PORT = int(os.environ.get("PORT", 8000))
WEBHOOK_URL = f"https://{os.environ.get('RENDER_EXTERNAL_HOSTNAME')}{WEBHOOK_PATH}"

bot = Bot(token=API_TOKEN, parse_mode=ParseMode.HTML)
from aiogram import Router

router = Router()

dp = Dispatcher()
dp.include_router(router)
scheduler = AsyncIOScheduler()

STATS_FILE = "stats.json"
MEDITATIONS_FILE = "meditations.json"

user_meditations = {}
user_uploading = {}
user_stats = {}
user_active_sessions = {}

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
# BASIC HANDLERS
@router.message(CommandStart())
async def cmd_start(message: Message):
    await message.answer("Привет! Бот работает через webhook.")


# WEBHOOK SERVER SETUP
###########################################################
async def handle_webhook(request):
    body = await request.text()
    update = Update.model_validate_json(body)
    await dp.feed_update(bot, update)
    return web.Response()

async def main():
    load_json()
    print("✅ Запущен бот (aiogram 3.x) через webhook.")

    app = web.Application()
    app.router.add_post(WEBHOOK_PATH, handle_webhook)

    # Устанавливаем webhook
    await bot.set_webhook(WEBHOOK_URL)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", WEBHOOK_PORT)
    await site.start()

    # Бесконечное ожидание (не завершать main)
    while True:
        await asyncio.sleep(3600)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        print("❌ Бот остановлен")

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
