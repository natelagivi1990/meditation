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
    print("[WARNING] _multiprocessing module is missing. APScheduler may require it for ProcessPoolExecutor. Skipping scheduler.")
    multiprocessing = None

import asyncio
import time
import json
import os
import logging

from aiogram import Bot, Dispatcher, F, Router
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

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

API_TOKEN = "7787463545:AAH6M-_sYua5CsIgr3L1eq1hTuQfWGIynk4"
WEBHOOK_PATH = "/webhook"
WEBHOOK_PORT = int(os.environ.get("PORT", 8000))
WEBHOOK_URL = f"https://{os.environ.get('RENDER_EXTERNAL_HOSTNAME')}{WEBHOOK_PATH}"

bot = Bot(token=API_TOKEN, parse_mode=ParseMode.HTML)
router = Router()
dp = Dispatcher(bot=bot)
dp.include_router(router)

STATS_FILE = "stats.json"
MEDITATIONS_FILE = "meditations.json"

user_meditations = {}
user_uploading = {}
user_stats = {}
user_active_sessions = {}

###########################################################
# KEYBOARDS
def main_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📥 Загрузить медитацию")],
            [KeyboardButton(text="📊 Статистика"), KeyboardButton(text="🏠 Меню")]
        ],
        resize_keyboard=True
    )


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
@router.message(F.text == "🏠 Меню")
async def cmd_start(message: Message):
    user_id = str(message.from_user.id)
    await message.answer("Добро пожаловать в бот для медитаций!", reply_markup=main_keyboard())

    meditations = user_meditations.get(user_id, [])
    if meditations:
        buttons = []
        for i, m in enumerate(meditations):
            buttons.append([
                InlineKeyboardButton(text="▶️ " + m["title"], callback_data=f"start_{i}"),
            ])
            buttons[-1].append(InlineKeyboardButton(text="🗑", callback_data=f"delete_{i}"))
        kb = InlineKeyboardMarkup(inline_keyboard=buttons)
        await message.answer("🧘‍♂️ Выбери медитацию:", reply_markup=kb)
    else:
        await message.answer("У тебя ещё нет загруженных медитаций. Используй '📥 Загрузить медитацию'.")


# ЗАГРУЗКА МЕДИТАЦИЙ
@router.message(F.text == "📥 Загрузить медитацию")
async def upload_menu(message: Message):
    user_id = str(message.from_user.id)
    user_uploading[user_id] = {"step": "wait_file"}
    await message.answer("Отправь медитацию (mp3/mp4 файл)")

@router.message(F.content_type.in_([ContentType.AUDIO, ContentType.VIDEO, ContentType.DOCUMENT]))
async def on_file_received(message: Message):
    user_id = str(message.from_user.id)
    data = user_uploading.get(user_id)
    if not data or data["step"] != "wait_file":
        return

    file_id = None
    file_type = None

    if message.audio:
        file_id = message.audio.file_id
        file_type = "audio"
        default_title = message.audio.file_name or "Unnamed"
    elif message.video:
        file_id = message.video.file_id
        file_type = "video"
        default_title = message.video.file_name or "Unnamed"
    elif message.document:
        fname = message.document.file_name.lower()
        if fname.endswith(".mp3"):
            file_type = "audio"
        elif fname.endswith(".mp4"):
            file_type = "video"
        file_id = message.document.file_id
        default_title = message.document.file_name

    if not file_id or not file_type:
        await message.answer("Файл не подходит (нужен mp3/mp4).", reply_markup=main_keyboard())
        return

    user_uploading[user_id].update({
        "file_id": file_id,
        "type": file_type,
        "default_title": default_title,
        "step": "wait_title"
    })

    await message.answer(
        f"Файл получен: <b>{default_title}</b>\n\n"
        "Если хочешь переименовать — напиши новое имя.\n"
        "Если оставить как есть, просто отправь 1.",
        parse_mode=ParseMode.HTML
    )

@router.message()
async def handle_file_rename(message: Message):
    user_id = str(message.from_user.id)
    data = user_uploading.get(user_id)
    if not data or data.get("step") != "wait_title":
        return

    if message.text.strip() == "1":
        title = data["default_title"]
    else:
        title = message.text.strip()

    entry = {
        "title": title,
        "file_id": data["file_id"],
        "type": data["type"]
    }

    user_meditations.setdefault(user_id, []).append(entry)
    save_json()
    user_uploading.pop(user_id, None)

    await message.answer(f"✅ Медитация <b>{title}</b> успешно загружена!", reply_markup=main_keyboard())

# СТАТИСТИКА
@router.message(F.text == "📊 Статистика")
async def show_stats(message: Message):
    user_id = str(message.from_user.id)
    stats = user_stats.get(user_id, {})
    if not stats:
        await message.answer("Пока нет статистики.")
        return

    overall = stats.get("Общее время", 0)
    text = "📊 <b>Твоя статистика</b>:\n"
    for t, val in stats.items():
        if t == "Общее время":
            continue
        text += f"— {t}: {val} мин\n"
    text += f"\nВсего (по всем медитациям): {overall} мин"

    await message.answer(text, parse_mode=ParseMode.HTML)


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
        loop = asyncio.get_event_loop()
        loop.run_until_complete(main())
    except (KeyboardInterrupt, SystemExit):
        print("❌ Бот остановлен")

###########################################################
# TESTS
###########################################################
class TestSSLModule(unittest.TestCase):
    def test_ssl_import(self):
        self.assertIsNotNone(ssl)

class TestScheduler(unittest.TestCase):
    def test_scheduler_init(self):
        if multiprocessing is None:
            self.skipTest("multiprocessing is not available")
        try:
            from apscheduler.schedulers.asyncio import AsyncIOScheduler
            s = AsyncIOScheduler()
            self.assertIsNotNone(s)
        except Exception as e:
            self.fail(f"Scheduler initialization failed unexpectedly: {e}")
