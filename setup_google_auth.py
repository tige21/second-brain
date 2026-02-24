"""Run this script ONCE locally to authenticate with Google and generate token.json.
Then copy token.json to your VPS.

Usage:
    python setup_google_auth.py
"""
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
import os

SCOPES = [
    'https://www.googleapis.com/auth/calendar',
    'https://www.googleapis.com/auth/tasks',
]

token_path = os.getenv("GOOGLE_TOKEN_JSON", "token.json")
creds_path = os.getenv("GOOGLE_CREDENTIALS_JSON", "credentials.json")

creds = None
if os.path.exists(token_path):
    creds = Credentials.from_authorized_user_file(token_path, SCOPES)

if not creds or not creds.valid:
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
    else:
        flow = InstalledAppFlow.from_client_secrets_file(creds_path, SCOPES)
        creds = flow.run_local_server(port=0)
    with open(token_path, 'w') as f:
        f.write(creds.to_json())

print(f"✅ Token saved to {token_path}")
print(f"   Now copy {token_path} to your VPS.")
