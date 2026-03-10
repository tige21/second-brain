import io
import httpx
from openai import AsyncOpenAI
from tenacity import retry, stop_after_attempt, wait_fixed
from config import OPENAI_API_KEY, OPENAI_PROXY_URL

_http_client = httpx.AsyncClient(proxy=OPENAI_PROXY_URL) if OPENAI_PROXY_URL else None
_client = AsyncOpenAI(api_key=OPENAI_API_KEY, http_client=_http_client)


_BASE_PROMPT = "Дейлик, встреча, задача, событие, напоминание, перенеси, удали, создай, завтра, сегодня, в понедельник"


@retry(stop=stop_after_attempt(2), wait=wait_fixed(1))
async def transcribe_audio(audio_bytes: bytes, filename: str = "voice.ogg", extra_hints: str = "") -> str:
    """
    Transcribe audio using OpenAI Whisper.
    extra_hints: comma-separated event/task names to improve recognition accuracy.
    Returns transcribed text or raises on failure.
    """
    prompt = f"{_BASE_PROMPT}, {extra_hints}" if extra_hints else _BASE_PROMPT
    audio_file = io.BytesIO(audio_bytes)
    audio_file.name = filename
    result = await _client.audio.transcriptions.create(
        model="whisper-1",
        file=audio_file,
        language="ru",
        prompt=prompt,
    )
    return result.text.strip()


def format_duration(seconds: int) -> str:
    """Format seconds as 'X мин Y сек' or 'Y сек'."""
    if seconds >= 60:
        minutes = seconds // 60
        secs = seconds % 60
        return f"{minutes} мин {secs} сек"
    return f"{seconds} сек"
