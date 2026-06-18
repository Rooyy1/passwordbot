import asyncio
import asyncpg
import os
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD")
ADMIN_ID = int(os.getenv("ADMIN_ID"))
DATABASE_URL = os.getenv("DATABASE_URL")

bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)
db_pool = None

admin_sessions = set()


class MailingStates(StatesGroup):
    waiting_for_target = State()
    waiting_for_content = State()
    waiting_for_button_text = State()
    waiting_for_button_url = State()
    waiting_for_usernames = State()
    waiting_for_confirm = State()


class SurveyStates(StatesGroup):
    waiting_for_application = State()


class AdminAuthStates(StatesGroup):
    waiting_for_password = State()


def is_admin(user_id: int) -> bool:
    return user_id in admin_sessions


async def init_db():
    global db_pool
    db_pool = await asyncpg.create_pool(DATABASE_URL, statement_cache_size=0)
    async with db_pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id BIGINT PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS config (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)
        await conn.execute("""
            INSERT INTO config (key, value)
            SELECT 'password', 'DROP77'
            WHERE NOT EXISTS (SELECT 1 FROM config WHERE key = 'password')
        """)
    print("✅ Supabase подключена")


async def get_password():
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow("SELECT value FROM config WHERE key = 'password'")
        return row[0] if row else "DROP77"


async def set_password(new_pass: str):
    async with db_pool.acquire() as conn:
        await conn.execute("UPDATE config SET value = $1 WHERE key = 'password'", new_pass)


async def save_user(user_id, username, first_name):
    async with db_pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO users (user_id, username, first_name)
            VALUES ($1, $2, $3)
            ON CONFLICT (user_id) DO NOTHING
        """, user_id, username, first_name)


async def get_all_users():
    async with db_pool.acquire() as conn:
        rows = await conn.fetch("SELECT user_id, username, first_name FROM users")
        return rows


async def get_user_id_by_username(username):
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow("SELECT user_id FROM users WHERE username = $1", username)
        return row[0] if row else None


def get_target_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📢 Всем пользователям", callback_data="target_all")],
        [InlineKeyboardButton(text="🎯 Выборочно (по username)", callback_data="target_select")]
    ])


def get_confirm_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Да, отправить", callback_data="confirm_yes")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="confirm_no")]
    ])


def get_button_choice_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Добавить кнопку", callback_data="add_button")],
        [InlineKeyboardButton(text="⏭️ Пропустить", callback_data="skip_button")]
    ])


# --- /admin ---
@dp.message(Command("admin"))
async def cmd_admin(message: types.Message, state: FSMContext):
    await state.set_state(AdminAuthStates.waiting_for_password)
    await message.answer("🔐 *Введите пароль администратора*", parse_mode="Markdown")


@dp.message(AdminAuthStates.waiting_for_password)
async def check_admin_password(message: types.Message, state: FSMContext):
    if message.text == ADMIN_PASSWORD:
        admin_sessions.add(message.from_user.id)
        await state.clear()
        await show_admin_panel(message)
    else:
        await message.answer("❌ *Неверный пароль*", parse_mode="Markdown")
        await state.clear()


async def show_admin_panel(message: types.Message):
    users = await get_all_users()
    total_users = len(users)
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Статистика", callback_data="admin_stats")],
        [InlineKeyboardButton(text="👥 Список пользователей", callback_data="admin_users")],
        [InlineKeyboardButton(text="📋 Форматирование", callback_data="admin_html_help")],
        [InlineKeyboardButton(text="🚪 Выйти", callback_data="admin_logout")]
    ])
    
    await message.answer(
        f"<b>👨‍💻 АДМИН-ПАНЕЛЬ</b>\n\n"
        f"👥 <b>Всего пользователей:</b> {total_users}\n\n"
        f"<i>Выбери действие:</i>",
        parse_mode="HTML",
        reply_markup=keyboard
    )


# --- Форматирование (HTML-справка) ---
@dp.callback_query(F.data == "admin_html_help")
async def admin_html_help(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return
    
    await callback.answer()
    
    help_text = """
📚 <b>Форматирование текста для рассылки</b>

<b>Жирный текст</b>
<code>&lt;b&gt;текст&lt;/b&gt;</code>

<i>Курсив</i>
<code>&lt;i&gt;текст&lt;/i&gt;</code>

<a href="https://site.com">Ссылка</a>
<code>&lt;a href="URL"&gt;текст&lt;/a&gt;</code>

<tg-spoiler>Спойлер</tg-spoiler>
<code>&lt;tg-spoiler&gt;текст&lt;/tg-spoiler&gt;</code>

<blockquote>Цитата</blockquote>
<code>&lt;blockquote&gt;текст&lt;/blockquote&gt;</code>

<u>Подчёркнутый</u>
<code>&lt;u&gt;текст&lt;/u&gt;</code>

<s>Зачёркнутый</s>
<code>&lt;s&gt;текст&lt;/s&gt;</code>

<pre>Пример для пароля:
&lt;b&gt;Пароль для входа на сайт: 77090&lt;/b&gt;

&lt;a href="https://ceoment.ru/"&gt;Купить - https://ceoment.ru/&lt;/a&gt;
(количество ограничено)</pre>

<i>Теги можно комбинировать.</i>
"""
    
    await callback.message.answer(help_text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Назад в админку", callback_data="admin_back")]
    ]))


# --- /start (новая логика с заявкой) ---
@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    await save_user(message.from_user.id, message.from_user.username, message.from_user.first_name)
    
    await message.answer(
        "<b>Приветствую! Чтобы получить пароль для покупки, распиши почему именно ты должен получить его</b>",
        parse_mode="HTML"
    )
    await state.set_state(SurveyStates.waiting_for_application)


# --- Обработка заявки ---
@dp.message(SurveyStates.waiting_for_application)
async def process_application(message: types.Message, state: FSMContext):
    user = message.from_user
    username = f"@{user.username}" if user.username else f"ID: {user.id}"
    
    # Отправляем админу
    await bot.send_message(
        ADMIN_ID,
        f"📩 <b>НОВАЯ ЗАЯВКА</b>\n\n"
        f"👤 {username}\n\n"
        f"📝 {message.text}",
        parse_mode="HTML"
    )
    
    # Отправляем пользователю
    await message.answer(
        "<b>Спасибо! Ваша заявка отправлена на обработку, в случае если нам понравится ваша заявка, мы вам отправим пароль за день до дропа</b>",
        parse_mode="HTML"
    )
    
    await state.clear()


# --- Остальные админ-команды ---
@dp.callback_query(F.data == "admin_logout")
async def admin_logout(callback: types.CallbackQuery):
    if callback.from_user.id in admin_sessions:
        admin_sessions.remove(callback.from_user.id)
    await callback.answer("🚪 Вы вышли из админ-панели", show_alert=True)
    await callback.message.delete()


@dp.callback_query(F.data == "admin_back")
async def admin_back(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return
    await callback.answer()
    await show_admin_panel(callback.message)


@dp.callback_query(F.data == "admin_stats")
async def admin_stats(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return
    users = await get_all_users()
    total = len(users)
    await callback.answer()
    await callback.message.answer(
        f"<b>📊 СТАТИСТИКА</b>\n\n👥 <b>Всего пользователей:</b> {total}",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_back")]
        ])
    )


@dp.callback_query(F.data == "admin_users")
async def admin_users(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return
    users = await get_all_users()
    if not users:
        await callback.answer("📭 Нет пользователей")
        return
    text = "<b>👥 СПИСОК ПОЛЬЗОВАТЕЛЕЙ:</b>\n\n"
    for uid, username, first_name in users[:30]:
        uname = f"@{username}" if username else "нет username"
        name = first_name or "без имени"
        text += f"👤 {name} ({uname}) — <code>{uid}</code>\n"
    if len(users) > 30:
        text += f"\n<i>... и еще {len(users) - 30} пользователей</i>"
    await callback.answer()
    await callback.message.answer(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_back")]
    ]))


@dp.message(Command("изменитьпароль"))
async def cmd_change_password(message: types.Message):
    if not is_admin(message.from_user.id):
        await message.answer("⛔ Нет прав. Авторизуйтесь через /admin")
        return
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("❌ Формат: /изменитьпароль НОВЫЙ_ПАРОЛЬ")
        return
    new_pass = parts[1].strip()
    await set_password(new_pass)
    await message.answer(f"✅ Пароль изменён на: `{new_pass}`", parse_mode="Markdown")


@dp.message(Command("база"))
async def cmd_get_users(message: types.Message):
    if not is_admin(message.from_user.id):
        await message.answer("⛔ Нет прав. Авторизуйтесь через /admin")
        return
    users = await get_all_users()
    if not users:
        await message.answer("📭 Нет пользователей")
        return
    batch = []
    for uid, username, first_name in users:
        uname = f"@{username}" if username else "нет username"
        name = first_name or "без имени"
        batch.append(f"👤 {name} ({uname}) — `{uid}`")
        if len(batch) >= 30:
            await message.answer("\n".join(batch), parse_mode="Markdown")
            batch = []
            await asyncio.sleep(0.3)
    if batch:
        await message.answer("\n".join(batch), parse_mode="Markdown")


@dp.message(Command("рассылка"))
async def cmd_mailing(message: types.Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        await message.answer("⛔ Нет прав. Авторизуйтесь через /admin")
        return
    await state.set_state(MailingStates.waiting_for_target)
    await message.answer("📨 *Кому отправляем рассылку?*", parse_mode="Markdown", reply_markup=get_target_keyboard())


@dp.callback_query(F.data == "target_all", MailingStates.waiting_for_target)
async def process_target_all(callback: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return
    await callback.answer()
    await state.update_data(target="all")
    await state.set_state(MailingStates.waiting_for_content)
    await callback.message.edit_text(
        "📝 *Отправь сообщение для рассылки*\n\nМожно: текст, фото, видео, кружок, документ.\nВ тексте можно использовать <b>HTML</b> теги.\n\nПросто отправь сообщение.",
        parse_mode="Markdown"
    )


@dp.callback_query(F.data == "target_select", MailingStates.waiting_for_target)
async def process_target_select(callback: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return
    await callback.answer()
    await state.update_data(target="select")
    await state.set_state(MailingStates.waiting_for_usernames)
    await callback.message.edit_text(
        "📝 *Отправь список username через запятую*\n\nПример: `@john,@jane,@alex`",
        parse_mode="Markdown"
    )


@dp.message(MailingStates.waiting_for_usernames)
async def process_usernames(message: types.Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        await message.answer("⛔ Нет прав")
        await state.clear()
        return
    usernames_str = message.text.strip()
    usernames = [u.strip().lstrip('@') for u in usernames_str.split(',')]
    users_to_send = []
    not_found = []
    for username in usernames:
        uid = await get_user_id_by_username(username)
        if uid:
            users_to_send.append(uid)
        else:
            not_found.append(f"@{username}")
    if not users_to_send:
        await message.answer(f"❌ Не найдено ни одного пользователя: {', '.join(not_found)}\n\nНачни заново с /рассылка")
        await state.clear()
        return
    await state.update_data(users_to_send=users_to_send, not_found=not_found)
    await state.set_state(MailingStates.waiting_for_content)
    await message.answer(
        f"✅ Найдено {len(users_to_send)} пользователей.\n❌ Не найдены: {', '.join(not_found) if not_found else 'нет'}\n\n📝 *Отправь сообщение для рассылки*",
        parse_mode="Markdown"
    )


@dp.message(MailingStates.waiting_for_content)
async def process_mailing_content(message: types.Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        await message.answer("⛔ Нет прав")
        await state.clear()
        return
    await state.update_data(content=message)
    await state.set_state(MailingStates.waiting_for_button_text)
    await message.answer("➕ *Добавить кнопку-ссылку?*", parse_mode="Markdown", reply_markup=get_button_choice_keyboard())


@dp.callback_query(F.data == "skip_button", MailingStates.waiting_for_button_text)
async def skip_button(callback: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return
    await callback.answer()
    await state.update_data(has_button=False)
    await state.set_state(MailingStates.waiting_for_confirm)
    await show_preview(callback.message, state)


@dp.callback_query(F.data == "add_button", MailingStates.waiting_for_button_text)
async def add_button(callback: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return
    await callback.answer()
    await state.set_state(MailingStates.waiting_for_button_text)
    await callback.message.edit_text("🔗 *Введи ТЕКСТ кнопки*\n\nПример: `Перейти на сайт`", parse_mode="Markdown")


@dp.message(MailingStates.waiting_for_button_text)
async def get_button_text(message: types.Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        await message.answer("⛔ Нет прав")
        await state.clear()
        return
    button_text = message.text.strip()
    await state.update_data(button_text=button_text)
    await state.set_state(MailingStates.waiting_for_button_url)
    await message.answer("🌐 *Введи ССЫЛКУ для кнопки*\n\nПример: `https://example.com`", parse_mode="Markdown")


@dp.message(MailingStates.waiting_for_button_url)
async def save_button_url(message: types.Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        await message.answer("⛔ Нет прав")
        await state.clear()
        return
    button_url = message.text.strip()
    if not button_url.startswith(('http://', 'https://')):
        button_url = 'https://' + button_url
    await state.update_data(button_url=button_url, has_button=True)
    await state.set_state(MailingStates.waiting_for_confirm)
    await show_preview(message, state)


async def show_preview(msg: types.Message, state: FSMContext):
    data = await state.get_data()
    target = data.get('target')
    content = data.get('content')
    has_button = data.get('has_button', False)
    button_text = data.get('button_text')
    button_url = data.get('button_url')
    users_to_send = data.get('users_to_send', [])
    not_found = data.get('not_found', [])

    reply_markup = None
    if has_button and button_text and button_url:
        reply_markup = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=button_text, url=button_url)]
        ])

    if target == "all":
        users = await get_all_users()
        info = f"📊 *Предпросмотр рассылки*\n\n👥 Получателей: **{len(users)}** (все)\n\n"
    else:
        info = f"📊 *Предпросмотр рассылки*\n\n👥 Получателей: **{len(users_to_send)}**\n"
        if not_found:
            info += f"❌ Не найдены: {', '.join(not_found)}\n\n"

    if has_button:
        info += f"🔘 Кнопка: `{button_text}` → {button_url}\n"

    info += "\n⬇️ *Само сообщение:*\n"
    await msg.answer(info, parse_mode="Markdown")
    await forward_message_to_chat(content, msg.chat.id, reply_markup)
    await msg.answer("✅ *Отправить рассылку?*", parse_mode="Markdown", reply_markup=get_confirm_keyboard())


@dp.callback_query(F.data == "confirm_yes", MailingStates.waiting_for_confirm)
async def confirm_mailing_yes(callback: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return
    await callback.answer()
    data = await state.get_data()
    target = data.get('target')
    content = data.get('content')
    has_button = data.get('has_button', False)
    button_text = data.get('button_text')
    button_url = data.get('button_url')
    users_to_send = data.get('users_to_send', [])

    reply_markup = None
    if has_button and button_text and button_url:
        reply_markup = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=button_text, url=button_url)]
        ])

    if target == "all":
        recipients = await get_all_users()
        recipient_ids = [row[0] for row in recipients]
    else:
        recipient_ids = users_to_send

    if not recipient_ids:
        await callback.message.edit_text("❌ Нет получателей для рассылки")
        await state.clear()
        return

    await callback.message.edit_text(f"📨 Начинаю рассылку для {len(recipient_ids)} пользователей...")
    success = 0
    for uid in recipient_ids:
        try:
            await forward_message_to_user(content, uid, reply_markup)
            success += 1
            await asyncio.sleep(0.05)
        except:
            pass
    await callback.message.answer(f"✅ Рассылка завершена. Отправлено {success} из {len(recipient_ids)}.")
    await state.clear()


@dp.callback_query(F.data == "confirm_no", MailingStates.waiting_for_confirm)
async def confirm_mailing_no(callback: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return
    await callback.answer()
    await callback.message.edit_text("❌ Рассылка отменена")
    await state.clear()


async def forward_message_to_user(msg: types.Message, target_user_id: int, reply_markup=None):
    if msg.text:
        await bot.send_message(target_user_id, msg.text, parse_mode="HTML", reply_markup=reply_markup)
    elif msg.photo:
        await bot.send_photo(target_user_id, msg.photo[-1].file_id, caption=msg.caption, parse_mode="HTML" if msg.caption else None, reply_markup=reply_markup)
    elif msg.video:
        await bot.send_video(target_user_id, msg.video.file_id, caption=msg.caption, parse_mode="HTML" if msg.caption else None, reply_markup=reply_markup)
    elif msg.video_note:
        await bot.send_video_note(target_user_id, msg.video_note.file_id)
    elif msg.document:
        await bot.send_document(target_user_id, msg.document.file_id, caption=msg.caption, parse_mode="HTML" if msg.caption else None, reply_markup=reply_markup)
    elif msg.audio:
        await bot.send_audio(target_user_id, msg.audio.file_id, caption=msg.caption, parse_mode="HTML" if msg.caption else None, reply_markup=reply_markup)
    elif msg.voice:
        await bot.send_voice(target_user_id, msg.voice.file_id, caption=msg.caption, parse_mode="HTML" if msg.caption else None, reply_markup=reply_markup)
    elif msg.sticker:
        await bot.send_sticker(target_user_id, msg.sticker.file_id)
    elif msg.animation:
        await bot.send_animation(target_user_id, msg.animation.file_id, caption=msg.caption, parse_mode="HTML" if msg.caption else None, reply_markup=reply_markup)
    else:
        await bot.send_message(target_user_id, "⚠️ Тип не поддерживается")


async def forward_message_to_chat(msg: types.Message, target_chat_id: int, reply_markup=None):
    if msg.text:
        await bot.send_message(target_chat_id, msg.text, parse_mode="HTML", reply_markup=reply_markup)
    elif msg.photo:
        await bot.send_photo(target_chat_id, msg.photo[-1].file_id, caption=msg.caption, parse_mode="HTML" if msg.caption else None, reply_markup=reply_markup)
    elif msg.video:
        await bot.send_video(target_chat_id, msg.video.file_id, caption=msg.caption, parse_mode="HTML" if msg.caption else None, reply_markup=reply_markup)
    elif msg.video_note:
        await bot.send_video_note(target_chat_id, msg.video_note.file_id)
    elif msg.document:
        await bot.send_document(target_chat_id, msg.document.file_id, caption=msg.caption, parse_mode="HTML" if msg.caption else None, reply_markup=reply_markup)
    elif msg.audio:
        await bot.send_audio(target_chat_id, msg.audio.file_id, caption=msg.caption, parse_mode="HTML" if msg.caption else None, reply_markup=reply_markup)
    elif msg.voice:
        await bot.send_voice(target_chat_id, msg.voice.file_id, caption=msg.caption, parse_mode="HTML" if msg.caption else None, reply_markup=reply_markup)
    elif msg.sticker:
        await bot.send_sticker(target_chat_id, msg.sticker.file_id)
    elif msg.animation:
        await bot.send_animation(target_chat_id, msg.animation.file_id, caption=msg.caption, parse_mode="HTML" if msg.caption else None, reply_markup=reply_markup)
    else:
        await bot.send_message(target_chat_id, "⚠️ Тип не поддерживается")


@dp.message()
async def remember_user(message: types.Message):
    await save_user(message.from_user.id, message.from_user.username, message.from_user.first_name)


async def main():
    await init_db()
    print("🚀 Бот запущен")
    print("🔐 Пароль админа:", ADMIN_PASSWORD)
    
    # Повторные попытки подключения к Telegram
    for attempt in range(5):
        try:
            await dp.start_polling(bot)
            break
        except Exception as e:
            print(f"❌ Ошибка подключения (попытка {attempt+1}/5): {e}")
            await asyncio.sleep(5)
    else:
        print("❌ Не удалось подключиться после 5 попыток")


if __name__ == "__main__":
    asyncio.run(main())