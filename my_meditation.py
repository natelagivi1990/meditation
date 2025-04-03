
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
# KEYBOARDS
###########################################################
def universal_keyboard():
    """
    Универсальное меню (нижнее): «Загрузить медитацию», «Статистика», «Меню»
    """
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📥 Загрузить медитацию"), KeyboardButton(text="📊 Статистика")],
            [KeyboardButton(text="Меню")]
        ],
        resize_keyboard=True
    )

###########################################################
# HANDLERS
###########################################################

@dp.message(CommandStart())
async def cmd_start(message: Message):
    """
    /start — привет, инструкция, основной экран
    """
    user_id = str(message.from_user.id)
    await message.answer("Добро пожаловать в бот для медитаций!")

    await asyncio.sleep(5)

    instructions = (
        "<b>Инструкция</b>:\n"
        "1) Расположитесь удобно\n"
        "2) Нажмите на нужную медитацию, бот начнёт отсчёт\n"
        "3) По завершении медитации нажмите 'Завершить'\n"
        "4) В статистике увидите общее время (и по каждой медитации).\n"
    )
    await message.answer(instructions, reply_markup=universal_keyboard())

    meditations = user_meditations.get(user_id, [])
    if meditations:
        buttons = []
        for i, m in enumerate(meditations):
            buttons.append([
                InlineKeyboardButton(text="▶️ " + m["title"], callback_data=f"start_{i}"),
                InlineKeyboardButton(text="🗑", callback_data=f"delete_{i}")
            ])
        kb = InlineKeyboardMarkup(inline_keyboard=buttons)
        await message.answer("🧘‍♂️ Выбери медитацию:", reply_markup=kb)
    else:
        await message.answer(
            "У тебя ещё нет загруженных медитаций. "
            "Используй '📥 Загрузить медитацию', чтобы добавить."
        )

@dp.message(F.text == "Меню")
async def show_menu(message: Message):
    """Показываем тот же стартовый список медитаций и инструкции заново (или коротко)."""
    user_id = str(message.from_user.id)
    meditations = user_meditations.get(user_id, [])

    await message.answer("Главное меню", reply_markup=universal_keyboard())

    if not meditations:
        await message.answer(
            "У тебя ещё нет загруженных медитаций. "
            "Используй '📥 Загрузить медитацию', чтобы добавить."
        )
    else:
        buttons = []
        for i, m in enumerate(meditations):
            buttons.append([
                InlineKeyboardButton(text="▶️ " + m["title"], callback_data=f"start_{i}"),
                InlineKeyboardButton(text="🗑", callback_data=f"delete_{i}")
            ])
        kb = InlineKeyboardMarkup(inline_keyboard=buttons)
        await message.answer("🧘‍♂️ Выбери медитацию:", reply_markup=kb)

@dp.message(F.text == "📥 Загрузить медитацию")
async def upload_menu(message: Message):
    """
    Начало загрузки медитации
    """
    user_id = str(message.from_user.id)
    user_uploading[user_id] = {"step": "wait_file"}
    await message.answer(
        "Отправь медитацию (mp3/mp4 файл)",
        reply_markup=universal_keyboard()
    )

@dp.message(F.text == "📊 Статистика")
async def show_stats(message: Message):
    user_id = str(message.from_user.id)
    stats = user_stats.get(user_id, {})

    if not stats:
        await message.answer("Пока нет статистики.", reply_markup=universal_keyboard())
        return

    overall = stats.get("Общее время", 0)
    text = "📊 <b>Твоя статистика</b>:\n"
    for t, val in stats.items():
        if t == "Общее время":
            continue
        text += f"— {t}: {val} мин\n"
    text += f"\nВсего (по всем медитациям): {overall} мин"

    await message.answer(text, reply_markup=universal_keyboard())

@dp.message()
async def handle_uploading_text(message: Message):
    """Обработка текста при загрузке медитации (название)."""
    user_id = str(message.from_user.id)
    data = user_uploading.get(user_id)
    if not data or data.get("step") != "wait_file":
        # не в режиме ожидания файла
        return

    # Если юзер прислал не файл, а текст, скажем "Введите файл"
    await message.answer(
        "Пожалуйста, отправь MP3/MP4 файл. Или нажми 'Меню'"
    )

###########################################################
# ПРИНИМАЕМ ФАЙЛ (mp3/mp4) => НАЗВАНИЕ => СОХРАНЕНИЕ
###########################################################

@dp.message(F.content_type.in_([ContentType.AUDIO, ContentType.VIDEO, ContentType.DOCUMENT]))
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
        default_title = message.audio.file_name if message.audio.file_name else "Unnamed"
    elif message.video:
        file_id = message.video.file_id
        file_type = "video"
        default_title = message.video.file_name if message.video.file_name else "Unnamed"
    else:
        fname = message.document.file_name.lower()
        if fname.endswith(".mp3"):
            file_type = "audio"
        elif fname.endswith(".mp4"):
            file_type = "video"
        file_id = message.document.file_id
        default_title = message.document.file_name

    if not file_id or not file_type:
        await message.answer("Файл не подходит (нужен mp3/mp4).", reply_markup=universal_keyboard())
        return

    # Сохраняем
    entry = {
        "title": default_title,
        "file_id": file_id,
        "type": file_type
    }
    user_meditations.setdefault(user_id, []).append(entry)
    save_json()

    user_uploading.pop(user_id, None)

    await message.answer(
        f"✅ Медитация <b>{default_title}</b> успешно загружена!",
        reply_markup=universal_keyboard()
    )

###########################################################
# СТАРТ / ЗАВЕРШИТЬ МЕДИТАЦИЮ
###########################################################
@dp.callback_query(F.data.startswith("start_"))
async def on_start_meditation(callback: CallbackQuery):
    user_id = str(callback.from_user.id)
    index = int(callback.data.replace("start_", ""))
    meditation = user_meditations[user_id][index]

    user_active_sessions[user_id] = {
        "start_time": time.time(),
        "title": meditation["title"]
    }

    finish_btn = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="✅ Завершить", callback_data=f"end_{index}")]]
    )

    # Определяем тип
    if meditation["type"] == "audio":
        await callback.message.answer_audio(
            meditation["file_id"],
            caption=f"▶️ {meditation['title']}",
            reply_markup=finish_btn
        )
    elif meditation["type"] == "video":
        await callback.message.answer_video(
            meditation["file_id"],
            caption=f"▶️ {meditation['title']}",
            reply_markup=finish_btn
        )
    else:
        await callback.message.answer(
            "🌬 Это дыхательная практика.\nЧтобы выполнить её, введи: /дыхание",
            reply_markup=finish_btn
        )

    await callback.answer()

@dp.callback_query(F.data.startswith("end_"))
async def on_end_meditation(callback: CallbackQuery):
    user_id = str(callback.from_user.id)
    session = user_active_sessions.pop(user_id, None)
    if not session:
        await callback.message.answer("Нет активной сессии.")
        await callback.answer()
        return

    total_sec = time.time() - session["start_time"]
    duration = max(1, int(total_sec // 60))
    title = session["title"]

    user_stats.setdefault(user_id, {})
    user_stats[user_id].setdefault(title, 0)
    user_stats[user_id][title] += duration

    user_stats[user_id].setdefault("Общее время", 0)
    user_stats[user_id]["Общее время"] += duration

    save_json()

    await callback.message.answer(
        f"✅ Медитация <b>{title}</b> завершена, добавлено {duration} мин.\n"
        "Выбирай следующую или загружай новые медитации!",
        reply_markup=universal_keyboard()
    )

    meditations = user_meditations.get(user_id, [])
    if not meditations:
        await callback.message.answer(
            "У тебя ещё нет загруженных медитаций. "
            "Используй '📥 Загрузить медитацию', чтобы добавить."
        )
    else:
        buttons = []
        for i, m in enumerate(meditations):
            buttons.append([
                InlineKeyboardButton(text="▶️ " + m["title"], callback_data=f"start_{i}"),
                InlineKeyboardButton(text="🗑", callback_data=f"delete_{i}")
            ])
        kb = InlineKeyboardMarkup(inline_keyboard=buttons)
        await callback.message.answer("🧘‍♂️ Выбери медитацию:", reply_markup=kb)

    await callback.answer()

###########################################################
# УДАЛЕНИЕ
###########################################################
@dp.callback_query(F.data.startswith("delete_"))
async def on_delete_meditation(callback: CallbackQuery):
    user_id = str(callback.from_user.id)
    index = int(callback.data.replace("delete_", ""))
    med = user_meditations[user_id].pop(index)
    save_json()
    await callback.message.answer(f"🗑 Удалено: <b>{med['title']}</b>")
    await callback.answer()

###########################################################
# MAIN
###########################################################
async def main():
    load_json()
    print("✅ Запущен бот (aiogram 3.x).")
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
