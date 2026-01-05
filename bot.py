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
    ConversationHandler, ContextTypes, filters,
)

# ---------- ENV / CONFIG ----------
load_dotenv()  # подтягиваем переменные из .env

TOKEN = os.getenv("BOT_TOKEN")            # из .env
ADDRESS_TEXT = "Дагестанская 10/1"        # можно вынести в .env, если нужно
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))  # chat_id админа из .env

TZ_OFFSET_HOURS = 5  # Уфа (+05), пока не используем явно

REMIND_1 = timedelta(hours=24)
REMIND_2 = timedelta(hours=2)

# название, цена, длительность (мин)
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
# ---------------------------

DB = "bookings.sqlite"

(
    SVC, DATE, TIME, PHONE, NAME, COMMENT, CONFIRM
) = range(7)


def db_init():
    with sqlite3.connect(DB) as con:
        con.execute(
            """CREATE TABLE IF NOT EXISTS bookings(
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
            )"""
        )
        con.commit()


def main_menu():
    return ReplyKeyboardMarkup(
        [["Записаться"], ["Прайс", "Адрес"], ["Вопрос администратору"]],
        resize_keyboard=True
    )


def parse_dt_local(date_text: str, time_text: str) -> datetime:
    # Формат: ДД.ММ.ГГГГ и ЧЧ:ММ
    dt = datetime.strptime(f"{date_text} {time_text}", "%d.%m.%Y %H:%M")
    return dt


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db_init()
    await update.message.reply_text(
        "Youses nails — запись через бота.\n"
        "Выберите действие кнопками ниже.",
        reply_markup=main_menu()
    )


async def myid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"Ваш chat_id: {update.effective_chat.id}")


async def setadmin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Для теста: кто вызвал — тот админ (в проде лучше убрать).
    admin_id = update.effective_chat.id
    await update.message.reply_text(
        f"Ок, ADMIN_ID = {admin_id}.\n"
        f"Запиши это число в .env как ADMIN_ID и перезапусти бота."
    )


async def show_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lines = ["Прайс:"]
    for name, price, _dur in SERVICES:
        lines.append(f"• {name} — {price}")
    await update.message.reply_text("\n".join(lines), reply_markup=main_menu())


async def show_address(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"Адрес: {ADDRESS_TEXT}", reply_markup=main_menu())


async def ask_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
    await context.bot.send_message(
        chat_id=ADMIN_ID,
        text=(
            "Вопрос от клиента:\n"
            f"Имя: {user.full_name}\n"
            f"@{user.username}\n"
            f"user_id: {user.id}\n\n"
            f"{txt}"
        )
    )
    await update.message.reply_text("Отправлено администратору.", reply_markup=main_menu())
    return ConversationHandler.END


async def booking_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # выбор услуги инлайн-кнопками
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
    idx = int(q.data.split("::")[1])
    name, price, dur = SERVICES[idx]
    context.user_data["service"] = name
    context.user_data["price"] = str(price)
    context.user_data["duration"] = dur
    await q.edit_message_text(
        f"Услуга: {name} ({price}), ~{dur} мин.\n\n"
        "Введите дату в формате ДД.ММ.ГГГГ (например 05.01.2026):"
    )
    return DATE


async def get_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["date_text"] = update.message.text.strip()
    await update.message.reply_text("Введите время в формате ЧЧ:ММ (например 16:00):")
    return TIME


async def get_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["time_text"] = update.message.text.strip()
    contact_btn = KeyboardButton("Поделиться контактом", request_contact=True)
    kb = ReplyKeyboardMarkup(
        [[contact_btn], ["Отмена"]],
        resize_keyboard=True,
        one_time_keyboard=True
    )
    await update.message.reply_text(
        "Нажмите кнопку, чтобы отправить номер телефона:",
        reply_markup=kb
    )
    return PHONE


async def get_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.contact:
        await update.message.reply_text(
            "Пожалуйста, отправьте номер через кнопку «Поделиться контактом»."
        )
        return PHONE
    context.user_data["phone"] = update.message.contact.phone_number
    await update.message.reply_text("Как вас записать? (имя)")
    return NAME


async def get_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["name"] = update.message.text.strip()
    await update.message.reply_text(
        "Комментарий (необязательно). Если нет — напишите «-»."
    )
    return COMMENT


async def get_comment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["comment"] = update.message.text.strip()
    s = context.user_data["service"]
    p = context.user_data["price"]
    d = context.user_data["duration"]
    dt = context.user_data["date_text"]
    tm = context.user_data["time_text"]
    phone = context.user_data["phone"]
    name = context.user_data["name"]
    cmt = context.user_data["comment"]

    text = (
        "Проверьте заявку:\n"
        f"Услуга: {s} — {p}\n"
        f"Дата/время: {dt} {tm}\n"
        f"Имя: {name}\n"
        f"Телефон: {phone}\n"
        f"Комментарий: {cmt}\n\n"
        "Отправить администратору?"
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("Отправить", callback_data="send::yes")],
        [InlineKeyboardButton("Отмена", callback_data="send::no")],
    ])
    await update.message.reply_text(text, reply_markup=kb)
    return CONFIRM


async def send_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    if q.data.endswith("no"):
        await q.edit_message_text("Ок, отменено.")
        return ConversationHandler.END

    if ADMIN_ID == 0:
        await q.edit_message_text(
            "Админ ещё не настроен (ADMIN_ID=0). Пропишите ADMIN_ID в .env."
        )
        return ConversationHandler.END

    user = q.from_user
    payload = dict(context.user_data)

    # save to db
    with sqlite3.connect(DB) as con:
        cur = con.execute(
            """INSERT INTO bookings(user_id, chat_id, service, price, duration_min,
                                    date_text, time_text, phone, name, comment,
                                    status, created_at)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                user.id, q.message.chat_id,
                payload["service"], payload["price"], int(payload["duration"]),
                payload["date_text"], payload["time_text"],
                payload["phone"], payload["name"], payload["comment"],
                "pending",
                datetime.utcnow().isoformat(),
            )
        )
        booking_id = cur.lastrowid
        con.commit()

    admin_text = (
        f"Новая заявка #{booking_id}\n"
        f"Услуга: {payload['service']} — {payload['price']} (~{payload['duration']} мин)\n"
        f"Дата/время: {payload['date_text']} {payload['time_text']}\n"
        f"Клиент: {payload['name']} (@{user.username})\n"
        f"Телефон: {payload['phone']}\n"
        f"Комментарий: {payload['comment']}\n"
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("Подтвердить", callback_data=f"adm::{booking_id}::ok")],
        [InlineKeyboardButton("Отменить", callback_data=f"adm::{booking_id}::cancel")],
    ])
    await context.bot.send_message(chat_id=ADMIN_ID, text=admin_text, reply_markup=kb)

    await q.edit_message_text("Заявка отправлена администратору. Ожидайте подтверждения.")
    return ConversationHandler.END


async def admin_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    if q.message.chat_id != ADMIN_ID:
        await q.edit_message_text("Недостаточно прав.")
        return

    _, bid, act = q.data.split("::")
    bid = int(bid)

    with sqlite3.connect(DB) as con:
        row = con.execute(
            "SELECT chat_id, date_text, time_text, service FROM bookings WHERE id=?",
            (bid,)
        ).fetchone()
        if not row:
            await q.edit_message_text("Заявка не найдена.")
            return
        client_chat_id, date_text, time_text, service = row

        status = "confirmed" if act == "ok" else "cancelled"
        con.execute("UPDATE bookings SET status=? WHERE id=?", (status, bid))
        con.commit()

    if act == "ok":
        await context.bot.send_message(
            chat_id=client_chat_id,
            text=f"Запись подтверждена: {service}, {date_text} {time_text}.\nАдрес: {ADDRESS_TEXT}"
        )

        dt = parse_dt_local(date_text, time_text)

        # напоминания (через JobQueue) [web:60]
        context.job_queue.run_once(
            remind_cb,
            when=dt - REMIND_1,
            data={
                "chat_id": client_chat_id,
                "text": f"Напоминание: завтра запись {service} в {time_text}. Адрес: {ADDRESS_TEXT}.",
            },
        )
        context.job_queue.run_once(
            remind_cb,
            when=dt - REMIND_2,
            data={
                "chat_id": client_chat_id,
                "text": f"Напоминание: через 2 часа запись {service} в {time_text}. Адрес: {ADDRESS_TEXT}.",
            },
        )

        await q.edit_message_text(f"Подтверждено #{bid}. Напоминания поставлены.")
    else:
        await context.bot.send_message(
            chat_id=client_chat_id,
            text="Запись отменена администратором. Если нужно — создайте новую заявку."
        )
        await q.edit_message_text(f"Отменено #{bid}.")


async def remind_cb(context: ContextTypes.DEFAULT_TYPE):
    data = context.job.data
    await context.bot.send_message(chat_id=data["chat_id"], text=data["text"])


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Отменено.", reply_markup=main_menu())
    return ConversationHandler.END


def build_app():
    if not TOKEN:
        raise RuntimeError("BOT_TOKEN не задан (проверь .env).")

    app = ApplicationBuilder().token(TOKEN).build()

    # commands
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("myid", myid))
    app.add_handler(CommandHandler("setadmin", setadmin))

    # static buttons
    app.add_handler(MessageHandler(filters.Regex("^Прайс$"), show_price))
    app.add_handler(MessageHandler(filters.Regex("^Адрес$"), show_address))

    # booking conversation
    booking_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^Записаться$"), booking_entry)],
        states={
            SVC: [CallbackQueryHandler(pick_service, pattern=r"^svc::")],
            DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_date)],
            TIME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_time)],
            PHONE: [
                MessageHandler(filters.CONTACT, get_phone),
                MessageHandler(filters.TEXT & ~filters.COMMAND, get_phone),
            ],
            NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_name)],
            COMMENT: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_comment)],
            CONFIRM: [CallbackQueryHandler(send_request, pattern=r"^send::")],
        },
        fallbacks=[
            MessageHandler(filters.Regex("^Отмена$"), cancel),
            CommandHandler("cancel", cancel),
        ],
        allow_reentry=True,
    )
    app.add_handler(booking_conv)

    # question flow
    ask_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^Вопрос администратору$"), ask_admin)],
        states={COMMENT: [MessageHandler(filters.TEXT & ~filters.COMMAND, forward_question)]},
        fallbacks=[
            MessageHandler(filters.Regex("^Отмена$"), cancel),
            CommandHandler("cancel", cancel),
        ],
    )
    app.add_handler(ask_conv)

    # admin callbacks
    app.add_handler(CallbackQueryHandler(admin_action, pattern=r"^adm::"))

    return app


if __name__ == "__main__":
    db_init()
    app = build_app()
    app.run_polling(allowed_updates=Update.ALL_TYPES)
