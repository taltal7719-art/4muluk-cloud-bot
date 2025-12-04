# -*- coding: utf-8 -*-
"""
Облачный Telegram-бот для Системы 4 Muluk.

Команды:
  /start          — приветствие и подсказка по командам
  /day            — отчёт на сегодня
  /day YYYY-MM-DD — отчёт на указанную дату
  /morning_test   — "утренний отчёт" прямо сейчас (как будет приходить утром)

Бот:
- сам считает энергетику дня через mayan_logic.py
- раз в сутки может слать утренний отчёт владельцу (OWNER_CHAT_ID)
- на Koyeb держит health-сервер на порту 8000 (для проверки живости)
"""

import os
import logging
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
)

from mayan_logic import (
    mayan_from_gregorian,
    get_moon_phase,
    classify_day,
    get_deep_profile,
    get_crowd_state,
    get_bot_mode,
    get_biorhythms,
    get_training_recommendation,
)

# --- НАСТРОЙКИ ПРОФИЛЯ 4 MULUK --- #

BIRTH_DATE = date(1972, 11, 10)
try:
    BISHKEK_TZ = ZoneInfo("Asia/Bishkek")
except Exception:
    # Запасной вариант, если вдруг нет таймзоны в образе
    from datetime import timedelta, timezone
    BISHKEK_TZ = timezone(timedelta(hours=6))

# Токен берём из переменных окружения (как мы и сделали на Koyeb)
BOT_TOKEN = (
    os.getenv("TELEGRAM_BOT_TOKEN")
    or os.getenv("BOT_TOKEN")
    or os.getenv("TOKEN")
)

# Чат, куда слать утренний отчёт (можно задать в Koyeb как OWNER_CHAT_ID="635079110")
OWNER_CHAT_ID = os.getenv("OWNER_CHAT_ID")


logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


# --- HEALTH-СЕРВЕР ДЛЯ KOYEB (порт 8000) --- #

def start_health_server():
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"OK")

        def log_message(self, format, *args):
            # Глушим стандартный треск HTTPServer в логах
            return

    server = HTTPServer(("0.0.0.0", 8000), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    logger.info("Health server запущен на порту 8000")


# --- ЛОГИКА ОТЧЁТА О ДНЕ --- #

def build_day_data(target_date: date) -> dict:
    info = mayan_from_gregorian(target_date)
    moon = get_moon_phase(target_date)
    cls = classify_day(info["tz_number"], info["tz_name"], moon["phase_code"])
    deep = get_deep_profile(info["tz_number"], info["tz_name"], moon["phase_code"])
    crowd = get_crowd_state(info["tz_number"], info["tz_name"], moon["phase_code"])
    bot_mode = get_bot_mode(cls["trading_signal_label"], crowd["code"])

    bior = get_biorhythms(BIRTH_DATE, target_date)
    training = get_training_recommendation(bior, cls, moon["phase_code"])

    return {
        "date": target_date,
        "info": info,
        "moon": moon,
        "cls": cls,
        "deep": deep,
        "crowd": crowd,
        "bot_mode": bot_mode,
        "bior": bior,
        "training": training,
    }


def format_day_report(day_data: dict, include_training: bool = True) -> str:
    d = day_data["date"]
    info = day_data["info"]
    moon = day_data["moon"]
    cls = day_data["cls"]
    crowd = day_data["crowd"]
    bot_mode = day_data["bot_mode"]
    bior = day_data["bior"]
    training = day_data["training"]

    lines: list[str] = []

    # Заголовок
    lines.append(f"📅 *День* {d.isoformat()}")
    lines.append(f"Майя: *{info['tz_number']} {info['tz_name']}*")
    lines.append(f"Луна: *{moon['phase_name']}*")
    lines.append("")

    # Класс дня и сигнал
    lines.append(f"Класс дня: *{cls['label']}*")
    lines.append(cls["description"])
    lines.append("")
    lines.append(f"Торговый сигнал: *{cls['trading_signal_label']}*")
    lines.append(cls["trading_signal_description"])
    lines.append("")

    # Толпа и режим бота
    lines.append(f"Толпа: *{crowd['state_label']}* ({crowd['code']})")
    lines.append(crowd["description"])
    lines.append("")
    lines.append(f"Режим бота: *{bot_mode['label']}* ({bot_mode['code']})")
    lines.append(bot_mode["description"])
    lines.append("")

    # Биоритмы
    lines.append("📊 *Биоритмы (в %):*")
    lines.append(
        f"Физический: {bior['physical']} | "
        f"Эмоциональный: {bior['emotional']} | "
        f"Интеллектуальный: {bior['intellectual']} | "
        f"Духовный: {bior['spiritual']}"
    )

    # Тренировка (по желанию)
    if include_training:
        lines.append("")
        lines.append("🏃 *Тренировка 4 Muluk на день:*")
        lines.append(f"Тип: *{training['type']}*")
        lines.append(training["text"])

    return "\n".join(lines)


# --- TELEGRAM-ХЕНДЛЕРЫ --- #

async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "Привет, Талгат! Я облачный бот Системы *4 Muluk* 🌊\n\n"
        "Доступные команды:\n"
        "/day — отчёт на сегодня\n"
        "/day YYYY-MM-DD — отчёт на конкретную дату\n"
        "/morning_test — показать, как будет выглядеть утренний отчёт\n\n"
        "Утренний автоотчёт раз в сутки:\n"
        "- время задаём в коде (сейчас 06:00 по Бишкеку)\n"
        "- чат для автоотчёта — через переменную окружения OWNER_CHAT_ID."
    )
    await update.message.reply_text(text, parse_mode="Markdown")


async def day_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if args:
        # пытаемся разобрать дату из аргумента
        try:
            d = datetime.strptime(args[0], "%Y-%m-%d").date()
        except ValueError:
            await update.message.reply_text(
                "Дата должна быть в формате YYYY-MM-DD, пример:\n"
                "`/day 2025-12-04`",
                parse_mode="Markdown",
            )
            return
    else:
        d = date.today()

    day_data = build_day_data(d)
    text = format_day_report(day_data, include_training=True)
    await update.message.reply_text(text, parse_mode="Markdown")


async def morning_test_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Ручной тест утреннего отчёта:
    - берём сегодняшнюю дату
    - считаем всё как для утра
    - шлём в этот же чат
    """
    d = date.today()
    day_data = build_day_data(d)
    text = "🌅 *Утренний отчёт 4 Muluk (тест)*\n\n" + format_day_report(
        day_data,
        include_training=True,
    )
    await update.message.reply_text(text, parse_mode="Markdown")


# --- УТРЕННЕЕ ЗАДАНИЕ ДЛЯ JOB QUEUE --- #

async def morning_job(context: ContextTypes.DEFAULT_TYPE):
    """
    Автоматический утренний отчёт (job_queue):
    - срабатывает по времени (06:00 Asia/Bishkek)
    - отправляет отчёт в OWNER_CHAT_ID (если задан)
    """
    if not OWNER_CHAT_ID:
        logger.info("OWNER_CHAT_ID не задан, утренний отчёт пропущен.")
        return

    try:
        chat_id = int(OWNER_CHAT_ID)
    except ValueError:
        logger.error("OWNER_CHAT_ID='%s' не удалось преобразовать в int", OWNER_CHAT_ID)
        return

    d = date.today()
    day_data = build_day_data(d)
    text = "🌅 *Утренний отчёт 4 Muluk*\n\n" + format_day_report(
        day_data,
        include_training=True,
    )

    logger.info("Отправляю утренний отчёт в чат %s", chat_id)
    await context.bot.send_message(chat_id=chat_id, text=text, parse_mode="Markdown")


# --- MAIN --- #

def main():
    if not BOT_TOKEN:
        print(
            "Не найден токен бота. Установи переменную окружения "
            "TELEGRAM_BOT_TOKEN или BOT_TOKEN или TOKEN."
        )
        return

    start_health_server()

    logger.info("Запускаю Telegram-бота 4 Muluk в облаке...")

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # Команды
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("day", day_cmd))
    app.add_handler(CommandHandler("morning_test", morning_test_cmd))

    # Утренняя задача (каждый день в 06:00 по Бишкеку)
    run_time = time(hour=6, minute=0, tzinfo=BISHKEK_TZ)
    app.job_queue.run_daily(
        morning_job,
        time=run_time,
        name="morning_report_4muluk",
    )

    # Запуск бота (polling)
    app.run_polling()


if __name__ == "__main__":
    main()
