import time
import requests
from typing import Tuple
from .config import TENANT_ID, CLIENT_ID, CLIENT_SECRET, TOKEN_SCOPE

class OAuthTokenProvider:
    """Holt und cached Access Tokens via Client Credentials für Exchange Online IMAP (XOAUTH2)."""

    def __init__(self):
        self._access_token = None
        self._expires_at = 0

    def get_token(self) -> str:
        now = time.time()
        if self._access_token and now < self._expires_at - 60:
            return self._access_token
        self._refresh_token()
        return self._access_token

    def _refresh_token(self) -> None:
        token_url = f"https://login.microsoftonline.com/{TENANT_ID}/oauth2/v2.0/token"
        data = {
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "scope": TOKEN_SCOPE,
            "grant_type": "client_credentials",
        }
        resp = requests.post(token_url, data=data, timeout=30)
        resp.raise_for_status()
        payload = resp.json()
        self._access_token = payload["access_token"]
        self._expires_at = time.time() + int(payload.get("expires_in", 3600))
