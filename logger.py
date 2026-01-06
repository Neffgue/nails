import os
import sqlite3
import requests
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv

load_dotenv()

NOTIFICATION_BOT_TOKEN = os.getenv("NOTIFICATION_BOT_TOKEN", "")
MONITORING_CHAT_ID = os.getenv("MONITORING_CHAT_ID", "")
DB = "bookings.sqlite"
TZ = timezone(timedelta(hours=5))


def init_activity_log():
    """Инициализирует таблицу логирования активности"""
    with sqlite3.connect(DB) as con:
        con.execute("""
            CREATE TABLE IF NOT EXISTS activity_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                username TEXT,
                action TEXT,
                details TEXT,
                timestamp TEXT,
                chat_id INTEGER
            )
        """)
        con.commit()


def log_activity(user_id, username, action, details="", chat_id=None):
    """Логирует действие пользователя в БД и отправляет в notification-бот"""
    timestamp = datetime.now(TZ).isoformat()
    
    with sqlite3.connect(DB) as con:
        con.execute("""
            INSERT INTO activity_log(user_id, username, action, details, timestamp, chat_id)
            VALUES(?, ?, ?, ?, ?, ?)
        """, (user_id, username, action, details, timestamp, chat_id))
        con.commit()
    
    if NOTIFICATION_BOT_TOKEN and MONITORING_CHAT_ID:
        send_notification(user_id, username, action, details, timestamp)


def send_notification(user_id, username, action, details="", timestamp=""):
    """Отправляет уведомление в notification-бот"""
    try:
        time_obj = datetime.fromisoformat(timestamp)
        time_str = time_obj.strftime("%H:%M:%S")
        
        message = (
            f"📊 <b>Активность пользователя</b>\n"
            f"👤 User: @{username or f'ID{user_id}'}\n"
            f"🎯 Действие: <b>{action}</b>\n"
            f"📝 Детали: {details or 'нет'}\n"
            f"🕐 Время: {time_str}"
        )
        
        url = f"https://api.telegram.org/bot{NOTIFICATION_BOT_TOKEN}/sendMessage"
        requests.post(url, json={
            "chat_id": MONITORING_CHAT_ID,
            "text": message,
            "parse_mode": "HTML"
        }, timeout=5)
    except Exception as e:
        print(f"⚠️ Ошибка отправки уведомления: {e}")


def get_today_stats():
    """Возвращает статистику за текущий день"""
    today = datetime.now(TZ).strftime('%Y-%m-%d')
    
    with sqlite3.connect(DB) as con:
        stats = con.execute("""
            SELECT 
                COUNT(DISTINCT user_id) as unique_users,
                COUNT(*) as total_actions
            FROM activity_log
            WHERE date(timestamp) = ?
        """, (today,)).fetchone()
    
    return stats if stats else (0, 0)


def get_user_actions(user_id, limit=10):
    """Возвращает последние действия пользователя"""
    with sqlite3.connect(DB) as con:
        actions = con.execute("""
            SELECT action, details, timestamp
            FROM activity_log
            WHERE user_id = ?
            ORDER BY timestamp DESC
            LIMIT ?
        """, (user_id, limit)).fetchall()
    
    return actions


def send_daily_report():
    """Отправляет ежедневный отчет в notification-бот"""
    if not NOTIFICATION_BOT_TOKEN or not MONITORING_CHAT_ID:
        return
    
    unique_users, total_actions = get_today_stats()
    today = datetime.now(TZ).strftime('%Y-%m-%d')
    
    with sqlite3.connect(DB) as con:
        top_actions = con.execute("""
            SELECT action, COUNT(*) as count
            FROM activity_log
            WHERE date(timestamp) = ?
            GROUP BY action
            ORDER BY count DESC
            LIMIT 5
        """, (today,)).fetchall()
    
    message = (
        f"📈 <b>Дневной отчет активности</b>\n"
        f"📅 Дата: {today}\n"
        f"👥 Уникальных пользователей: <b>{unique_users}</b>\n"
        f"🔄 Всего действий: <b>{total_actions}</b>\n\n"
    )
    
    if top_actions:
        message += "<b>Топ действий:</b>\n"
        for action, count in top_actions:
            message += f"• {action}: {count}\n"
    
    try:
        url = f"https://api.telegram.org/bot{NOTIFICATION_BOT_TOKEN}/sendMessage"
        requests.post(url, json={
            "chat_id": MONITORING_CHAT_ID,
            "text": message,
            "parse_mode": "HTML"
        }, timeout=5)
    except Exception as e:
        print(f"⚠️ Ошибка отправки отчета: {e}")
