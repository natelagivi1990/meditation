import asyncio
import time
from aiogram import Bot, Dispatcher, F, types
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart
from aiogram.types import (
    ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton
)
from aiogram.client.default import DefaultBotProperties

API_TOKEN = '7787463545:AAH6M-_sYua5CsIgr3L1eq1hTuQfWGIynk4'

bot = Bot(token=API_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

# Хранилища
user_times = {}
user_meditations = {}
user_uploading = {}
user_active_sessions = {}

# Главное меню
def main_keyboard():
    return ReplyKeyboardMarkup(resize_keyboard=True, keyboard=[
        [KeyboardButton(text="🧘 Начать медитацию")],
        [KeyboardButton(text="📥 Загрузить медитацию")],
        [KeyboardButton(text="📊 Статистика")],
    ])

@dp.message(CommandStart())
async def start_handler(message: types.Message):
    await message.answer(
        "Привет! Я бот для медитаций 🧘‍♂️\n\n"
        "Ты можешь:\n"
        "— Загружать свои аудио и видео медитации\n"
        "— Слушать их и считать время\n"
        "— Смотреть свою статистику",
        reply_markup=main_keyboard()
    )

@dp.message(F.text == "🧘 Начать медитацию")
async def meditation_menu(message: types.Message):
    user_id = message.from_user.id
    meditations = user_meditations.get(user_id)

    if not meditations:
        await message.answer("У тебя пока нет загруженных медитаций. Отправь файл через 📥.")
        return

    await message.answer(
        "🧘‍♀️ Устройся поудобнее. Сделай пару глубоких вдохов.\n"
        "Когда будешь готов — выбери медитацию, и я начну отсчёт времени 🙏"
    )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=m["title"], callback_data=f"start_{i}")]
            for i, m in enumerate(meditations)
        ]
    )

    await message.answer("📄 Выбери медитацию:", reply_markup=keyboard)

@dp.callback_query(F.data.startswith("start_"))
async def start_meditation(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    index = int(callback.data.replace("start_", ""))
    meditation = user_meditations[user_id][index]

    user_active_sessions[user_id] = time.time()

    if meditation["type"] == "audio":
        await callback.message.answer_audio(
            audio=meditation["file_id"],
            caption=f"▶️ <b>{meditation['title']}</b>\n🕒 Таймер запущен..."
        )
    else:
        await callback.message.answer_video(
            video=meditation["file_id"],
            caption=f"▶️ <b>{meditation['title']}</b>\n🕒 Таймер запущен..."
        )

    end_keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Завершить медитацию", callback_data="end_meditation")]
        ]
    )
    await callback.message.answer("Когда завершишь — нажми кнопку ниже 👇", reply_markup=end_keyboard)
    await callback.answer()

@dp.callback_query(F.data == "end_meditation")
async def end_meditation(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    start_time = user_active_sessions.get(user_id)

    if not start_time:
        await callback.message.answer("⛔ Медитация не запущена.")
        await callback.answer()
        return

    end_time = time.time()
    elapsed_minutes = int((end_time - start_time) / 60)
    elapsed_minutes = max(1, elapsed_minutes)

    user_times[user_id] = user_times.get(user_id, 0) + elapsed_minutes
    user_active_sessions.pop(user_id)

    await callback.message.answer(
        f"✅ Медитация завершена!\n⏱ Засчитано в статистику: <b>{elapsed_minutes}</b> минут 🙏",
        reply_markup=main_keyboard()
    )
    await callback.answer()

@dp.message(F.text == "📥 Загрузить медитацию")
async def upload_instruction(message: types.Message):
    user_id = message.from_user.id
    user_uploading[user_id] = True
    await message.answer("Отправь аудиофайл (.mp3) или видео (.mp4, .mov) — я сохраню его.\n\nОтправь /cancel чтобы выйти из режима загрузки.")

@dp.message(F.text == "/cancel")
async def cancel_upload(message: types.Message):
    user_id = message.from_user.id
    user_uploading[user_id] = False
    await message.answer("❌ Загрузка отменена.", reply_markup=main_keyboard())

@dp.message(F.audio | F.video | F.document)
async def handle_media_upload(message: types.Message):
    user_id = message.from_user.id

    if not user_uploading.get(user_id):
        await message.reply("⛔ Сначала нажми 📥 'Загрузить медитацию'")
        return

    file = message.audio or message.video or message.document
    mime_type = file.mime_type or ""
    is_audio = "audio" in mime_type
    is_video = "video" in mime_type

    if not (is_audio or is_video):
        await message.reply("⛔ Только аудио (.mp3) и видео (.mp4, .mov) поддерживаются.")
        return

    meditation = {
        "title": file.file_name or "Без названия",
        "file_id": file.file_id,
        "duration": file.duration or 0,
        "type": "audio" if is_audio else "video"
    }

    if user_id not in user_meditations:
        user_meditations[user_id] = []

    user_meditations[user_id].append(meditation)
    user_uploading[user_id] = False

    await message.reply(
        f"✅ Медитация <b>{meditation['title']}</b> загружена!\n"
        f"⏱ Длительность файла: {meditation['duration'] // 60} мин {meditation['duration'] % 60} сек",
        reply_markup=main_keyboard()
    )

@dp.message(F.text == "📊 Статистика")
async def stats_handler(message: types.Message):
    user_id = message.from_user.id
    total = user_times.get(user_id, 0)
    await message.answer(f"📊 Ты всего медитировал: <b>{total}</b> минут")

async def main():
    print("✅ Бот запущен")
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())
