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

API_TOKEN = 'твой_токен_сюда'

bot = Bot(token=API_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

# === ФАЙЛЫ ===
STATS_FILE = "stats.json"
MEDITATIONS_FILE = "meditations.json"

# === ДАННЫЕ ===
user_stats = {}         # user_id -> {"Общее время": 35, "название": 10, ...}
user_meditations = {}   # user_id -> список медитаций
user_active_sessions = {}  # user_id -> start_time
user_uploading = {}     # user_id -> временное хранилище загрузки

# === ЗАГРУЗКА / СОХРАНЕНИЕ ===
def load_json():
    global user_stats, user_meditations
    if os.path.exists(STATS_FILE):
        with open(STATS_FILE, "r") as f:
            user_stats = json.load(f)
    if os.path.exists(MEDITATIONS_FILE):
        with open(MEDITATIONS_FILE, "r") as f:
            user_meditations = json.load(f)

def save_json():
    with open(STATS_FILE, "w") as f:
        json.dump(user_stats, f)
    with open(MEDITATIONS_FILE, "w") as f:
        json.dump(user_meditations, f)

# === КЛАВИАТУРА ===
def main_keyboard():
    return ReplyKeyboardMarkup(resize_keyboard=True, keyboard=[
        [KeyboardButton(text="🧘 Начать медитацию")],
        [KeyboardButton(text="📥 Загрузить медитацию")],
        [KeyboardButton(text="📊 Статистика")],
    ])

# === СТАРТ ===
@dp.message(CommandStart())
async def start_handler(message: types.Message):
    await message.answer(
        "Привет! Я бот для медитаций 🧘‍♂️\n\n"
        "Ты можешь:\n"
        "— Загружать аудио и видео медитации\n"
        "— Выбирать категорию\n"
        "— Смотреть статистику по каждой медитации",
        reply_markup=main_keyboard()
    )

# === ЗАГРУЗКА МЕДИТАЦИИ ===
@dp.message(F.text == "📥 Загрузить медитацию")
async def start_upload(message: types.Message):
    user_id = str(message.from_user.id)
    user_uploading[user_id] = {"step": "wait_file"}
    await message.answer("Отправь мне медитацию (mp3/mp4 файл)")

@dp.message(F.text == "/cancel")
async def cancel_upload(message: types.Message):
    user_id = str(message.from_user.id)
    user_uploading.pop(user_id, None)
    await message.answer("❌ Загрузка отменена", reply_markup=main_keyboard())

@dp.message(F.audio | F.video | F.document)
async def handle_media(message: types.Message):
    user_id = str(message.from_user.id)
    if user_id not in user_uploading or user_uploading[user_id]["step"] != "wait_file":
        await message.answer("⛔ Нажми сначала 📥 'Загрузить медитацию'")
        return

    file = message.audio or message.video or message.document
    mime = file.mime_type or ""
    is_audio = "audio" in mime
    is_video = "video" in mime

    if not (is_audio or is_video):
        await message.answer("⛔ Только mp3/mp4")
        return

    # Сохраняем инфу
    user_uploading[user_id].update({
        "step": "wait_title",
        "file_id": file.file_id,
        "default_title": file.file_name or "Без названия",
        "duration": file.duration or 0,
        "type": "audio" if is_audio else "video"
    })

    await message.answer(
        f"📎 Файл получен. Название файла: <b>{file.file_name}</b>\n"
        "Напиши своё название или отправь 'Оставить', чтобы оставить как есть.")

@dp.message(F.text & (lambda msg: msg.from_user.id))
async def handle_title_or_category(message: types.Message):
    user_id = str(message.from_user.id)

    # Ввод названия
    if user_id in user_uploading and user_uploading[user_id]["step"] == "wait_title":
        title = message.text.strip()
        if title.lower() == "оставить":
            title = user_uploading[user_id]["default_title"]
        user_uploading[user_id]["title"] = title
        user_uploading[user_id]["step"] = "wait_category"
        await message.answer("🗂 В какую категорию добавить?\nВыбери: <b>Диспенза</b> или <b>Дыхательные</b>")
        return

    # Выбор категории
    if user_id in user_uploading and user_uploading[user_id]["step"] == "wait_category":
        category = message.text.strip().lower()
        if category not in ["диспенза", "дыхательные"]:
            await message.answer("⛔ Варианты: Диспенза или Дыхательные")
            return

        data = user_uploading[user_id]
        meditation = {
            "title": data["title"],
            "category": category.capitalize(),
            "file_id": data["file_id"],
            "duration": data["duration"],
            "type": data["type"]
        }

        # Сохраняем
        user_meditations.setdefault(user_id, []).append(meditation)
        user_uploading.pop(user_id)
        save_json()

        await message.answer(f"✅ Медитация <b>{meditation['title']}</b> добавлена в категорию {meditation['category']}", reply_markup=main_keyboard())
        return

# === ВЫБОР МЕДИТАЦИИ ===
@dp.message(F.text == "🧘 Начать медитацию")
async def choose_meditation(message: types.Message):
    user_id = str(message.from_user.id)
    meditations = user_meditations.get(user_id, [])

    if not meditations:
        await message.answer("Нет загруженных медитаций.")
        return

    await message.answer("🧘‍♀️ Устройся поудобнее. Когда будешь готов — выбери медитацию 🙏")

    buttons = [
        InlineKeyboardButton(text=f"{m['title']} [{m['category']}]", callback_data=f"start_{i}")
        for i, m in enumerate(meditations)
    ]

    keyboard = InlineKeyboardMarkup(inline_keyboard=[[btn] for btn in buttons])
    await message.answer("📄 Выбери медитацию:", reply_markup=keyboard)

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
        await callback.message.answer_audio(audio=meditation["file_id"], caption=f"▶️ <b>{meditation['title']}</b>")
    else:
        await callback.message.answer_video(video=meditation["file_id"], caption=f"▶️ <b>{meditation['title']}</b>")

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="✅ Завершить медитацию", callback_data="end_meditation")]]
    )
    await callback.message.answer("Нажми, когда завершишь медитацию 👇", reply_markup=keyboard)
    await callback.answer()

@dp.callback_query(F.data == "end_meditation")
async def end_meditation(callback: types.CallbackQuery):
    user_id = str(callback.from_user.id)
    session = user_active_sessions.pop(user_id, None)

    if not session:
        await callback.message.answer("⛔ Нет активной медитации.")
        return

    end = time.time()
    duration = int((end - session["start"]) / 60)
    duration = max(1, duration)

    user_stats.setdefault(user_id, {})
    user_stats[user_id]["Общее время"] = user_stats[user_id].get("Общее время", 0) + duration
    user_stats[user_id][session["title"]] = user_stats[user_id].get(session["title"], 0) + duration
    save_json()

    await callback.message.answer(f"✅ Медитация завершена. Засчитано: <b>{duration}</b> минут", reply_markup=main_keyboard())
    await callback.answer()

# === СТАТИСТИКА ===
@dp.message(F.text == "📊 Статистика")
async def show_stats(message: types.Message):
    user_id = str(message.from_user.id)
    stats = user_stats.get(user_id, {})
    if not stats:
        await message.answer("Пока нет статистики.")
        return

    text = "📊 <b>Твоя статистика:</b>\n"
    for key, value in stats.items():
        text += f"— {key}: {value} мин\n"

    await message.answer(text)

# === ЗАПУСК ===
async def main():
    load_json()
    print("✅ Бот запущен")
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())
