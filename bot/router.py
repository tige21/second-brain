from datetime import datetime, timezone
from telegram import Update
from telegram.ext import ContextTypes
from config import TELEGRAM_CHAT_ID, RATE_LIMIT_SECONDS
from db.database import get_conn
from db.models import (
    update_rate_limit, get_last_request_time,
    get_or_create_user, approve_user, is_user_approved, get_user_token,
)
from bot.handlers.text import handle_text
from bot.handlers.voice import handle_voice, handle_reply_to_voice, handle_audio
from bot.handlers.location import handle_location


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

    chat_id = message.chat_id
    username = message.from_user.username if message.from_user else None
    conn = get_conn()

    # Register user and auto-approve owner
    user, is_new = get_or_create_user(conn, chat_id, username)
    if chat_id == TELEGRAM_CHAT_ID and not user['approved']:
        approve_user(conn, chat_id)
        user['approved'] = 1

    # If not approved, inform user and notify admin (only on first contact)
    if not user['approved']:
        if is_new:
            await message.reply_text(
                f"⏳ Запрос доступа отправлен администратору.\n"
                f"Твой Chat ID: <code>{chat_id}</code>",
                parse_mode="HTML"
            )
            try:
                uname = f"@{username}" if username else "без username"
                await context.bot.send_message(
                    chat_id=TELEGRAM_CHAT_ID,
                    text=(
                        f"👤 Новый пользователь запрашивает доступ:\n"
                        f"Chat ID: <code>{chat_id}</code>\n"
                        f"Username: {uname}\n\n"
                        f"Одобри командой: /approve {chat_id}"
                    ),
                    parse_mode="HTML"
                )
            except Exception:
                pass
        else:
            await message.reply_text("⏳ Ожидай одобрения администратора.")
        return

    # Allow certain actions before Google is connected
    text = message.text or ""
    pre_auth_commands = ('/connect', '/approve', '/start', '/help')
    if any(text.startswith(cmd) for cmd in pre_auth_commands):
        await handle_text(update, context)
        return

    # Also allow OAuth code paste (starts with "4/", no spaces, >20 chars)
    stripped = text.strip()
    if stripped.startswith('4/') and len(stripped) > 20 and ' ' not in stripped:
        await handle_text(update, context)
        return

    # Require Google Calendar to be connected for all other actions
    if not get_user_token(conn, chat_id):
        await message.reply_text(
            "⚠️ Google Calendar не подключён.\n"
            "Используй /connect для подключения."
        )
        return

    # Rate limit
    wait_secs = _check_rate_limit(chat_id)
    if wait_secs:
        await message.reply_text(f"⏳ Подожди {wait_secs:.0f} сек. перед следующим запросом.")
        return

    update_rate_limit(conn, chat_id)

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

    # [3] Audio file (from iOS Shortcuts)
    if message.audio or (message.document and message.document.mime_type and 'audio' in message.document.mime_type):
        await handle_audio(update, context)
        return

    # [4] Location pin
    if message.location:
        await handle_location(update, context)
        return

    # [5] Unsupported
    await message.reply_text(
        "Этот тип сообщения не поддерживается. "
        "Отправь текст, голосовое сообщение или геолокацию."
    )
