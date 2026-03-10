import json
import os
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import Flow

SCOPES = [
    'https://www.googleapis.com/auth/calendar',
    'https://www.googleapis.com/auth/tasks',
]

_REDIRECT_URI = 'urn:ietf:wg:oauth:2.0:oob'
_creds_cache: dict[int, Credentials] = {}


def _migrate_token_json(chat_id: int) -> None:
    """Import legacy token.json into DB (one-time migration for the owner account)."""
    from config import GOOGLE_TOKEN_JSON
    if not os.path.exists(GOOGLE_TOKEN_JSON):
        return
    from db.database import get_conn
    from db.models import get_user_token, save_user_token
    conn = get_conn()
    if get_user_token(conn, chat_id):
        return  # Already migrated
    with open(GOOGLE_TOKEN_JSON, 'r') as f:
        token_data = f.read()
    save_user_token(conn, chat_id, token_data)


def get_credentials(chat_id: int) -> Credentials:
    # Try cache first
    creds = _creds_cache.get(chat_id)
    if creds and creds.valid:
        return creds

    # One-time migration from token.json for the owner
    from config import TELEGRAM_CHAT_ID
    if chat_id == TELEGRAM_CHAT_ID:
        _migrate_token_json(chat_id)

    from db.database import get_conn
    from db.models import get_user_token, save_user_token
    conn = get_conn()
    token_json = get_user_token(conn, chat_id)

    if token_json:
        creds = Credentials.from_authorized_user_info(json.loads(token_json), SCOPES)
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
            save_user_token(conn, chat_id, creds.to_json())
        if creds and creds.valid:
            _creds_cache[chat_id] = creds
            return creds

    raise RuntimeError(
        f"No valid Google credentials for user {chat_id}. Use /connect to authorize."
    )


def get_auth_url() -> str:
    """Generate OAuth authorization URL for manual code flow."""
    from config import GOOGLE_CREDENTIALS_JSON
    flow = Flow.from_client_secrets_file(
        GOOGLE_CREDENTIALS_JSON, scopes=SCOPES, redirect_uri=_REDIRECT_URI
    )
    auth_url, _ = flow.authorization_url(prompt='consent')
    return auth_url


def exchange_code(chat_id: int, code: str) -> None:
    """Exchange authorization code for tokens and persist to DB."""
    from config import GOOGLE_CREDENTIALS_JSON
    from db.database import get_conn
    from db.models import save_user_token

    flow = Flow.from_client_secrets_file(
        GOOGLE_CREDENTIALS_JSON, scopes=SCOPES, redirect_uri=_REDIRECT_URI
    )
    flow.fetch_token(code=code.strip())
    creds = flow.credentials
    conn = get_conn()
    save_user_token(conn, chat_id, creds.to_json())
    _creds_cache[chat_id] = creds
