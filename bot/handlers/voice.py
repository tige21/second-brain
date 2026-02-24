import io
from telegram import Update
from telegram.ext import ContextTypes
from services.openai_stt import transcribe_audio, format_duration
from agent.executor import run_agent
from bot.formatters import md_to_html, chunk_message
from config import VOICE_LONG_THRESHOLD_SECONDS


async def _download_voice_bytes(bot, file_id: str) -> bytes:
    """Download voice file, returns raw bytes."""
    voice_file = await bot.get_file(file_id)
    bio = io.BytesIO()
    await voice_file.download_to_memory(bio)
    bio.seek(0)
    return bio.read()


async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle voice messages."""
    message = update.message
    chat_id = message.chat_id
    voice = message.voice

    await context.bot.send_chat_action(chat_id=chat_id, action="typing")

    audio_bytes = await _download_voice_bytes(context.bot, voice.file_id)
    duration_secs = voice.duration or 0

    try:
        transcription = await transcribe_audio(audio_bytes, "voice.ogg")
    except Exception as e:
        await message.reply_text(f"⚠️ Не удалось распознать голос: {e}")
        return

    if duration_secs > VOICE_LONG_THRESHOLD_SECONDS:
        duration_str = format_duration(duration_secs)
        user_input = f"🎙️ [Запись {duration_str}]\n{transcription}"
    else:
        user_input = transcription

    response = await run_agent(chat_id, user_input)
    html_response = md_to_html(response)
    for chunk in chunk_message(html_response):
        await message.reply_text(chunk, parse_mode="HTML")


async def handle_reply_to_voice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle text reply to a voice message — transcribes the original voice."""
    message = update.message
    chat_id = message.chat_id
    reply_voice = message.reply_to_message.voice
    user_comment = (message.text or "").strip()

    await context.bot.send_chat_action(chat_id=chat_id, action="typing")

    audio_bytes = await _download_voice_bytes(context.bot, reply_voice.file_id)
    try:
        transcription = await transcribe_audio(audio_bytes, "voice.ogg")
    except Exception as e:
        await message.reply_text(f"⚠️ Не удалось распознать голос: {e}")
        return

    # "." reply → just return transcription
    if user_comment in (".", ""):
        await message.reply_text(f"📝 <code>{transcription}</code>", parse_mode="HTML")
        return

    # Text comment → send both to agent
    user_input = f'📨 Голосовое: "{transcription}"\n💬 Комментарий: {user_comment}'
    response = await run_agent(chat_id, user_input)
    html_response = md_to_html(response)
    for chunk in chunk_message(html_response):
        await message.reply_text(chunk, parse_mode="HTML")
