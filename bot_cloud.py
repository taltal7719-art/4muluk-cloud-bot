# -*- coding: utf-8 -*-
"""
Облачный Telegram-бот 4 Muluk для Koyeb.

Особенности:
- Берёт BOT_TOKEN из переменной окружения.
- Считает энергетику дня напрямую через mayan_logic (без локального API).
- Поднимает простой HTTP-сервер на порту $PORT для health-check Koyeb.
"""

import logging
import os
import threading
import http.server
import socketserver
from datetime import datetime, date

from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
)

from mayan_logic import (
    mayan_from_gregorian,
    classify_day,
    get_deep_profile,
    get_moon_phase,
    get_crowd_state,
    get_bot_mode,
    get_biorhythms,
    get_training_recommendation,
    get_daily_schedule,
    get_nutrition_profile,
    get_sumerian_profile,
    get_eastern_profile,
)

# === НАСТРОЙКИ ===

# дата рождения 4 Muluk
BIRTH_DATE = date(1972, 11, 10)

BOT_TOKEN = os.getenv("BOT_TOKEN")

if not BOT_TOKEN:
    raise SystemExit("Переменная окружения BOT_TOKEN не задана. Задай её в настройках Koyeb.")


# === ЛОГИРОВАНИЕ ===

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


# === HEALTH-CHECK HTTP-СЕРВЕР ДЛЯ KOYEB ===

def run_health_server():
    """
    Простейший HTTP-сервер, который отвечает 200 OK на любой запрос.
    Нужен только для health-check Koyeb (порт 8000 или $PORT).
    """
    port = int(os.getenv("PORT", "8000"))

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"OK")

        def log_message(self, format, *args):
            # глушим болтливый лог http-сервера
            return

    with socketserver.TCPServer(("", port), Handler) as httpd:
        logger.info("Health server запущен на порту %s", port)
        httpd.serve_forever()


# === ВСПОМОГАТЕЛЬНАЯ ЛОГИКА ===

def compute_day_payload(d: date) -> dict:
    """
    Собираем полный профиль дня (примерно как /api/day в локальной версии).
    """
    info = mayan_from_gregorian(d)
    moon = get_moon_phase(d)
    cls = classify_day(info["tz_number"], info["tz_name"], moon["phase_code"])
    deep = get_deep_profile(info["tz_number"], info["tz_name"], moon["phase_code"])
    crowd_state = get_crowd_state(info["tz_number"], info["tz_name"], moon["phase_code"])
    bot_mode = get_bot_mode(cls["trading_signal_label"], crowd_state["code"])

    bior = get_biorhythms(BIRTH_DATE, d)
    training = get_training_recommendation(bior, cls, moon["phase_code"])
    schedule = get_daily_schedule(BIRTH_DATE, d, cls, moon["phase_code"], bior)
    nutrition = get_nutrition_profile(bior, cls, moon["phase_code"])
    sumer = get_sumerian_profile(d)
    east = get_eastern_profile(d)

    return {
        "date": d.isoformat(),
        "tzolkin": {
            "number": info["tz_number"],
            "name": info["tz_name"],
        },
        "haab": {
            "day": info["haab_day"],
            "month": info["haab_month_name"],
        },
        "moon": {
            "phase_code": moon["phase_code"],
            "phase_name": moon["phase_name"],
            "age": moon["age"],
            "illum": moon["illum"],
        },
        "class": {
            "level": cls["level"],
            "label": cls["label"],
            "description": cls["description"],
            "trading_signal_label": cls["trading_signal_label"],
            "trading_signal_description": cls["trading_signal_description"],
        },
        "crowd": {
            "scenario": deep["crowd_scenario"],
            "state": crowd_state["code"],
            "state_label": crowd_state["label"],
            "state_description": crowd_state["description"],
        },
        "bot_mode": {
            "code": bot_mode["code"],
            "label": bot_mode["label"],
            "description": bot_mode["description"],
        },
        "biorhythms": bior,
        "training": training,
        "schedule": schedule,
        "nutrition": nutrition,
        "sumerian": sumer,
        "eastern": east,
    }


def format_day_message(payload: dict) -> str:
    """
    Формируем красивый текст для Telegram из payload.
    """
    d = payload["date"]
    tz = payload["tzolkin"]
    moon = payload["moon"]
    cls = payload["class"]
    crowd = payload["crowd"]
    bot_mode = payload["bot_mode"]
    bior = payload["biorhythms"]

    lines: list[str] = []

    lines.append(f"📅 *День* {d}")
    lines.append(f"Майя: *{tz['number']} {tz['name']}*")
    lines.append(f"Луна: {moon['phase_name']}")
    lines.append("")
    lines.append(f"Класс дня: *{cls['label']}*")
    lines.append(cls["description"])
    lines.append("")
    lines.append(f"Торговый сигнал: *{cls['trading_signal_label']}*")
    lines.append(cls["trading_signal_description"])
    lines.append("")
    lines.append(f"Толпа: *{crowd['state_label']}* ({crowd['state']})")
    lines.append(crowd["state_description"])
    lines.append("")
    lines.append(f"Режим бота: *{bot_mode['label']}* ({bot_mode['code']})")
    lines.append(bot_mode["description"])
    lines.append("")
    lines.append("📊 *Биоритмы* (в %):")
    lines.append(
        f"Физический: {bior['physical']} | Эмоциональный: {bior['emotional']} | "
        f"Интеллектуальный: {bior['intellectual']} | Духовный: {bior['spiritual']}"
    )

    return "\n".join(lines)


# === ОБРАБОТЧИКИ КОМАНД ===

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "Привет! Я облачный бот *Системы 4 Muluk*.\n\n"
        "Команды:\n"
        "/day — энергетический отчёт на сегодня\n"
        "/day YYYY-MM-DD — отчёт на конкретную дату\n\n"
        "Бот работает в облаке 24/7, даже если твой компьютер выключен."
    )
    await update.message.reply_text(text, parse_mode="Markdown")


async def day_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    date_str = None
    d: date

    if args:
        try:
            d = datetime.strptime(args[0], "%Y-%m-%d").date()
            date_str = args[0]
        except ValueError:
            await update.message.reply_text(
                "Дата должна быть в формате YYYY-MM-DD, пример:\n"
                "/day 2025-11-30"
            )
            return
    else:
        d = date.today()
        date_str = d.isoformat()

    try:
        payload = compute_day_payload(d)
    except Exception as e:
        logger.exception("Ошибка при расчёте дня %s: %s", date_str, e)
        await update.message.reply_text("Не удалось посчитать энергетику дня. Попробуй позже.")
        return

    text = format_day_message(payload)
    await update.message.reply_text(text, parse_mode="Markdown")


# === MAIN ===

async def run_bot():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("day", day_cmd))

    logger.info("Запускаю Telegram-бота 4 Muluk в облаке...")
    await app.run_polling(close_loop=False)


def main():
    # health-server запускаем в отдельном потоке
    threading.Thread(target=run_health_server, daemon=True).start()

    # Telegram-бот — в основном потоке (asyncio)
    import asyncio
    asyncio.run(run_bot())


if __name__ == "__main__":
    main()
