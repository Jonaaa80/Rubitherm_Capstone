import imaplib
import time
import base64
import ssl
from typing import List, Tuple, Optional
from .oauth import OAuthTokenProvider  # only used for XOAUTH2
from .config import IMAP_HOST, IMAP_PORT, IMAP_USER, IMAP_PASSWORD, AUTH_METHOD, POLL_INTERVAL, CONNECT_TIMEOUT, READ_TIMEOUT
from .utils.email_utils import parse_email

class IMAPPoller:
    """Ein robuster IMAP-Poller, der UNSEEN Mails findet und verarbeitet.
    Hinweis: Für echte Near-Realtime kannst du auf IDLE umstellen (siehe Kommentar unten).
    Unterstützt AUTH_METHOD=LOGIN (Benutzer/Passwort) und AUTH_METHOD=XOAUTH2.
    """

    def __init__(self):
        self.conn: Optional[imaplib.IMAP4_SSL] = None
        self._last_seen_uids = set()
        self.token_provider = OAuthTokenProvider() if AUTH_METHOD.upper() == "XOAUTH2" else None

    def _auth_string(self, access_token: str) -> str:
        # XOAUTH2: base64("user=...\1auth=Bearer <token>\1\1")
        authz = f"user={IMAP_USER}\x01auth=Bearer {access_token}\x01\x01"
        return base64.b64encode(authz.encode()).decode()

    def connect(self) -> None:
        # Timeout nur teilweise von imaplib unterstützt; wir nutzen SSLContext + socket timeouts implizit.
        self.conn = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT, ssl_context=ssl.create_default_context())
        self._authenticate()

    def _authenticate(self) -> None:
        assert self.conn is not None
        method = AUTH_METHOD.upper()
        if method == "XOAUTH2":
            access_token = self.token_provider.get_token()
            xoauth2 = self._auth_string(access_token)
            typ, data = self.conn.authenticate("XOAUTH2", lambda x: xoauth2)
            if typ != "OK":
                raise RuntimeError(f"IMAP XOAUTH2 auth failed: {typ} {data}")
        elif method == "LOGIN":
            typ, data = self.conn.login(IMAP_USER, IMAP_PASSWORD)
            if typ != "OK":
                raise RuntimeError(f"IMAP LOGIN auth failed: {typ} {data}")
        else:
            raise RuntimeError(f"Unsupported AUTH_METHOD: {AUTH_METHOD}")
        typ, _ = self.conn.select("INBOX")
        if typ != "OK":
            raise RuntimeError("Cannot select INBOX")

    def _refresh_auth_if_needed(self) -> None:
        # Bei Auth-Fehlern neu authentifizieren
        try:
            assert self.conn is not None
            typ, _ = self.conn.noop()
            if typ != "OK":
                raise RuntimeError("NOOP not OK, reconnecting")
        except Exception:
            self.safe_reconnect()

    def safe_reconnect(self) -> None:
        self.safe_logout()
        for i in range(5):
            try:
                self.connect()
                return
            except Exception as e:
                time.sleep(min(2 ** i, 30))
        raise RuntimeError("Reconnect failed after retries")

    def safe_logout(self) -> None:
        try:
            if self.conn is not None:
                try:
                    self.conn.logout()
                except Exception:
                    pass
        finally:
            self.conn = None

    def fetch_unseen_uids(self) -> List[bytes]:
        assert self.conn is not None
        typ, data = self.conn.uid("search", None, "UNSEEN")
        if typ != "OK":
            return []
        uids = data[0].split() if data and data[0] else []
        # Dedupliziere bereits gesehene
        new_uids = [u for u in uids if u not in self._last_seen_uids]
        for u in new_uids:
            self._last_seen_uids.add(u)
        return new_uids

    def fetch_email_by_uid(self, uid: bytes) -> bytes:
        assert self.conn is not None

        def _extract_bytes(fetch_data):
            # Server responses vary: look for (tuple) entries with bytes payload
            if not fetch_data:
                return None
            for item in fetch_data:
                if isinstance(item, tuple) and len(item) >= 2 and isinstance(item[1], (bytes, bytearray)):
                    return item[1]
            return None

        def _try_fetch(u: bytes):
            typ, data = self.conn.uid("fetch", u, "(BODY.PEEK[])")
            if typ == "OK":
                payload = _extract_bytes(data)
                if payload:
                    return payload
            # Some servers return RFC822; try fallback
            typ, data = self.conn.uid("fetch", u, "(RFC822)")
            if typ == "OK":
                payload = _extract_bytes(data)
                if payload:
                    return payload
            return None

        # First attempt
        raw = _try_fetch(uid)
        if raw:
            return raw

        # Re-select INBOX and retry (message may have been moved/flag-changed)
        self.conn.select("INBOX")
        raw = _try_fetch(uid)
        if raw:
            return raw

        # Give up; caller may choose to continue to next UID
        raise RuntimeError(f"Fetch failed for UID {uid!r}")

    def loop(self, handler):
        try:
            if self.conn is None:
                self.connect()
            while True:
                self._refresh_auth_if_needed()
                for uid in self.fetch_unseen_uids():
                    try:
                        raw = self.fetch_email_by_uid(uid)
                    except Exception:
                        # Skip this UID if it vanished or couldn't be fetched
                        continue
                    email_obj = parse_email(raw)
                    handler(email_obj)
                time.sleep(POLL_INTERVAL)
        finally:
            self.safe_logout()

    # --- OPTIONAL: IDLE (Near-realtime) ---
    # imaplib hat kein High-Level-IDLE. Man kann es per low-level Command implementieren:
    #   self.conn._simple_command('IDLE')
    #   typ, data = self.conn._command_complete('IDLE')
    # oder eine Lib wie 'imapclient' verwenden (IMAPClient.idle()).
    # Für ein robustes, produktives Setup empfiehlt sich IMAPClient + Idle/Noop-Mix.
