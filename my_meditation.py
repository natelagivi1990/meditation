import asyncio
import time
import json
import os
from aiogram import Bot, Dispatcher, F, types
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart
from aiogram.types import (
    ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton
)
from aiogram.client.default import DefaultBotProperties
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from datetime import datetime

API_TOKEN = 'твой_токен_сюда'

bot = Bot(token=API_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()
scheduler = AsyncIOScheduler()

# === ФАЙЛЫ ===
STATS_FILE = "stats.json"
MEDITATIONS_FILE = "meditations.json"
REMINDERS_FILE = "reminders.json"

# === ДАННЫЕ ===
user_stats = {}
user_meditations = {}
user_active_sessions = {}
user_uploading = {}
user_reminders = {}

# === ХРАНИЛКИ ===
def load_json():
    global user_stats, user_meditations, user_reminders
    if os.path.exists(STATS_FILE):
        with open(STATS_FILE, "r") as f:
            user_stats = json.load(f)
    if os.path.exists(MEDITATIONS_FILE):
        with open(MEDITATIONS_FILE, "r") as f:
            user_meditations = json.load(f)
    if os.path.exists(REMINDERS_FILE):
        with open(REMINDERS_FILE, "r") as f:
            user_reminders = json.load(f)

def save_json():
    with open(STATS_FILE, "w") as f:
        json.dump(user_stats, f)
    with open(MEDITATIONS_FILE, "w") as f:
        json.dump(user_meditations, f)
    with open(REMINDERS_FILE, "w") as f:
        json.dump(user_reminders, f)

# === UI ===
def main_keyboard():
    return ReplyKeyboardMarkup(resize_keyboard=True, keyboard=[
        [KeyboardButton(text="🧘 Начать медитацию")],
        [KeyboardButton(text="📥 Загрузить медитацию")],
        [KeyboardButton(text="📊 Статистика")],
    ])

CATEGORY_OPTIONS = InlineKeyboardMarkup(
    inline_keyboard=[
        [InlineKeyboardButton(text="Диспенза", callback_data="cat_Диспенза")],
        [InlineKeyboardButton(text="Дыхательные", callback_data="cat_Дыхательные")],
    ]
)

# === СТАРТ ===
@dp.message(CommandStart())
async def start_handler(message: types.Message):
    await message.answer(
        "Привет! Я бот для медитаций 🧘‍♂️\n\n"
        "Ты можешь:\n— Загружать медитации\n— Выбирать категорию\n— Устанавливать напоминания",
        reply_markup=main_keyboard()
    )

# === ЗАГРУЗКА ===
@dp.message(F.text == "📥 Загрузить медитацию")
async def start_upload(message: types.Message):
    user_id = str(message.from_user.id)
    user_uploading[user_id] = {"step": "wait_file"}
    await message.answer("Отправь медитацию (mp3/mp4 файл)")

@dp.message(F.audio | F.video | F.document)
async def handle_file(message: types.Message):
    user_id = str(message.from_user.id)
    if user_id not in user_uploading or user_uploading[user_id]["step"] != "wait_file":
        return

    file = message.audio or message.video or message.document
    if not file.mime_type or ("audio" not in file.mime_type and "video" not in file.mime_type):
        await message.answer("⛔ Только аудио или видео файлы")
        return

    user_uploading[user_id].update({
        "step": "wait_title",
        "file_id": file.file_id,
        "default_title": file.file_name or "Без названия",
        "duration": file.duration or 0,
        "type": "audio" if "audio" in file.mime_type else "video"
    })
    await message.answer(f"Название файла: {file.file_name}\nНапиши своё название или отправь 'Оставить'")

@dp.message(F.text)
async def handle_upload_steps(message: types.Message):
    user_id = str(message.from_user.id)
    data = user_uploading.get(user_id)

    if not data:
        return

    # Название
    if data["step"] == "wait_title":
        title = message.text.strip()
        if title.lower() == "оставить":
            title = data["default_title"]
        data["title"] = title
        data["step"] = "wait_category"
        await message.answer("Выбери категорию:", reply_markup=CATEGORY_OPTIONS)
        return

@dp.callback_query(F.data.startswith("cat_"))
async def choose_category(callback: types.CallbackQuery):
    user_id = str(callback.from_user.id)
    data = user_uploading.get(user_id)

    if not data or data["step"] != "wait_category":
        return

    category = callback.data.replace("cat_", "")
    meditation = {
        "title": data["title"],
        "category": category,
        "file_id": data["file_id"],
        "duration": data["duration"],
        "type": data["type"]
    }

    user_meditations.setdefault(user_id, []).append(meditation)
    user_uploading.pop(user_id)
    save_json()

    await callback.message.answer(f"✅ Медитация <b>{meditation['title']}</b> добавлена в категорию {category}", reply_markup=main_keyboard())
    await callback.answer()

# === СТАРТ МЕДИТАЦИИ ===
@dp.message(F.text == "🧘 Начать медитацию")
async def choose_category_start(message: types.Message):
    await message.answer("🧘 Выбери категорию медитаций:", reply_markup=CATEGORY_OPTIONS)

@dp.callback_query(F.data.startswith("cat_"))
async def show_meditations_by_category(callback: types.CallbackQuery):
    user_id = str(callback.from_user.id)
    category = callback.data.replace("cat_", "")
    meditations = [m for m in user_meditations.get(user_id, []) if m["category"] == category]

    if not meditations:
        await callback.message.answer("Нет медитаций в этой категории.")
        await callback.answer()
        return

    buttons = [
        [InlineKeyboardButton(text="▶️ " + m["title"], callback_data=f"start_{i}"),
         InlineKeyboardButton(text="🗑", callback_data=f"delete_{i}")]
        for i, m in enumerate(user_meditations[user_id]) if m["category"] == category
    ]
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)

    await callback.message.answer(f"📄 Медитации категории <b>{category}</b>:", reply_markup=keyboard)
    await callback.answer()

@dp.callback_query(F.data.startswith("start_"))
async def start_meditation(callback: types.CallbackQuery):
    user_id = str(callback.from_user.id)
    index = int(callback.data.replace("start_", ""))
    meditation = user_meditations[user_id][index]

    user_active_sessions[user_id] = {
        "start": time.time(),
        "title": meditation["title"]
    }

    if meditation["type"] == "audio":
        await callback.message.answer_audio(meditation["file_id"], caption=f"▶️ {meditation['title']}")
    else:
        await callback.message.answer_video(meditation["file_id"], caption=f"▶️ {meditation['title']}")

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="✅ Завершить медитацию", callback_data="end_meditation")]]
    )
    await callback.message.answer("Нажми кнопку, когда завершишь 👇", reply_markup=keyboard)
    await callback.answer()

@dp.callback_query(F.data == "end_meditation")
async def end_session(callback: types.CallbackQuery):
    user_id = str(callback.from_user.id)
    session = user_active_sessions.pop(user_id, None)

    if not session:
        await callback.message.answer("⛔ Нет активной медитации.")
        return

    duration = max(1, int((time.time() - session["start"]) / 60))
    user_stats.setdefault(user_id, {})
    user_stats[user_id]["Общее время"] = user_stats[user_id].get("Общее время", 0) + duration
    user_stats[user_id][session["title"]] = user_stats[user_id].get(session["title"], 0) + duration
    save_json()

    await callback.message.answer(f"✅ Медитация завершена. Засчитано: <b>{duration}</b> минут", reply_markup=main_keyboard())
    await callback.answer()

# === УДАЛЕНИЕ ===
@dp.callback_query(F.data.startswith("delete_"))
async def delete_meditation(callback: types.CallbackQuery):
    user_id = str(callback.from_user.id)
    index = int(callback.data.replace("delete_", ""))
    meditation = user_meditations[user_id].pop(index)
    save_json()
    await callback.message.answer(f"🗑 Удалено: <b>{meditation['title']}</b>")
    await callback.answer()

# === СТАТИСТИКА ===
@dp.message(F.text == "📊 Статистика")
async def stats(message: types.Message):
    user_id = str(message.from_user.id)
    stats = user_stats.get(user_id, {})
    if not stats:
        await message.answer("Пока нет статистики.")
        return

    text = "📊 <b>Твоя статистика:</b>\n"
    for name, mins in stats.items():
        text += f"— {name}: {mins} мин\n"
    await message.answer(text)

# === НАПОМИНАНИЯ ===
@dp.message(F.text.startswith("/напомни"))
async def set_reminder(message: types.Message):
    user_id = str(message.from_user.id)
    parts = message.text.split()
    if len(parts) != 2 or ":" not in parts[1]:
        await message.reply("⏰ Используй так: /напомни 20:30")
        return

    hour, minute = map(int, parts[1].split(":"))
    user_reminders[user_id] = {"hour": hour, "minute": minute}
    save_json()

    scheduler.add_job(
        send_reminder,
        CronTrigger(hour=hour, minute=minute),
        args=[user_id],
        id=f"reminder_{user_id}",
        replace_existing=True
    )
    await message.reply(f"✅ Буду напоминать каждый день в {hour:02d}:{minute:02d} 🙏")

async def send_reminder(user_id):
    try:
        await bot.send_message(user_id, "🌙 Пора медитировать, как и обещал 🙏")
    except:
        pass

# === ЗАПУСК ===
async def main():
    load_json()
    for user_id, r in user_reminders.items():
        scheduler.add_job(
            send_reminder,
            CronTrigger(hour=r["hour"], minute=r["minute"]),
            args=[user_id],
            id=f"reminder_{user_id}",
            replace_existing=True
        )
    scheduler.start()
    print("✅ Бот запущен")
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())
