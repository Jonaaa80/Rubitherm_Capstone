from email import message_from_bytes
from email.message import Message
from typing import Tuple, Optional
from email.utils import parseaddr
import re


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

# Heuristic: extract original sender from quoted header block in body (Outlook inline-forward)
def extract_original_from_body(msg: Message) -> Optional[str]:
    """Tries to recover the original From from an inline-forward quoted header block.
    Looks for lines starting with 'From:' or 'Von:' and extracts `Name <addr>` or `addr`.
    Returns the last matching quoted header block found (useful for cascaded forwards where
    the deepest/last block corresponds to the most recent original message in the chain).
    Returns a raw header-like string (e.g., 'Alice <alice@example.com>') or None.
    """
    try:
        from .email_utils import extract_bodies  # local import guard if structure changes
    except Exception:
        # fallback: assume same module
        pass
    plain, html = extract_bodies(msg)

    def strip_html(h: Optional[str]) -> str:
        if not h:
            return ""
        # very light tag removal for header block detection
        return re.sub(r"<[^>]+>", "", h)

    text = plain or strip_html(html)
    if not text:
        return None

    # Normalize line breaks and whitespace
    lines = [l.strip() for l in text.splitlines() if l.strip()]

    # Patterns: match
    #   From: Name <addr>
    #   From: addr
    #   Von:  Name <addr>
    #   Von:  addr
    patterns = [
        re.compile(r"^(?:From|Von)\s*:\s*(.*?)\s*<([^>]+)>", re.IGNORECASE),
        re.compile(r"^(?:From|Von)\s*:\s*<?([^\s>@]+@[^\s>]+)>?", re.IGNORECASE),
    ]

    last_match = None
    for line in lines:
        for pat in patterns:
            m = pat.search(line)
            if m:
                if len(m.groups()) == 2:
                    name, addr = m.group(1).strip(), m.group(2).strip()
                    last_match = f"{name} <{addr}>" if name else addr
                else:
                    addr = m.group(1).strip()
                    last_match = addr
                # continue scanning to prefer the last header block in cascaded forwards
    return last_match

def get_effective_message(msg: Message) -> Message:
    """Prefer the embedded original message (message/rfc822). If not present,
    try forwarding/redirect headers (e.g., X-Google-Original-From). If that
    fails, heuristically parse Outlook inline-forward quoted blocks in the body.

    If an original sender is detected, overwrite `From` with it and preserve
    the forwarder address in `X-Forwarder-From`. Also mirror to `X-Effective-From`.
    """
    inner = extract_embedded_rfc822(msg)
    if inner:
        return inner

    # 1) Dedicated headers from providers/clients
    original_from = extract_original_from_header(msg)
    if not original_from:
        # 2) Outlook inline-forward body heuristic
        original_from = extract_original_from_body(msg)

    if original_from:
        forwarder = msg.get("From")
        if forwarder and not msg.get("X-Forwarder-From"):
            msg["X-Forwarder-From"] = forwarder
        try:
            if msg.get("From") is not None:
                del msg["From"]
        except Exception:
            pass
        msg["From"] = original_from
        msg["X-Effective-From"] = original_from

    return msg