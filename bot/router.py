from datetime import datetime, timezone
from telegram import Update
from telegram.ext import ContextTypes
from config import TELEGRAM_CHAT_ID, RATE_LIMIT_SECONDS
from db.database import get_conn
from db.models import update_rate_limit, get_last_request_time
from bot.handlers.text import handle_text
from bot.handlers.voice import handle_voice, handle_reply_to_voice
from bot.handlers.location import handle_location


def _is_authorized(update: Update) -> bool:
    message = update.message or update.edited_message
    if not message:
        return False
    return message.chat_id == TELEGRAM_CHAT_ID


def _check_rate_limit(chat_id: int) -> float | None:
    """Returns seconds to wait, or None if OK to proceed."""
    conn = get_conn()
    last = get_last_request_time(conn, chat_id)
    if not last:
        return None
    elapsed = (datetime.now(timezone.utc) - last).total_seconds()
    if elapsed < RATE_LIMIT_SECONDS:
        return RATE_LIMIT_SECONDS - elapsed
    return None


async def route_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Main entry point for all incoming Telegram messages."""
    # Normalize edited_message → message
    if update.edited_message and not update.message:
        update._message = update.edited_message

    message = update.message
    if not message:
        return

    # Auth check
    if not _is_authorized(update):
        await message.reply_text("⛔ Access Denied")
        return

    chat_id = message.chat_id

    # Rate limit
    wait_secs = _check_rate_limit(chat_id)
    if wait_secs:
        await message.reply_text(f"⏳ Подожди {wait_secs:.0f} сек. перед следующим запросом.")
        return

    update_rate_limit(get_conn(), chat_id)

    # Classify — order matters, more specific first

    # [0] Reply to voice message
    if (
        message.reply_to_message
        and message.reply_to_message.voice
        and message.text
    ):
        await handle_reply_to_voice(update, context)
        return

    # [1] Text message
    if message.text:
        await handle_text(update, context)
        return

    # [2] Voice message
    if message.voice:
        await handle_voice(update, context)
        return

    # [3] Location pin
    if message.location:
        await handle_location(update, context)
        return

    # [4] Unsupported
    await message.reply_text(
        "Этот тип сообщения не поддерживается. "
        "Отправь текст, голосовое сообщение или геолокацию."
    )
