from email import message_from_bytes
from email.message import Message
from typing import Tuple, Optional
from email.utils import parseaddr


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


def extract_embedded_rfc822(msg: Message) -> Message | None:
    """Gibt die erste eingebettete Originalmail (message/rfc822) zurück – oder None."""
    for part in msg.walk():
        if part.get_content_type() == "message/rfc822":
            payload = part.get_payload()
            # Manche MUAs liefern eine Liste, andere direkt eine Message
            if isinstance(payload, list) and payload:
                inner = payload[0]
                if isinstance(inner, Message):
                    return inner
            if isinstance(payload, Message):
                return payload
            raw = part.get_payload(decode=True)
            if raw:
                try:
                    return message_from_bytes(raw)
                except Exception:
                    pass
    return None


# Helper to extract original sender from forwarding/redirect headers
def extract_original_from_header(msg: Message) -> Optional[str]:
    """Try to find the original sender from forwarding/redirect headers.
    Checks Apple Mail/Gmail style and generic variants.
    Returns a raw header value (may include angle brackets) or None.
    """
    candidates = [
        "X-Google-Original-From",  # Gmail when redirecting via Apple Mail
        "X-Original-From",
        "Original-From",
        "Resent-From",            # redirect-like flow
    ]
    for h in candidates:
        val = msg.get(h)
        if val:
            # validate it looks like an address
            name, addr = parseaddr(val)
            if addr:
                return val
    return None

def get_effective_message(msg: Message) -> Message:
    """Prefer the embedded original message (message/rfc822). If not present,
    try Apple Mail/Gmail forwarding headers to recover the original sender.
    If such a header is found, overwrite From with original and keep the
    forwarder's address in X-Forwarder-From for downstream use.
    """
    inner = extract_embedded_rfc822(msg)
    if inner:
        return inner

    original_from = extract_original_from_header(msg)
    if original_from:
        # preserve the forwarder address
        forwarder = msg.get("From")
        if forwarder and not msg.get("X-Forwarder-From"):
            msg["X-Forwarder-From"] = forwarder
        # replace From with the detected original sender
        try:
            if msg.get("From") is not None:
                del msg["From"]
        except Exception:
            pass
        msg["From"] = original_from
        # also expose explicitly for consumers if needed
        msg["X-Effective-From"] = original_from
    return msg