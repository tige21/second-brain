"""
Simple HTTP server that accepts audio uploads from iOS Shortcuts,
transcribes them via Whisper, and runs the agent — same pipeline as voice messages.

Endpoint: POST /voice?token=SECRET&chat_id=ID
Body: raw audio bytes (M4A, OGG, MP3, etc.)
"""
import logging
import os
from io import BytesIO
from aiohttp import web

logger = logging.getLogger(__name__)

UPLOAD_TOKEN = os.environ.get("UPLOAD_TOKEN", "")


async def handle_voice_upload(request: web.Request) -> web.Response:
    if request.rel_url.query.get("token", "") != UPLOAD_TOKEN:
        return web.Response(status=403, text="Forbidden")

    chat_id_str = request.rel_url.query.get("chat_id", "")
    try:
        chat_id = int(chat_id_str)
    except (ValueError, TypeError):
        return web.Response(status=400, text="Invalid chat_id")

    from db.database import get_conn
    from db.models import is_user_approved, get_user_token
    conn = get_conn()
    if not is_user_approved(conn, chat_id) or not get_user_token(conn, chat_id):
        return web.Response(status=403, text="Forbidden")

    audio_bytes = await request.read()
    if not audio_bytes:
        return web.Response(status=400, text="Empty body")

    bot = request.app["bot"]

    # Acknowledge immediately so Shortcuts doesn't timeout
    await bot.send_chat_action(chat_id=chat_id, action="typing")

    try:
        from services.openai_stt import transcribe_audio, format_duration
        from agent.executor import run_agent
        from bot.formatters import md_to_html, chunk_message
        from config import VOICE_LONG_THRESHOLD_SECONDS

        # Transcribe
        transcription = await transcribe_audio(audio_bytes, "voice.m4a")

        # Detect duration: try X-Duration-Seconds header first (set by iOS Shortcut),
        # then fall back to mutagen metadata parsing, then 0 (treats as short clip).
        duration_secs = 0
        header_duration = request.headers.get("X-Duration-Seconds", "")
        if header_duration:
            try:
                duration_secs = int(float(header_duration))
            except ValueError:
                pass
        if duration_secs == 0:
            try:
                import mutagen
                meta = mutagen.File(BytesIO(audio_bytes))
                if meta and meta.info:
                    duration_secs = int(meta.info.length)
            except Exception:
                pass
        if duration_secs > VOICE_LONG_THRESHOLD_SECONDS:
            duration_str = format_duration(duration_secs)
            user_input = f"🎙️ [Запись {duration_str}]\n{transcription}"
        else:
            user_input = transcription

        # Run agent
        response = await run_agent(chat_id, user_input)
        html_response = md_to_html(response)
        for chunk in chunk_message(html_response):
            await bot.send_message(chat_id=chat_id, text=chunk, parse_mode="HTML")

    except Exception as e:
        logger.error(f"Upload processing error: {e}")
        await bot.send_message(chat_id=chat_id, text=f"⚠️ Ошибка обработки записи: {e}")

    return web.Response(text="OK")


def create_upload_app(bot) -> web.Application:
    app = web.Application(client_max_size=50 * 1024 * 1024)
    app["bot"] = bot
    app.router.add_post("/voice", handle_voice_upload)
    return app


async def start_upload_server(bot, port: int = 8765) -> web.AppRunner:
    app = create_upload_app(bot)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logger.info(f"Upload server started on port {port}")
    return runner
