import io
from openai import AsyncOpenAI
from tenacity import retry, stop_after_attempt, wait_fixed
from config import OPENAI_API_KEY

_client = AsyncOpenAI(api_key=OPENAI_API_KEY)


@retry(stop=stop_after_attempt(2), wait=wait_fixed(1))
async def transcribe_audio(audio_bytes: bytes, filename: str = "voice.ogg") -> str:
    """
    Transcribe audio using OpenAI Whisper.
    Returns transcribed text or raises on failure.
    """
    audio_file = io.BytesIO(audio_bytes)
    audio_file.name = filename
    result = await _client.audio.transcriptions.create(
        model="whisper-1",
        file=audio_file,
        language="ru",
    )
    return result.text.strip()


def format_duration(seconds: int) -> str:
    """Format seconds as 'X мин Y сек' or 'Y сек'."""
    if seconds >= 60:
        minutes = seconds // 60
        secs = seconds % 60
        return f"{minutes} мин {secs} сек"
    return f"{seconds} сек"
