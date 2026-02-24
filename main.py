import logging
import asyncio
from telegram import Update
from telegram.ext import Application, MessageHandler, filters
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from config import TELEGRAM_BOT_TOKEN
from bot.router import route_message
from schedulers.morning_summary import send_morning_summary
from schedulers.departure_check import check_departures

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)


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
        lambda: asyncio.create_task(send_morning_summary(app.bot)),
        'cron',
        hour=7,
        minute=0,
        id='morning_summary',
    )

    # Departure check: every 2 hours
    scheduler.add_job(
        lambda: asyncio.create_task(check_departures(app.bot)),
        'interval',
        hours=2,
        id='departure_check',
    )

    scheduler.start()
    logger.info("Scheduler started. Second Brain Bot running...")

    app.run_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True,
    )


if __name__ == "__main__":
    main()
