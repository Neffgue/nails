import os
import sqlite3
from datetime import datetime, timedelta
from dotenv import load_dotenv
from telegram import (
    Update, ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton,
)
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler,
    ConversationHandler, ContextTypes, filters
)
from logger import (
    init_activity_log, log_activity, get_today_stats, 
    send_daily_report, get_user_actions
)

load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")
ADDRESS_TEXT = "Дагестанская 10/1"
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
TZ_OFFSET_HOURS = 5
REMIND_1 = timedelta(hours=24)
REMIND_2 = timedelta(hours=2)

SERVICES = [
    ("Маникюр", 1000, 60),
    ("Маникюр с покрытием", 1600, 90),
    ("Наращивание ногтей", 2500, 180),
    ("Ремонт ногтя", "от 50", 15),
    ("Наращивание ногтя", "от 100", 20),
    ("Дизайн ногтя", "от 50", 20),
    ("Укрепление ногтей", 300, 30),
    ("Моделирование ногтей", 600, 60),
    ("Педикюр (пальчики)", 1000, 60),
    ("Педикюр (пальчики) с покрытием", 1700, 90),
    ("SMART педикюр", 1700, 100),
    ("SMART педикюр с покрытием", 2000, 120),
]

DB = "bookings.sqlite"
(SVC, DATE, TIME, PHONE, NAME, COMMENT, CONFIRM) = range(7)


def db_init():
    with sqlite3.connect(DB) as con:
        con.execute("""CREATE TABLE IF NOT EXISTS bookings(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            chat_id INTEGER,
            service TEXT,
            price TEXT,
            duration_min INTEGER,
            date_text TEXT,
            time_text TEXT,
            phone TEXT,
            name TEXT,
            comment TEXT,
            status TEXT,
            created_at TEXT
        )""")
        con.commit()
    init_activity_log()


def main_menu():
    return ReplyKeyboardMarkup(
        [["Записаться"], ["Прайс", "Адрес"], ["Вопрос администратору"], ["📊 Моя активность"]],
        resize_keyboard=True
    )


def parse_dt_local(date_text: str, time_text: str) -> datetime:
    dt = datetime.strptime(f"{date_text} {time_text}", "%d.%m.%Y %H:%M")
    return dt


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db_init()
    user = update.effective_user
    log_activity(user.id, user.username, "🚀 Запуск /start", f"Имя: {user.first_name}", update.message.chat_id)
    
    await update.message.reply_text(
        "Youses nails — запись через бота.\n"
        "Выберите действие кнопками ниже.",
        reply_markup=main_menu()
    )


async def myid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    log_activity(user.id, user.username, "🔍 Запрос chat_id", "", update.message.chat_id)
    await update.message.reply_text(f"Ваш chat_id: {update.effective_chat.id}")


async def setadmin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    admin_id = update.effective_chat.id
    user = update.effective_user
    log_activity(user.id, user.username, "⚙️ Установка администратора", "", update.message.chat_id)
    
    await update.message.reply_text(
        f"Ок, ADMIN_ID = {admin_id}.\n"
        f"Запиши это число в .env как ADMIN_ID и перезапусти бота."
    )


async def show_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    log_activity(user.id, user.username, "💰 Просмотр прайса", "", update.message.chat_id)
    
    lines = ["💅 <b>ПРАЙС:</b>\n"]
    for name, price, dur in SERVICES:
        lines.append(f"• {name} — <b>{price}</b> (~{dur} мин)")
    
    await update.message.reply_text("\n".join(lines), reply_markup=main_menu(), parse_mode="HTML")


async def show_address(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    log_activity(user.id, user.username, "📍 Просмотр адреса", "", update.message.chat_id)
    await update.message.reply_text(f"📍 <b>Адрес:</b> {ADDRESS_TEXT}", reply_markup=main_menu(), parse_mode="HTML")


async def show_activity(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    log_activity(user.id, user.username, "📊 Просмотр активности", "", update.message.chat_id)
    
    actions = get_user_actions(user.id, limit=5)
    
    if not actions:
        await update.message.reply_text(
            "У вас еще нет зафиксированных действий.",
            reply_markup=main_menu()
        )
        return
    
    text = "📊 <b>Ваша активность (последние 5):</b>\n\n"
    for action, details, timestamp in actions:
        time_obj = datetime.fromisoformat(timestamp)
        time_str = time_obj.strftime("%d.%m %H:%M")
        text += f"🔹 {action}\n"
        if details:
            text += f"   └─ {details}\n"
        text += f"   └─ {time_str}\n\n"
    
    await update.message.reply_text(text, reply_markup=main_menu(), parse_mode="HTML")


async def ask_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    log_activity(user.id, user.username, "❓ Начало диалога с админом", "", update.message.chat_id)
    
    await update.message.reply_text(
        "Напишите вопрос одним сообщением — он уйдёт администратору.",
        reply_markup=ReplyKeyboardMarkup([["Отмена"]], resize_keyboard=True)
    )
    return COMMENT


async def forward_question(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if ADMIN_ID == 0:
        await update.message.reply_text(
            "Админ ещё не настроен. Сначала узнайте свой chat_id командой /myid "
            "и пропишите его в .env как ADMIN_ID."
        )
        return ConversationHandler.END
    
    txt = update.message.text
    user = update.effective_user
    
    log_activity(user.id, user.username, "💬 Отправка вопроса администратору", txt[:50], update.message.chat_id)
    
    await context.bot.send_message(
        chat_id=ADMIN_ID,
        text=(
            "❓ <b>Вопрос от клиента:</b>\n"
            f"Имя: {user.full_name}\n"
            f"@{user.username}\n"
            f"user_id: {user.id}\n\n"
            f"{txt}"
        ),
        parse_mode="HTML"
    )
    await update.message.reply_text("✅ Отправлено администратору.", reply_markup=main_menu())
    return ConversationHandler.END


async def booking_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    log_activity(user.id, user.username, "📅 Начало бронирования", "", update.message.chat_id)
    
    buttons = [
        [InlineKeyboardButton(f"{n} — {p}", callback_data=f"svc::{i}")]
        for i, (n, p, _d) in enumerate(SERVICES)
    ]
    await update.message.reply_text(
        "Выберите услугу:",
        reply_markup=InlineKeyboardMarkup(buttons)
    )
    return SVC


async def pick_service(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    user = q.from_user
    idx = int(q.data.split("::")[1])
    name, price, dur = SERVICES[idx]
    context.user_data["service"] = name
    context.user_data["price"] = str(
