# -*- coding: utf-8 -*-
"""
Облачный Telegram-бот Системы 4 Muluk.

Особенности:
- Бот сам считает энергетику дня/недели через mayan_logic.py
- Никакой локальный app.py ему не нужен
- Готов к запуску как 24/7 worker на Render / Railway и т.п.

Команды:
  /start                  — приветствие и помощь
  /day                    — краткий отчёт на сегодня
  /day YYYY-MM-DD         — отчёт на указанную дату
  /week                   — обзор на 7 дней вперёд (сегодня + 6)
  /week YYYY-MM-DD        — неделя, начиная с указанной даты
  /menu                   — интерактивное меню с кнопками
"""

import os
import logging
from datetime import datetime, date, timedelta

from telegram import (
    Update,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    CallbackQueryHandler,
)

# === ЛОГИКА 4 MULUK ===
from mayan_logic import (
    mayan_from_gregorian,
    get_moon_phase,
    classify_day,
    get_deep_profile,
    get_crowd_state,
    get_bot_mode,
    get_biorhythms,
    get_training_recommendation,
    get_daily_schedule,
    get_nutrition_profile,
    get_sumerian_profile,
    # get_eastern_profile,  # если есть — можно подключить
)

# === НАСТРОЙКИ ===

# токен читаем из переменной окружения
BOT_TOKEN = os.getenv("BOT_TOKEN", "")

# твоя дата рождения под 4 Muluk
BIRTH_DATE = date(1972, 11, 10)

# при желании можно использовать CHAT_ID для рассылок
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


# === ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ===

def parse_date_arg(args: list[str]) -> date | None:
    """Парсинг даты из аргументов команды (формат YYYY-MM-DD)."""
    if not args:
        return None
    try:
        d = datetime.strptime(args[0], "%Y-%m-%d").date()
        return d
    except ValueError:
        return None


def calc_day(d: date) -> dict:
    """
    Считаем полный профиль дня через mayan_logic.
    Возвращаем структуру, похожую на /api/day локальной версии.
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
    # east = get_eastern_profile(d)  # если реализовано

    return {
        "date": d,
        "tzolkin": {
            "number": info["tz_number"],
            "name": info["tz_name"],
        },
        "haab": {
            "day": info["haab_day"],
            "month": info["haab_month_name"],
        },
        "moon": moon,
        "class": cls,
        "deep": deep,
        "crowd": crowd_state,
        "bot_mode": bot_mode,
        "bior": bior,
        "training": training,
        "schedule": schedule,
        "nutrition": nutrition,
        "sumerian": sumer,
        # "eastern": east,
    }


def format_day_text(day_data: dict) -> str:
    """Формирует текст отчёта по одному дню."""
    d = day_data["date"]
    tz = day_data["tzolkin"]
    moon = day_data["moon"]
    cls = day_data["class"]
    crowd = day_data["crowd"]
    bot_mode = day_data["bot_mode"]
    bior = day_data["bior"]

    lines: list[str] = []

    lines.append(f"📅 *День* {d.strftime('%d.%m.%Y')}")
    lines.append(f"Майя: *{tz['number']} {tz['name']}*")
    lines.append(f"Луна: {moon['phase_name']} ({moon['phase_emoji']})")
    lines.append("")
    lines.append(f"Класс дня: *{cls['label']}*")
    lines.append(cls["description"])
    lines.append("")
    lines.append(f"Сигнал трейдинга: *{cls['trading_signal_label']}*")
    lines.append(cls["trading_signal_description"])
    lines.append("")
    lines.append(f"Толпа: *{crowd['label']}* (`{crowd['code']}`)")
    lines.append(crowd["description"])
    lines.append("")
    lines.append(f"Режим бота: *{bot_mode['label']}* (`{bot_mode['code']}`)")
    lines.append("")
    lines.append("Биоритмы:")
    lines.append(f"• Физический: {bior['physical']}%")
    lines.append(f"• Эмоциональный: {bior['emotional']}%")
    lines.append(f"• Интеллектуальный: {bior['intellectual']}%")
    lines.append(f"• Духовный: {bior['spiritual']}%")

    return "\n".join(lines)


def format_week_text(days: list[dict]) -> str:
    """Текстовый обзор недели (без кнопок)."""
    lines: list[str] = []
    lines.append("📈 *Неделя 4 Muluk*")
    if not days:
        return "\n".join(lines)

    start = days[0]["date"]
    end = days[-1]["date"]
    lines.append(f"c {start.strftime('%d.%m.%Y')} по {end.strftime('%d.%m.%Y')}")
    lines.append("")

    for d in days:
        bior = d["bior"]
        lines.append(
            f"*{d['date'].strftime('%d.%m')}* — {d['tzolkin']['number']} {d['tzolkin']['name']}, "
            f"{d['class']['label']}, бот: `{d['bot_mode']['code']}`"
        )
        lines.append(
            f"  Физ: {bior['physical']}%, Эмоц: {bior['emotional']}%"
        )
        lines.append("")

    return "\n".join(lines)


def build_day_keyboard(d: date) -> InlineKeyboardMarkup:
    """Инлайн-клавиатура под отчётом дня."""
    iso = d.isoformat()
    keyboard = [
        [
            InlineKeyboardButton("Показать толпу", callback_data=f"crowd:{iso}"),
            InlineKeyboardButton("Режим бота", callback_data=f"mode:{iso}"),
        ],
        [
            InlineKeyboardButton("Неделя от этого дня", callback_data=f"week:{iso}"),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)


# === ОБРАБОТЧИКИ КОМАНД ===

async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "Привет, Талгат! Я *облачный бот* Системы 4 Muluk.\n\n"
        "Доступные команды:\n"
        "/day — отчёт на сегодня\n"
        "/day YYYY-MM-DD — отчёт на дату\n"
        "/week — обзор на 7 дней вперёд\n"
        "/week YYYY-MM-DD — неделя, начиная с даты\n"
        "/menu — показать меню с кнопками\n\n"
        "Я использую те же расчёты Майя/Луна/биоритмы, что и твой локальный календарь, "
        "но работаю 24/7 в облаке ✨"
    )
    if update.message:
        await update.message.reply_text(text, parse_mode="Markdown")


async def day_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    d = parse_date_arg(args) or date.today()

    day_data = calc_day(d)
    text = format_day_text(day_data)
    kb = build_day_keyboard(d)

    if update.message:
        await update.message.reply_text(text, parse_mode="Markdown", reply_markup=kb)


async def week_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    start_date = parse_date_arg(args) or date.today()

    days: list[dict] = []
    for i in range(7):
        d = start_date + timedelta(days=i)
        days.append(calc_day(d))

    text = format_week_text(days)

    if update.message:
        await update.message.reply_text(text, parse_mode="Markdown")


async def menu_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Простое меню с основными кнопками."""
    keyboard = [
        [
            InlineKeyboardButton("День (сегодня)", callback_data=f"day:{date.today().isoformat()}"),
            InlineKeyboardButton("Неделя", callback_data=f"week:{date.today().isoformat()}"),
        ],
    ]
    kb = InlineKeyboardMarkup(keyboard)
    if update.message:
        await update.message.reply_text("Выбери действие:", reply_markup=kb)


# === CALLBACK-КНОПКИ ===

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query:
        return

    await query.answer()

    data = query.data or ""
    try:
        action, payload = data.split(":", 1)
    except ValueError:
        return

    if action == "day":
        try:
            d = datetime.strptime(payload, "%Y-%m-%d").date()
        except ValueError:
            d = date.today()
        day_data = calc_day(d)
        text = format_day_text(day_data)
        kb = build_day_keyboard(d)
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=kb)

    elif action == "week":
        try:
            start_date = datetime.strptime(payload, "%Y-%m-%d").date()
        except ValueError:
            start_date = date.today()
        days: list[dict] = []
        for i in range(7):
            d = start_date + timedelta(days=i)
            days.append(calc_day(d))
        text = format_week_text(days)
        await query.edit_message_text(text, parse_mode="Markdown")

    elif action == "crowd":
        try:
            d = datetime.strptime(payload, "%Y-%m-%d").date()
        except ValueError:
            d = date.today()
        info = mayan_from_gregorian(d)
        moon = get_moon_phase(d)
        crowd = get_crowd_state(info["tz_number"], info["tz_name"], moon["phase_code"])
        text = (
            f"🧠 *Толпа {d.strftime('%d.%m.%Y')}*\n\n"
            f"Состояние: *{crowd['label']}* (`{crowd['code']}`)\n"
            f"{crowd['description']}"
        )
        await query.edit_message_text(text, parse_mode="Markdown")

    elif action == "mode":
        try:
            d = datetime.strptime(payload, "%Y-%m-%d").date()
        except ValueError:
            d = date.today()
        info = mayan_from_gregorian(d)
        moon = get_moon_phase(d)
        cls = classify_day(info["tz_number"], info["tz_name"], moon["phase_code"])
        crowd = get_crowd_state(info["tz_number"], info["tz_name"], moon["phase_code"])
        bot_mode = get_bot_mode(cls["trading_signal_label"], crowd["code"])
        text = (
            f"🎛 *Режим бота {d.strftime('%d.%m.%Y')}*\n\n"
            f"Сигнал: *{cls['trading_signal_label']}*\n"
            f"{cls['trading_signal_description']}\n\n"
            f"Толпа: *{crowd['label']}* (`{crowd['code']}`)\n\n"
            f"Режим бота: *{bot_mode['label']}* (`{bot_mode['code']}`)\n"
            f"{bot_mode['description']}"
        )
        await query.edit_message_text(text, parse_mode="Markdown")


# === MAIN ===

def main():
    if not BOT_TOKEN or BOT_TOKEN.strip() == "":
        print("❌ Не задан BOT_TOKEN. Укажи токен бота в переменной окружения BOT_TOKEN.")
        return

    app = ApplicationBuilder().token(BOT_TOKEN.strip()).build()

    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("day", day_cmd))
    app.add_handler(CommandHandler("week", week_cmd))
    app.add_handler(CommandHandler("menu", menu_cmd))

    app.add_handler(CallbackQueryHandler(callback_handler))

    print("✅ Облачный бот 4 Muluk запущен. (локально: Ctrl+C для остановки)")
    app.run_polling()


if __name__ == "__main__":
    main()
