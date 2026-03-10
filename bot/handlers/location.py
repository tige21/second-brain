import json
from telegram import Update
from telegram.ext import ContextTypes
from services.yandex_geocoder import reverse_geocode
from db.database import get_conn
from db.models import set_setting
from agent.executor import run_agent
from bot.formatters import md_to_html, chunk_message


async def handle_location(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle GPS location pin — saves as pending location, asks agent to prompt for name."""
    message = update.message
    chat_id = message.chat_id
    loc = message.location
    lat, lon = loc.latitude, loc.longitude

    await context.bot.send_chat_action(chat_id=chat_id, action="typing")

    # Reverse geocode to get text address
    text_address = await reverse_geocode(lat, lon) or f"{lat:.4f}, {lon:.4f}"
    coords_str = f"{lat:.6f},{lon:.6f}"

    # Save as pending location (per-user)
    conn = get_conn()
    pending = json.dumps({"coords": coords_str, "address": text_address}, ensure_ascii=False)
    set_setting(conn, chat_id, 'pending_location', pending)

    # Ask agent to handle (agent will ask user for name)
    user_input = (
        f"Пользователь отправил геолокацию.\n"
        f"Адрес: {text_address}\n"
        f"Координаты: {coords_str}\n"
        f"Спроси как назвать этот адрес для сохранения в адресную книгу."
    )
    response = await run_agent(chat_id, user_input)
    html_response = md_to_html(response)
    for chunk in chunk_message(html_response):
        await message.reply_text(chunk, parse_mode="HTML")
