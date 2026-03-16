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


PRIVACY_POLICY_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Privacy Policy – Second Brain Bot</title>
<style>
  body { font-family: Arial, sans-serif; max-width: 800px; margin: 40px auto; padding: 0 20px; color: #333; line-height: 1.6; }
  h1 { color: #1a1a1a; } h2 { color: #333; margin-top: 32px; }
  p, li { margin: 8px 0; }
</style>
</head>
<body>
<h1>Privacy Policy</h1>
<p><strong>Application:</strong> Second Brain Bot<br>
<strong>Last updated:</strong> March 2026</p>

<h2>1. Overview</h2>
<p>Second Brain Bot is a personal Telegram bot that helps manage Google Calendar events and Google Tasks using voice and text commands. This privacy policy describes how the application accesses and uses your data.</p>

<h2>2. Data We Access</h2>
<p>With your explicit consent through Google OAuth, the application accesses:</p>
<ul>
  <li><strong>Google Calendar</strong> – to read, create, update, and delete your calendar events.</li>
  <li><strong>Google Tasks</strong> – to read, create, update, complete, and delete your tasks.</li>
</ul>

<h2>3. How We Use Your Data</h2>
<p>Your Google Calendar and Tasks data is used solely to fulfill commands you send to the bot (e.g. "Add an event tomorrow at 10am", "Show my tasks for today"). Data is processed in real time and is not stored beyond what is necessary to respond to your request.</p>

<h2>4. Data Storage</h2>
<p>The application stores the following data locally on a private server:</p>
<ul>
  <li>Your Telegram chat ID (to identify you as a user).</li>
  <li>Your Google OAuth tokens (encrypted at rest), used to authenticate API requests on your behalf.</li>
  <li>A short rolling history of your recent bot interactions (last 6 exchanges), used to provide conversational context.</li>
  <li>Address book entries and reminders you explicitly ask the bot to save.</li>
</ul>
<p>No calendar or task data is stored permanently. It is fetched from Google APIs on demand.</p>

<h2>5. Data Sharing</h2>
<p>Your data is never sold, rented, or shared with any third party. The only external services used are:</p>
<ul>
  <li><strong>Google APIs</strong> (calendar.google.com, tasks.googleapis.com) – to read and write your calendar and tasks.</li>
  <li><strong>OpenAI API</strong> – to transcribe voice messages and interpret natural-language commands. Voice transcriptions and command text are sent to OpenAI for processing.</li>
  <li><strong>Telegram Bot API</strong> – to receive and send messages.</li>
</ul>

<h2>6. Revoking Access</h2>
<p>You can revoke the application's access to your Google account at any time by visiting <a href="https://myaccount.google.com/permissions">Google Account Permissions</a> and removing "Second Brain Bot".</p>

<h2>7. Contact</h2>
<p>For any questions or data deletion requests, contact: <a href="mailto:mregoryt@gmail.com">mregoryt@gmail.com</a></p>
</body>
</html>"""


async def handle_privacy(request: web.Request) -> web.Response:
    return web.Response(text=PRIVACY_POLICY_HTML, content_type="text/html", charset="utf-8")


async def handle_oauth_callback(request: web.Request) -> web.Response:
    code = request.rel_url.query.get("code", "")
    state = request.rel_url.query.get("state", "")
    error = request.rel_url.query.get("error", "")

    if error:
        html = f"<h2>❌ Авторизация отклонена: {error}</h2><p>Вернись в Telegram и попробуй /connect снова.</p>"
        return web.Response(text=html, content_type="text/html", charset="utf-8")

    if not code or not state:
        return web.Response(status=400, text="Missing code or state")

    try:
        chat_id = int(state)
    except ValueError:
        return web.Response(status=400, text="Invalid state")

    try:
        from services.google_auth import exchange_code
        exchange_code(chat_id, code)
        bot = request.app["bot"]
        await bot.send_message(
            chat_id=chat_id,
            text="✅ <b>Google Calendar и Tasks подключены!</b>\nМожешь создавать события и задачи.",
            parse_mode="HTML",
        )
        html = "<h2>✅ Успешно!</h2><p>Авторизация завершена. Можешь закрыть эту страницу и вернуться в Telegram.</p>"
    except Exception as e:
        logger.error(f"OAuth callback error for chat_id={state}: {e}")
        html = f"<h2>❌ Ошибка авторизации</h2><p>{e}</p><p>Вернись в Telegram и попробуй /connect снова.</p>"

    return web.Response(text=html, content_type="text/html", charset="utf-8")


def create_upload_app(bot) -> web.Application:
    app = web.Application(client_max_size=50 * 1024 * 1024)
    app["bot"] = bot
    app.router.add_post("/voice", handle_voice_upload)
    app.router.add_get("/privacy", handle_privacy)
    app.router.add_get("/oauth/callback", handle_oauth_callback)
    return app


async def start_upload_server(bot, port: int = 8765) -> web.AppRunner:
    app = create_upload_app(bot)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logger.info(f"Upload server started on port {port}")
    return runner
