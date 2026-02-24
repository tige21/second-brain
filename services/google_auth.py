import os
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request

SCOPES = [
    'https://www.googleapis.com/auth/calendar',
    'https://www.googleapis.com/auth/tasks',
]

_creds: Credentials | None = None


def get_credentials() -> Credentials:
    global _creds
    from config import GOOGLE_CREDENTIALS_JSON, GOOGLE_TOKEN_JSON

    if _creds and _creds.valid:
        return _creds

    if os.path.exists(GOOGLE_TOKEN_JSON):
        _creds = Credentials.from_authorized_user_file(GOOGLE_TOKEN_JSON, SCOPES)

    if _creds and _creds.expired and _creds.refresh_token:
        _creds.refresh(Request())
        with open(GOOGLE_TOKEN_JSON, 'w') as f:
            f.write(_creds.to_json())

    if not _creds or not _creds.valid:
        raise RuntimeError(
            "No valid Google credentials. Run: python setup_google_auth.py"
        )
    return _creds
