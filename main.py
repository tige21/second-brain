import logging
import asyncio
from telegram import Update, BotCommand
from telegram.ext import Application, MessageHandler, filters
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from config import TELEGRAM_BOT_TOKEN
from bot.router import route_message
from upload_server import start_upload_server
from schedulers.morning_summary import send_morning_summary
from schedulers.evening_summary import send_evening_summary
from schedulers.departure_check import check_departures
from schedulers.reminder_check import check_reminders
from schedulers.token_check import check_google_tokens
from schedulers.event_task_notifier import check_event_task_reminders

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Generate UPLOAD_TOKEN if not set
import secrets as _secrets
import os as _os
if not _os.environ.get("UPLOAD_TOKEN"):
    _os.environ["UPLOAD_TOKEN"] = _secrets.token_urlsafe(24)


async def error_handler(update: object, context) -> None:
    logger.error("Exception while handling update:", exc_info=context.error)
    if isinstance(update, Update) and update.effective_message:
        try:
            await update.effective_message.reply_text(
                f"⚠️ Попробовал ещё раз, но не получилось:\n{str(context.error)[:500]}"
            )
        except Exception:
            pass


def main() -> None:
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # All message types → router
    app.add_handler(MessageHandler(filters.ALL, route_message))
    app.add_error_handler(error_handler)

    # Scheduler
    scheduler = AsyncIOScheduler()

    # Morning summary: 07:00 UTC daily (10:00 MSK)
    scheduler.add_job(
        send_morning_summary,
        'cron',
        hour=7,
        minute=0,
        id='morning_summary',
        args=[app.bot],
    )

    # Evening summary: 18:00 UTC daily (21:00 MSK)
    scheduler.add_job(
        send_evening_summary,
        'cron',
        hour=18,
        minute=0,
        id='evening_summary',
        args=[app.bot],
    )

    # Reminder check: every minute
    scheduler.add_job(
        check_reminders,
        'interval',
        minutes=1,
        id='reminder_check',
        args=[app.bot],
    )

    # Departure check: every 15 minutes
    scheduler.add_job(
        check_departures,
        'interval',
        minutes=15,
        id='departure_check',
        args=[app.bot],
    )

    # Event-task reminders: every 15 minutes
    scheduler.add_job(
        check_event_task_reminders,
        'interval',
        minutes=15,
        id='event_task_reminders',
        args=[app.bot],
    )

    # Google token check: daily at 09:00 UTC (12:00 MSK)
    scheduler.add_job(
        check_google_tokens,
        'cron',
        hour=9,
        minute=0,
        id='token_check',
        args=[app.bot],
    )

    scheduler.start()

    # Register bot commands (shown in Telegram "/" menu)
    async def _register_commands(_app):
        await _app.bot.set_my_commands([
            BotCommand("connect",  "🔗 Подключить Google Calendar"),
            BotCommand("week",     "📅 События на 7 дней"),
            BotCommand("tomorrow", "🌅 События завтра"),
            BotCommand("tasks",    "✅ Все активные задачи"),
            BotCommand("go",       "🚀 Когда выходить на ближайшее событие"),
            BotCommand("undo",     "↩️ Отменить последнее действие"),
            BotCommand("tz",       "🕐 Установить часовой пояс (/tz +3)"),
            BotCommand("reset",    "🗑 Сбросить историю диалога"),
            BotCommand("approve",  "👥 Управление пользователями"),
            BotCommand("help",     "❓ Справка по боту"),
        ])
        logger.info("Bot commands registered.")

    async def on_startup(_app):
        await _register_commands(_app)
        await start_upload_server(_app.bot)
        upload_token = _os.environ.get("UPLOAD_TOKEN", "")
        logger.info(f"Upload server ready. Token: {upload_token}")

    app.post_init = on_startup
    logger.info("Scheduler started. Second Brain Bot running...")

    app.run_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True,
    )


if __name__ == "__main__":
    main()
