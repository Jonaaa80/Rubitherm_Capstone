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