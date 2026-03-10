import os
from dotenv import load_dotenv

load_dotenv()

# Telegram
TELEGRAM_BOT_TOKEN: str = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID: int = int(os.environ["TELEGRAM_CHAT_ID"])

# OpenAI
OPENAI_API_KEY: str = os.environ["OPENAI_API_KEY"]
OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

# Google
GOOGLE_CREDENTIALS_JSON: str = os.getenv("GOOGLE_CREDENTIALS_JSON", "credentials.json")
GOOGLE_TOKEN_JSON: str = os.getenv("GOOGLE_TOKEN_JSON", "token.json")
GOOGLE_CALENDAR_ID: str = os.getenv("GOOGLE_CALENDAR_ID", "primary")
GOOGLE_TASKS_LIST_ID: str = os.getenv("GOOGLE_TASKS_LIST_ID", "@default")

# App
RATE_LIMIT_SECONDS: int = int(os.getenv("RATE_LIMIT_SECONDS", "5"))
OPENAI_PROXY_URL: str | None = os.getenv("OPENAI_PROXY_URL")
DB_PATH: str = os.getenv("DB_PATH", "data/brain.db")
TIMEZONE_OFFSET: int = int(os.getenv("TIMEZONE_OFFSET", "3"))
DEFAULT_TRAVEL_MINUTES: int = 45
VOICE_LONG_THRESHOLD_SECONDS: int = 30
MAX_TELEGRAM_MESSAGE_LENGTH: int = 4000
