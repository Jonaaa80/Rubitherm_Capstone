"""
spaCy/NER-based email signature & contact extractor
--------------------------------------------------
This module provides a lightweight, dependency-friendly variant that mirrors the
shape of ai_email_parser.py's output contract, but uses spaCy NER + heuristics.

Public API:
    - spacy_ner_email_parser(email_text: str) -> dict
      Returns a dict with the JSON contract used in your project:
        {
          "full_name": str | None,
          "role": str | None,
          "company": str | None,
          "address": list[str],
          "phone": list[str],
          "email": list[str],
          "url": list[str]
        }

    - attach_to_data(email_text: str, data: dict) -> dict
      Adds the parsed result under data["spacy_ner_email_parser"].

Design notes:
- Uses spaCy NER to get PERSON/ORG/LOC/GPE entities, then complements with
  regex for phones, emails, urls and address heuristics (PLZ patterns, etc.).
- Robust to missing spaCy model: falls back to a minimal regex-only path.
- Language-agnostic where possible, but tuned to EU/Germanic formats.
"""
from __future__ import annotations

import re
from typing import List, Dict, Optional, Any

try:
    import spacy
    _SPACY_AVAILABLE = True
except Exception:  # pragma: no cover
    spacy = None  # type: ignore
    _SPACY_AVAILABLE = False


# -----------------------------
# Regex utilities
# -----------------------------
_EMAIL_RE = re.compile(r"\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b")
_URL_RE = re.compile(r"\b(?:https?://|www\.)[\w.-/]+\b", re.IGNORECASE)
# Phone patterns accept international and local formats; conservative to avoid noise.
_PHONE_RE = re.compile(r"(?:\+\d[\d\s().\-\/]{5,}|\b(?:\(?0\)?[\d\s().\-\/]{5,})\b)")

# Common EU postal code patterns to help detect address lines
_PLZ_RES = [
    re.compile(r"\b\d{5}\b"),                  # DE/FR/IT/ES generic 5 digits
    re.compile(r"\b\d{4}\b"),                  # DK/NO (can collide; use heuristics)
    re.compile(r"\b\d{3}\s?\d{2}\b"),         # SE 3 2
    re.compile(r"\b\d{2}-\d{3}\b"),           # PL 12-345
    re.compile(r"\b\d{4}\s?[A-Z]{2}\b"),      # NL 1234 AB
    re.compile(r"[A-Z]{1,2}\d[A-Z\d]?\s?\d[A-Z]{2}")  # UK
]

# Legal entity keywords to help find company lines
_COMPANY_HINTS = [
    "gmbh", "ag", "kg", "ohg", "e.k.", "ug", "sarl", "sa", "sas", "s.a.",
    "s.l.", "slu", "bv", "nv", "oy", "ab", "a/s", "s.r.o.", "a.s.", "sp. z o.o.",
    "spa", "srl", "ltd", "plc", "llc", "inc", "e.u.", "ug (haftungsbeschränkt)",
]

# Role/job title keywords (multilingual, non-exhaustive)
_ROLE_HINTS = [
    # DE
    "geschäftsführer", "leiter", "vertrieb", "einkauf", "projektleiter", "projektmanager",
    "ingenieur", "berater", "vertriebsleiter", "assistent", "assistentin", "kundenservice",
    # EN
    "ceo", "cto", "cfo", "sales", "sales manager", "account manager", "engineer", "consultant",
    "director", "manager", "head of", "vp", "president",
    # FR/ES/IT
    "directeur", "ingénieur", "ventas", "director", "direttore", "responsable",
]

_VALedictions = [
    # EN
    "best regards", "kind regards", "sincerely", "thanks", "thank you",
    # DE
    "mit freundlichen grüßen", "beste grüße", "viele grüße", "freundliche grüße",
    # FR/ES/IT
    "cordialement", "bien à vous", "sincères salutations", "saludos", "atentamente", "cordiali saluti",
]


def _load_spacy_model():
    """Try to load a reasonable spaCy model for German/Multilingual text."""
    if not _SPACY_AVAILABLE:
        return None
    candidates = [
        "de_core_news_md",  # good DE NER
        "de_core_news_sm",
        "xx_ent_wiki_sm",  # multilingual small with NER
    ]
    for name in candidates:
        try:
            return spacy.load(name)
        except Exception:
            continue
    return None


from email.message import Message as _StdMessage  # stdlib fallback

def _coerce_to_text(original: Any) -> str:
    """Best-effort conversion of various email objects to a plaintext string.
    Handles: str, bytes, dict-like, stdlib email.message.Message/EmailMessage,
    and common custom attributes (text/body/content/plain/html).
    """
    # 1) Direct cases
    if isinstance(original, str):
        return original
    if isinstance(original, bytes):
        try:
            return original.decode("utf-8", errors="ignore")
        except Exception:
            return original.decode(errors="ignore")

    # 2) stdlib email.message.Message / EmailMessage
    try:
        if isinstance(original, _StdMessage):
            # Prefer text/plain
            try:
                # Python 3.6+ EmailMessage has get_body
                get_body = getattr(original, "get_body", None)
                if callable(get_body):
                    part = get_body(preferencelist=("plain",))
                    if part is not None:
                        payload = part.get_payload(decode=True)
                        if isinstance(payload, (bytes, bytearray)):
                            return payload.decode(part.get_content_charset() or "utf-8", errors="ignore")
                        if isinstance(payload, str):
                            return payload
                # Fallback: walk parts
                parts = []
                for p in original.walk():
                    ctype = p.get_content_type()
                    if ctype == "text/plain":
                        payload = p.get_payload(decode=True)
                        if isinstance(payload, (bytes, bytearray)):
                            parts.append(payload.decode(p.get_content_charset() or "utf-8", errors="ignore"))
                        elif isinstance(payload, str):
                            parts.append(payload)
                if parts:
                    return "\n\n".join(parts)
            except Exception:
                pass
            # Last resort: as string
            try:
                return original.as_string()
            except Exception:
                return str(original)
    except Exception:
        pass

    # 3) dict-like
    try:
        if hasattr(original, "get"):
            for key in ("text", "body", "content", "plain"):
                val = original.get(key)  # type: ignore[attr-defined]
                if isinstance(val, str) and val.strip():
                    return val
    except Exception:
        pass

    # 4) attribute-based
    for attr in ("text", "body", "content", "plain"):
        try:
            val = getattr(original, attr)
            if isinstance(val, str) and val.strip():
                return val
        except Exception:
            continue

    # 5) fallback
    return str(original)


def _segment_current_body(email_text: str) -> str:
    """Heuristic: return latest human-authored body (above quoted separators)."""
    text = email_text.replace("\r\n", "\n").replace("\r", "\n").strip()

    # Cut off common quoted markers
    markers = [
        "-----Original Message-----", "-------- Forwarded message --------",
        "On ", "Am ", "Le ", "El ",
    ]
    cut_idx = len(text)
    for m in markers:
        idx = text.find(m)
        if idx != -1:
            cut_idx = min(cut_idx, idx)
    # Also cut before first block of lines starting with '>'
    gt_idx = text.find("\n>")
    if gt_idx != -1:
        cut_idx = min(cut_idx, gt_idx)
    return text[:cut_idx].strip()


def _candidate_signature_block(body: str) -> str:
    """Attempt to isolate the signature block at the end of the current body.
    Strategy:
      1) try valediction anchor; else
      2) bottom-up collect lines that look like signature (phones/emails/urls/company lines)
    """
    lines = [ln.rstrip() for ln in body.split("\n")]
    # First pass: valediction anchor
    last_val = -1
    lower_lines = [ln.lower().strip() for ln in lines]
    for i, ln in enumerate(lower_lines):
        if any(v in ln for v in _VALedictions):
            last_val = i
    start = max(0, last_val)
    cand = [ln.strip() for ln in lines[start:] if ln.strip()]
    if cand:
        # Keep last 2–14 short lines as a quick heuristic
        tail = []
        for ln in reversed(cand):
            if len(ln) > 160:
                break
            tail.append(ln)
            if len(tail) >= 14:
                break
        if tail:
            return "\n".join(reversed(tail))

    # Second pass: bottom-up signature cues
    cues = ("tel", "telefon", "fax", "mobile", "handy", "cell", "gsm", "email", "e-mail", "www", "http", "@")
    out = []
    started = False
    for raw in reversed(lines):
        ln = raw.strip()
        if not ln:
            if started and len(out) >= 2:
                break
            else:
                continue
        low = ln.lower()
        has_phone = bool(_PHONE_RE.search(ln))
        has_email = bool(_EMAIL_RE.search(ln))
        has_url = bool(_URL_RE.search(ln))
        has_cue = any(c in low for c in cues)
        if has_phone or has_email or has_url or has_cue:
            started = True
            out.append(ln)
            # limit total lines to avoid swallowing whole email
            if len(out) >= 16:
                break
        elif started:
            # Also include a few context lines above the cues (name/company/address)
            out.append(ln)
            if len(out) >= 16:
                break
        else:
            # keep scanning upwards until we hit cues
            continue
    out.reverse()
    # If still empty, fallback to last 8 non-empty lines
    if not out:
        out = [ln.strip() for ln in lines if ln.strip()][-8:]
    return "\n".join(out)


def _pick_full_name_from_ents(ents) -> Optional[str]:
    names = []
    for e in ents:
        if e.label_.lower() in {"person", "per"}:
            val = e.text.strip()
            if val and not val.isupper():
                names.append(val)
    # Prefer the shortest plausible full name near top
    if names:
        names.sort(key=lambda s: (s.count(" "), len(s)))
        return names[0]
    return None


def _pick_company(lines: List[str], ents) -> Optional[str]:
    # Prefer ORG entities
    orgs = [e.text.strip() for e in ents if e.label_.lower() in {"org", "organisation", "organization"}]

    def clean_company_segment(seg: str) -> Optional[str]:
        s = seg.strip()
        if not s:
            return None
        low = s.lower()
        # skip if line has obvious contact hints
        if any(k in low for k in ("tel", "telefon", "fax", "mobile", "handy", "email", "e-mail", "www", "http", "@")):
            return None
        # require a company hint OR be an ORG entity
        has_hint = any(h in low for h in _COMPANY_HINTS)
        if has_hint:
            return s
        return None

    cand = None
    if orgs:
        orgs = sorted(set(orgs), key=len)
        cand = orgs[0]
    else:
        for ln in lines:
            # Some signatures place company + address on one line separated by comma
            parts = [p for p in re.split(r",|\s{2,}", ln) if p.strip()]
            for seg in parts:
                c = clean_company_segment(seg)
                if c:
                    cand = c
                    break
            if cand:
                break
    return cand


def _find_roles(text: str) -> Optional[str]:
    low = text.lower()
    hits = [kw for kw in _ROLE_HINTS if kw in low]
    if hits:
        # return the longest (more specific) match
        return sorted(hits, key=len, reverse=True)[0]
    return None


def _find_emails(text: str) -> List[str]:
    return sorted(set(_EMAIL_RE.findall(text)), key=str.lower)


def _find_urls(text: str) -> List[str]:
    return sorted(set(_URL_RE.findall(text)), key=str.lower)


def _find_phones(text: str) -> List[str]:
    cands = [m.group(0) for m in _PHONE_RE.finditer(text)]
    # Filter likely fax when labeled; keep both otherwise
    return sorted(set(s.strip() for s in cands), key=lambda s: (len(s), s))


def _looks_like_address_line(s: str) -> bool:
    s_clean = s.strip()
    if not s_clean:
        return False
    # contain digits + letters and not only url/email/phone
    if _EMAIL_RE.search(s_clean) or _URL_RE.search(s_clean) or _PHONE_RE.search(s_clean):
        return False
    # Street indicators (language-agnostic selection)
    street_hints = [
        "straße", "str.", "strasse", "allee", "weg", "platz", "ring",
        "rue", "avenue", "av.", "via", "calle", "c/", "road", "rd", "street",
    ]
    low = s_clean.lower()
    if any(h in low for h in street_hints):
        return True
    # Postal code patterns
    if any(rx.search(s_clean) for rx in _PLZ_RES):
        return True
    # Country line
    country_hints = ["germany", "deutschland", "france", "italy", "spain", "poland", "netherlands", "austria"]
    if any(ch in low for ch in country_hints):
        return True
    return False


def _extract_address_lines(sig_block: str) -> List[str]:
    raw_lines = [ln.strip() for ln in sig_block.split("\n") if ln.strip()]
    lines: List[str] = []
    for ln in raw_lines:
        # skip obvious contact lines; they will be handled elsewhere
        low = ln.lower()
        if any(k in low for k in ("tel", "telefon", "fax", "mobile", "handy", "email", "e-mail", "www", "http", "@")):
            continue
        # split comma-joined address lines conservatively
        parts = [p.strip() for p in ln.split(",") if p.strip()]
        if len(parts) > 1:
            lines.extend(parts)
        else:
            lines.append(ln)

    addr = [ln for ln in lines if _looks_like_address_line(ln)]
    # keep order but unique
    seen = set()
    out: List[str] = []
    for ln in lines:
        if ln in addr and ln not in seen:
            seen.add(ln)
            out.append(ln)
    return out


def _nlp_doc(nlp, text: str):
    try:
        return nlp(text) if nlp is not None else None
    except Exception:
        return None



def spacy_ner_email_parser(email_text: str) -> Dict[str, object]:
    """Deprecated. Use extract_generic_entities_text + attach_to_data instead."""
    return {}



def attach_to_data(email_text: str, data: Dict[str, object]) -> Dict[str, object]:
    """
    Attach the parsed output under key 'spacy_ner_entities' to the given data dict,
    using the visible (body_window) part of the email.
    """
    visible = _get_visible_text_from_data(data, email_text)
    ents = extract_generic_entities_text(visible)
    data = dict(data or {})
    data["spacy_ner_entities"] = ents
    return data

def extract_generic_entities_text(text: str) -> List[Dict[str, object]]:
    """Return all generic spaCy NER entities from the given text.
    Output: [{"text", "label", "start", "end"}]
    Filters to standard labels only.
    """
    nlp = _load_spacy_model()
    doc = _nlp_doc(nlp, text)
    if doc is None or not hasattr(doc, "ents"):
        return []
    allowed = {"PERSON", "PER", "ORG", "GPE", "LOC", "DATE", "TIME", "MONEY", "PERCENT"}
    out: List[Dict[str, object]] = []
    for e in doc.ents:
        lbl = e.label_.upper()
        if lbl not in allowed:
            continue
        out.append({
            "text": e.text,
            "label": e.label_,
            "start": int(e.start_char),
            "end": int(e.end_char),
        })
    return out



# Adapter to match main.py's expected interface
def process(data: Dict[str, object], original: Any) -> Dict[str, object]:
    """Adapter to match main.py's expected interface.

    Args:
        data: The running pipeline dict to be updated.
        original: The raw/plaintext email body or other common email object types.

    Returns:
        Updated data dict with key 'spacy_ner_entities'.
    """
    visible = _get_visible_text_from_data(data, original)
    return attach_to_data(visible, data)


__all__ = [
    "attach_to_data",
    "process",
    "extract_generic_entities_text",
]


# --- New helpers for visible text selection ---

def _find_key_recursive(obj: Any, key: str) -> Optional[str]:
    """Search recursively for a string value under the given key in nested dicts/lists."""
    try:
        if isinstance(obj, dict):
            if key in obj and isinstance(obj[key], str) and obj[key].strip():
                return obj[key]
            for v in obj.values():
                res = _find_key_recursive(v, key)
                if isinstance(res, str) and res.strip():
                    return res
        elif isinstance(obj, (list, tuple)):
            for item in obj:
                res = _find_key_recursive(item, key)
                if isinstance(res, str) and res.strip():
                    return res
    except Exception:
        pass
    return None


def _get_visible_text_from_data(data: Dict[str, object], original: Any) -> str:
    """Prefer the 'body_window' from ai_email_parser (visible part), else coerce the original."""
    # Try common nesting: data["ai_email_parser"]["body_window"]
    if isinstance(data, dict):
        aiep = data.get("ai_email_parser") if hasattr(data, "get") else None
        if isinstance(aiep, dict):
            bw = aiep.get("body_window")
            if isinstance(bw, str) and bw.strip():
                return bw
    # Fallback: recursive search anywhere in data
    bw_any = _find_key_recursive(data, "body_window")
    if isinstance(bw_any, str) and bw_any.strip():
        return bw_any
    # Last resort: coerce original
    return _coerce_to_text(original)

"""
spaCy-based Generic NER Extractor (Visible Body Only)
-----------------------------------------------------
This module extracts ONLY standard NER entities (PERSON/PER, ORG, GPE/LOC, DATE,
TIME, MONEY, PERCENT) from the visible email body (ai_email_parser.body_window).
It intentionally omits all non-NER heuristics (phones, emails, urls, addresses, roles).

Public API:
- process(data, original) -> dict
    Updates `data["spacy_ner_entities"]` with the list of entities.
- attach_to_data(email_text, data) -> dict
    Same as above but takes a text; internally chooses `body_window` if present.
- extract_generic_entities_text(text) -> list[dict]
    Returns entities from the provided text only (no body-window selection).
"""
from __future__ import annotations

from typing import List, Dict, Optional, Any

try:
    import spacy
    _SPACY_AVAILABLE = True
except Exception:  # pragma: no cover
    spacy = None  # type: ignore
    _SPACY_AVAILABLE = False


# -----------------------------
# spaCy helpers
# -----------------------------

def _load_spacy_model():
    """Try to load a reasonable spaCy model for German/Multilingual text."""
    if not _SPACY_AVAILABLE:
        return None
    candidates = [
        "de_core_news_md",  # good DE NER
        "de_core_news_sm",
        "xx_ent_wiki_sm",  # multilingual small with NER
    ]
    for name in candidates:
        try:
            return spacy.load(name)
        except Exception:
            continue
    return None


def _nlp_doc(nlp, text: str):
    try:
        return nlp(text) if nlp is not None else None
    except Exception:
        return None


# -----------------------------
# Visible text selection
# -----------------------------
from email.message import Message as _StdMessage  # stdlib fallback

def _coerce_to_text(original: Any) -> str:
    """Best-effort conversion of various email objects to a plaintext string."""
    if isinstance(original, str):
        return original
    if isinstance(original, bytes):
        try:
            return original.decode("utf-8", errors="ignore")
        except Exception:
            return original.decode(errors="ignore")
    try:
        if isinstance(original, _StdMessage):
            try:
                get_body = getattr(original, "get_body", None)
                if callable(get_body):
                    part = get_body(preferencelist=("plain",))
                    if part is not None:
                        payload = part.get_payload(decode=True)
                        if isinstance(payload, (bytes, bytearray)):
                            return payload.decode(part.get_content_charset() or "utf-8", errors="ignore")
                        if isinstance(payload, str):
                            return payload
                parts = []
                for p in original.walk():
                    if p.get_content_type() == "text/plain":
                        payload = p.get_payload(decode=True)
                        if isinstance(payload, (bytes, bytearray)):
                            parts.append(payload.decode(p.get_content_charset() or "utf-8", errors="ignore"))
                        elif isinstance(payload, str):
                            parts.append(payload)
                if parts:
                    return "\n\n".join(parts)
            except Exception:
                pass
            try:
                return original.as_string()
            except Exception:
                return str(original)
    except Exception:
        pass
    try:
        if hasattr(original, "get"):
            for key in ("text", "body", "content", "plain"):
                val = original.get(key)  # type: ignore[attr-defined]
                if isinstance(val, str) and val.strip():
                    return val
    except Exception:
        pass
    for attr in ("text", "body", "content", "plain"):
        try:
            val = getattr(original, attr)
            if isinstance(val, str) and val.strip():
                return val
        except Exception:
            continue
    return str(original)


def _find_key_recursive(obj: Any, key: str) -> Optional[str]:
    """Search recursively for a string value under the given key in nested dicts/lists."""
    try:
        if isinstance(obj, dict):
            if key in obj and isinstance(obj[key], str) and obj[key].strip():
                return obj[key]
            for v in obj.values():
                res = _find_key_recursive(v, key)
                if isinstance(res, str) and res.strip():
                    return res
        elif isinstance(obj, (list, tuple)):
            for item in obj:
                res = _find_key_recursive(item, key)
                if isinstance(res, str) and res.strip():
                    return res
    except Exception:
        pass
    return None


def _get_visible_text_from_data(data: Dict[str, object], original: Any) -> str:
    """Prefer the 'body_window' from ai_email_parser (visible part), else coerce the original."""
    if isinstance(data, dict):
        aiep = data.get("ai_email_parser") if hasattr(data, "get") else None
        if isinstance(aiep, dict):
            bw = aiep.get("body_window")
            if isinstance(bw, str) and bw.strip():
                return bw
    bw_any = _find_key_recursive(data, "body_window")
    if isinstance(bw_any, str) and bw_any.strip():
        return bw_any
    return _coerce_to_text(original)


# -----------------------------
# NER extraction (standard labels only)
# -----------------------------

def extract_generic_entities_text(text: str) -> List[Dict[str, object]]:
    """Return all generic spaCy NER entities from the given text.
    Output: [{"text", "label", "start", "end"}]
    Filters to standard labels only.
    """
    nlp = _load_spacy_model()
    doc = _nlp_doc(nlp, text)
    if doc is None or not hasattr(doc, "ents"):
        return []
    allowed = {"PERSON", "PER", "ORG", "GPE", "LOC", "DATE", "TIME", "MONEY", "PERCENT"}
    out: List[Dict[str, object]] = []
    for e in doc.ents:
        lbl = e.label_.upper()
        if lbl not in allowed:
            continue
        out.append({
            "text": e.text,
            "label": e.label_,
            "start": int(e.start_char),
            "end": int(e.end_char),
        })
    return out


# -----------------------------
# Public API
# -----------------------------

def attach_to_data(email_text: str, data: Dict[str, object]) -> Dict[str, object]:
    """Attach the NER entities under key 'spacy_ner_entities' using the visible body."""
    visible = _get_visible_text_from_data(data, email_text)
    ents = extract_generic_entities_text(visible)
    data = dict(data or {})
    data["spacy_ner_entities"] = ents
    return data


def process(data: Dict[str, object], original: Any) -> Dict[str, object]:
    """Adapter matching main.py interface → updates 'spacy_ner_entities'."""
    visible = _get_visible_text_from_data(data, original)
    return attach_to_data(visible, data)


__all__ = [
    "attach_to_data",
    "process",
    "extract_generic_entities_text",
]