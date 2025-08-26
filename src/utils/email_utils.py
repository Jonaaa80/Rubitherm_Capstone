from email import message_from_bytes
from email.message import Message
from typing import Tuple, Optional

def parse_email(raw_bytes: bytes) -> Message:
    return message_from_bytes(raw_bytes)

def extract_bodies(msg: Message) -> Tuple[Optional[str], Optional[str]]:
    """Gibt (plain_text, html) zurück."""
    if msg.is_multipart():
        plain, html = None, None
        for part in msg.walk():
            ctype = part.get_content_type()
            disp = str(part.get("Content-Disposition"))
            if ctype == "text/plain" and "attachment" not in disp.lower():
                charset = part.get_content_charset() or "utf-8"
                try:
                    plain = part.get_payload(decode=True).decode(charset, errors="replace")
                except Exception:
                    plain = part.get_payload(decode=True).decode("utf-8", errors="replace")
            elif ctype == "text/html" and "attachment" not in disp.lower():
                charset = part.get_content_charset() or "utf-8"
                try:
                    html = part.get_payload(decode=True).decode(charset, errors="replace")
                except Exception:
                    html = part.get_payload(decode=True).decode("utf-8", errors="replace")
        return plain, html
    else:
        ctype = msg.get_content_type()
        if ctype == "text/plain":
            charset = msg.get_content_charset() or "utf-8"
            return msg.get_payload(decode=True).decode(charset, errors="replace"), None
        if ctype == "text/html":
            charset = msg.get_content_charset() or "utf-8"
            return None, msg.get_payload(decode=True).decode(charset, errors="replace")
        # Fallback
        payload = msg.get_payload(decode=True) or b""
        try:
            return payload.decode("utf-8", errors="replace"), None
        except Exception:
            return None, None
