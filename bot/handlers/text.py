from telegram import Update
from telegram.ext import ContextTypes
from config import TELEGRAM_CHAT_ID
from agent.executor import run_agent
from db.database import get_conn
from db.models import clear_memory
from bot.formatters import md_to_html, chunk_message


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle plain text messages and bot commands."""
    message = update.message or update.edited_message
    chat_id = message.chat_id
    text = message.text or ""

    # Commands
    if text.startswith('/start') or text.startswith('/help'):
        help_text = (
            "🤖 <b>Second Brain Bot</b>\n\n"
            "Я управляю твоим Google Calendar и Google Tasks.\n\n"
            "<b>Что я умею:</b>\n"
            "• 📅 Создавать, изменять, удалять события\n"
            "• ✅ Управлять задачами\n"
            "• 🎙️ Распознавать голосовые сообщения\n"
            "• 📍 Сохранять адреса и рассчитывать маршруты\n"
            "• 🌅 Утренняя сводка в 10:00 MSK\n"
            "• 🚀 Напоминание о выезде\n\n"
            "<b>Команды:</b>\n"
            "/start, /help — эта справка\n"
            "/reset — сбросить историю диалога"
        )
        await message.reply_text(help_text, parse_mode="HTML")
        return

    if text.startswith('/reset'):
        conn = get_conn()
        clear_memory(conn, chat_id)
        await message.reply_text("✅ История диалога сброшена.")
        return

    # Forwarded messages (PTB 21.x uses forward_origin instead of forward_date)
    user_input = text
    if message.forward_origin:
        user_input = f'📨 Пересланное сообщение: "{text}"\nИзвлеки задачу или событие.'

    # Reply to another message
    elif message.reply_to_message and message.reply_to_message.text:
        original = message.reply_to_message.text
        user_input = f'📨 Сообщение: "{original}"\n💬 Комментарий: {text}'

    await context.bot.send_chat_action(chat_id=chat_id, action="typing")
    response = await run_agent(chat_id, user_input)
    html_response = md_to_html(response)

    for chunk in chunk_message(html_response):
        await message.reply_text(chunk, parse_mode="HTML")
