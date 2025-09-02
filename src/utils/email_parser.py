# -*- coding: utf-8 -*-
"""
Email/contact parser with line-wise regex extraction and clustering.
Detects only EMAIL, TEL (phone) and URL fields.
TEL matches are suppressed on lines containing weekday or month names (DE/EN, short/long).

Additionally detects and normalizes common quoted header fields (DE/EN): From/Von, To/An, Cc/Kopie, Bcc/Blindkopie, Subject/Betreff, Date/Datum, Sent/Gesendet, Reply-To/Antwort an, Sender/Absender.
Date normalization to ISO-8601 for SENT/DATE (DE/EN/FR/ES month names).
Header blocks are detected as contiguous segments; segments are returned and also exposed as HEADER_SEGMENT entities.
Return value is simplified to only contiguous clusters; header segments are clusters by definition.

Parameters
----------
strategy : str, optional
    Determines how clusters are selected from the parsed body. Two strategies are supported:
    - "bottom-up" (default): Walks from the bottom of the message upwards, collecting clusters until the first header cluster is found, and returns these clusters (typically the most recent message).
    - "top-down": Returns all clusters from top to bottom, without filtering.
"""

from dataclasses import dataclass, asdict
import re
import html
from typing import List, Dict, Any, Tuple

def _normalize_cluster_lines(clusters: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    for c in clusters:
        items = c.get("items", [])
        if items:
            o_start = min(it.get("line", 0) for it in items)
            o_end = max(it.get("line", 0) for it in items)
            # preserve compact line span
            c["cstart"], c["cend"] = c.get("start_line", o_start), c.get("end_line", o_end)
            # set start/end to original line span
            c["start_line"], c["end_line"] = o_start, o_end
    return clusters

# Header aliases (DE/EN) for quoted header blocks in mail bodies
_HEADER_ALIASES: Dict[str, str] = {
    # From
    r"from": "FROM", r"von": "FROM", r"absender": "FROM",
    # To
    r"to": "TO", r"an": "TO",
    # Cc / Bcc
    r"cc": "CC", r"kopie": "CC", r"kopie an": "CC",
    r"bcc": "BCC", r"blindkopie": "BCC", r"blindkopie an": "BCC",
    # Subject
    r"subject": "SUBJECT", r"betreff": "SUBJECT",
    # Date / Sent
    r"date": "DATE", r"datum": "DATE",
    r"sent": "SENT", r"gesendet": "SENT", r"gesendet am": "SENT",
    # Reply-To / Sender
    r"reply-to": "REPLY_TO", r"antwort an": "REPLY_TO",
    r"sender": "SENDER", r"absenderadresse": "SENDER",
    # French
    r"de": "FROM", r"à": "TO", r"a": "TO", r"cc": "CC", r"cci": "BCC", r"objet": "SUBJECT", r"date": "DATE", r"envoyé": "SENT", r"envoye": "SENT", r"répondre à": "REPLY_TO", r"repondre a": "REPLY_TO", r"expéditeur": "SENDER", r"expediteur": "SENDER",
    # Spanish
    r"de": "FROM", r"para": "TO", r"cc": "CC", r"cco": "BCC", r"asunto": "SUBJECT", r"fecha": "DATE", r"enviado": "SENT", r"responder a": "REPLY_TO", r"remitente": "SENDER",
}
_HEADER_KEYS_PATTERN = re.compile(
    r"^\s*(" + r"|".join(sorted(_HEADER_ALIASES.keys(), key=len, reverse=True)) + r")\s*:\s*(.*)$",
    re.IGNORECASE | re.UNICODE,
)

def _compile_calendar_regex() -> re.Pattern:
    # Weekdays (DE full/short) + (EN full/short)
    weekdays = [
        # German full
        r"montag", r"dienstag", r"mittwoch", r"donnerstag", r"freitag", r"samstag", r"sonntag",
        # German short (optional dot)
        r"mo\.?", r"di\.?", r"mi\.?", r"do\.?", r"fr\.?", r"sa\.?", r"so\.?",
        # English full
        r"monday", r"tuesday", r"wednesday", r"thursday", r"friday", r"saturday", r"sunday",
        # English short (allow variants)
        r"mon\.?", r"tue(?:s)?\.?", r"wed\.?", r"thu(?:r|rs)?\.?", r"fri\.?", r"sat\.?", r"sun\.?",
    ]
    # Months (DE + EN, full/short; handle März/Maerz and Mrz)
    months = [
        # German full
        r"januar", r"februar", r"märz", r"maerz", r"april", r"mai", r"juni", r"juli", r"august", r"september", r"oktober", r"november", r"dezember",
        # German short
        r"jan\.?", r"feb\.?", r"mrz\.?", r"apr\.?", r"jun\.?", r"jul\.?", r"aug\.?", r"sep\.?", r"sept\.?", r"okt\.?", r"nov\.?", r"dez\.?",
        # English full
        r"january", r"february", r"march", r"april", r"may", r"june", r"july", r"august", r"september", r"october", r"november", r"december",
        # English short
        r"jan\.?", r"feb\.?", r"mar\.?", r"apr\.?", r"may\.?", r"jun\.?", r"jul\.?", r"aug\.?", r"sep\.?", r"sept\.?", r"oct\.?", r"nov\.?", r"dec\.?",
    ]
    pattern = r"\b(?:" + "|".join(weekdays + months) + r")\b"
    return re.compile(pattern, re.IGNORECASE | re.UNICODE)

_CAL_RE = _compile_calendar_regex()

_MONTHS_MAP = {
    # English
    "january":1, "jan":1, "february":2, "feb":2, "march":3, "mar":3, "april":4, "apr":4, "may":5, "june":6, "jun":6, "july":7, "jul":7, "august":8, "aug":8, "september":9, "sep":9, "sept":9, "october":10, "oct":10, "november":11, "nov":11, "december":12, "dec":12,
    # German
    "januar":1, "jan":1, "februar":2, "feb":2, "maerz":3, "märz":3, "mrz":3, "april":4, "apr":4, "mai":5, "juni":6, "jun":6, "juli":7, "jul":7, "august":8, "aug":8, "september":9, "sep":9, "oktober":10, "okt":10, "november":11, "nov":11, "dezember":12, "dez":12,
    # French
    "janvier":1, "janv":1, "février":2, "fevrier":2, "févr":2, "fevr":2, "mars":3, "avril":4, "avr":4, "mai":5, "juin":6, "juillet":7, "juil":7, "août":8, "aout":8, "septembre":9, "sept":9, "octobre":10, "oct":10, "novembre":11, "nov":11, "décembre":12, "decembre":12, "déc":12, "dec":12,
    # Spanish
    "enero":1, "ene":1, "febrero":2, "feb":2, "marzo":3, "mar":3, "abril":4, "abr":4, "mayo":5, "junio":6, "jun":6, "julio":7, "jul":7, "agosto":8, "ago":8, "septiembre":9, "setiembre":9, "sep":9, "sept":9, "octubre":10, "oct":10, "noviembre":11, "nov":11, "diciembre":12, "dic":12,
}

def _norm_token(t: str) -> str:
    t = t.strip().lower().replace(".", "")
    t = t.replace("ä", "ae").replace("ö", "oe").replace("ü", "ue").replace("ß", "ss")
    t = t.replace("é", "e").replace("è", "e").replace("ê", "e").replace("á", "a").replace("í", "i").replace("ó", "o").replace("ú", "u").replace("à", "a").replace("ô", "o").replace("ù", "u").replace("ç", "c")
    return t

def _month_name_to_num(name: str) -> int:
    return _MONTHS_MAP.get(_norm_token(name), 0)

def _try_parse_date(value: str) -> str:
    s = value.strip()
    # Remove weekday names and commas
    s = _CAL_RE.sub(" ", s)
    s = re.sub(r",", " ", s)
    # ISO-like: YYYY-MM-DD [HH:MM[:SS]]
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})(?:[ T](\d{2}):(\d{2})(?::(\d{2}))?)?", s)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        hh, mm, ss = (m.group(4) or "00", m.group(5) or "00", m.group(6) or "00")
        return f"{y:04d}-{mo:02d}-{d:02d}T{int(hh):02d}:{int(mm):02d}:{int(ss):02d}"
    # DE: DD.MM.YYYY [HH:MM[:SS]]
    m = re.search(r"(\d{1,2})\.(\d{1,2})\.(\d{4})(?:\s+(\d{1,2}):(\d{2})(?::(\d{2}))?)?", s)
    if m:
        d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        hh, mm, ss = (m.group(4) or "00", m.group(5) or "00", m.group(6) or "00")
        return f"{y:04d}-{mo:02d}-{d:02d}T{int(hh):02d}:{int(mm):02d}:{int(ss):02d}"
    # "DD Month YYYY" [time]
    m = re.search(r"(\d{1,2})\s+([A-Za-zÀ-ÿ\.]+)\s+(\d{4})(?:\s+(\d{1,2}):(\d{2})(?::(\d{2}))?)?", s)
    if m:
        d, mon, y = int(m.group(1)), _month_name_to_num(m.group(2)), int(m.group(3))
        if mon:
            hh, mm, ss = (m.group(4) or "00", m.group(5) or "00", m.group(6) or "00")
            return f"{y:04d}-{mon:02d}-{d:02d}T{int(hh):02d}:{int(mm):02d}:{int(ss):02d}"
    # "Month DD, YYYY" [time]
    m = re.search(r"([A-Za-zÀ-ÿ\.]+)\s+(\d{1,2}),?\s+(\d{4})(?:\s+(\d{1,2}):(\d{2})(?::(\d{2}))?)?", s)
    if m:
        mon, d, y = _month_name_to_num(m.group(1)), int(m.group(2)), int(m.group(3))
        if mon:
            hh, mm, ss = (m.group(4) or "00", m.group(5) or "00", m.group(6) or "00")
            return f"{y:04d}-{mon:02d}-{d:02d}T{int(hh):02d}:{int(mm):02d}:{int(ss):02d}"
    return ""

@dataclass
class MatchItem:
    type: str
    values: List[str]
    line: int      # original line number
    cline: int     # compact line number (ignores empty lines)

def _extract_visible_text(s: str) -> str:
    if not isinstance(s, str):
        return ""
    # Detect *likely* HTML tags. If no real tag markers, treat as plain text.
    if not re.search(r"<\s*(?:/?[A-Za-z]|!DOCTYPE|!--)", s):
        return s
    # Protect angle-bracketed email addresses like <user@example.com>
    s = re.sub(r"<\s*([A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,})\s*>", r"\1", s)
    # Remove script/style
    s = re.sub(r"<script[\s\S]*?</script>", " ", s, flags=re.IGNORECASE)
    s = re.sub(r"<style[\s\S]*?</style>", " ", s, flags=re.IGNORECASE)
    # Convert common block tags to newlines to preserve line structure
    s = re.sub(r"<(br|br/|br\s*/)>", "\n", s, flags=re.IGNORECASE)
    s = re.sub(r"</?(p|div|li|tr|td|th|table|h[1-6])[^>]*>", "\n", s, flags=re.IGNORECASE)
    # Keep anchor inner text only (drop href/src attributes to avoid hidden URLs)
    s = re.sub(r"<a[^>]*>(.*?)</a>", r"\1", s, flags=re.IGNORECASE | re.DOTALL)
    # Drop remaining tags
    s = re.sub(r"<[^>]+>", " ", s)
    # Unescape HTML entities
    s = html.unescape(s)
    # Normalize whitespace
    s = re.sub(r"\r\n|\r", "\n", s)
    s = re.sub(r"\u00A0", " ", s)
    s = re.sub(r"[ \t]{2,}", " ", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()

def parse_header_block(body: str) -> Dict[str, Any]:
    lines = body.splitlines()
    headers_list: List[Dict[str, Any]] = []
    headers: Dict[str, str] = {}
    segments: List[Dict[str, Any]] = []
    i = 0
    compact_idx = 0
    def is_nonempty(s: str) -> bool:
        return bool(s.strip())
    while i < len(lines):
        raw = lines[i]
        line = raw.rstrip("\n")
        if is_nonempty(line):
            compact_idx += 1
        m = _HEADER_KEYS_PATTERN.match(line)
        if not m:
            i += 1
            continue
        seg_start = i
        seg_cstart = compact_idx
        # containers for this segment
        seg_items: List[Dict[str, Any]] = []
        seg_headers: Dict[str, str] = {}
        # collect one header (with continuations)
        while True:
            key_raw = m.group(1)
            value = m.group(2).strip()
            # Continuations
            j = i + 1
            while j < len(lines):
                nxt = lines[j]
                if nxt.strip() == "":
                    break
                if re.match(r"^[\t ]+", nxt):
                    value += " " + nxt.strip()
                    j += 1
                    continue
                if _HEADER_KEYS_PATTERN.match(nxt):
                    break
                else:
                    break
            norm_key = _HEADER_ALIASES.get(key_raw.lower(), key_raw.upper())
            # date normalization for DATE/SENT
            seg_headers[norm_key] = value
            if norm_key in ("DATE", "SENT"):
                iso = _try_parse_date(value)
                if iso:
                    seg_headers[norm_key + "_ISO"] = iso
            seg_items.append({
                "key": key_raw,
                "normalized_key": norm_key,
                "value": value,
                "line": i + 1,
            })
            # keep old behavior for global headers/headers_list
            if norm_key in ("DATE", "SENT"):
                iso = _try_parse_date(value)
                if iso:
                    headers[norm_key + "_ISO"] = iso
            headers[norm_key] = value
            headers_list.append({
                "key": key_raw,
                "normalized_key": norm_key,
                "value": value,
                "line": i + 1,
            })
            i = j
            if i >= len(lines):
                break
            line = lines[i].rstrip("\n")
            if not _HEADER_KEYS_PATTERN.match(line):
                break
            m = _HEADER_KEYS_PATTERN.match(line)
            if is_nonempty(line):
                compact_idx += 1
        # extend segment to the last header line we processed
        seg_end = i - 1 if i > seg_start else i
        # compute compact end by counting non-empty between seg_start..seg_end
        cend = seg_cstart
        for k in range(seg_start + 1, seg_end + 1):
            if is_nonempty(lines[k]):
                cend += 1
        seg_keys = sorted({h["normalized_key"] for h in seg_items})
        segments.append({
            "start_line": seg_start + 1,
            "end_line": seg_end + 1,
            "cstart": seg_cstart,
            "cend": cend,
            "keys": seg_keys,
            "headers": seg_headers,
            "entries": seg_items,
        })
    return {"headers": headers, "headers_list": headers_list, "segments": segments}

def compile_patterns() -> Dict[str, List[re.Pattern]]:
    patterns: Dict[str, List[str]] = {
        "EMAIL": [
            r"\b[a-z0-9._%+\-]+@[a-z0-9.\-]+\.[a-z]{2,}\b",
        ],
        "URL": [
            r"\bhttps?://[^\s)]+",
            r"\bwww\.[a-z0-9\-]+(\.[a-z]{2,}){1,}(/[^\s)]*)?",
        ],
        "TEL": [
            r"(?:\b(?:Tel\.?|Telefon|Phone|Mob\.?|Mobile|Handy)\s*[:\-]?\s*)?"
            r"(?:(?:\+|00)\d{1,3}\s*(?:\(\s*0\s*\)\s*)?)?"  # country code with optional (0)
            r"(?:\(?0?\d{1,5}\)?[\s\u00A0\u202F\-\u2013./·]?)"  # area code with common separators
            r"\d{2,4}(?:[\s\u00A0\u202F\-\u2013./·]?\d{2,4}){1,4}\b"  # groups with common separators
        ],
    }
    return {k: [re.compile(p, re.IGNORECASE | re.UNICODE) for p in v] for k, v in patterns.items()}

def apply_regexes_per_line(
    body: str, patterns: Dict[str, List[re.Pattern]]
) -> Dict[str, List[Tuple[List[str], int, int]]]:
    lines = body.splitlines()
    result: Dict[str, List[Tuple[List[str], int, int]]] = {k: [] for k in patterns.keys()}
    compact_idx = 0
    for idx, raw in enumerate(lines, start=1):
        line = raw.strip()
        if not line:
            continue
        compact_idx += 1
        calendar_line = bool(_CAL_RE.search(line))
        for key, regs in patterns.items():
            if key == "TEL" and calendar_line:
                continue
            hits: List[str] = []
            for r in regs:
                hits.extend([m.group(0) for m in r.finditer(line)])
            if hits:
                dedup = []
                seen = set()
                for h in hits:
                    if h not in seen:
                        dedup.append(h)
                        seen.add(h)
                result[key].append((dedup, idx, compact_idx))
    return {k: v for k, v in result.items() if v}

def flatten_entries(per_type: Dict[str, List[Tuple[List[str], int, int]]]) -> List[MatchItem]:
    flat: List[MatchItem] = []
    for t, items in per_type.items():
        for values, line, cline in items:
            flat.append(MatchItem(type=t, values=values, line=line, cline=cline))
    flat.sort(key=lambda x: x.cline)
    return flat

def cluster_by_lines(entries: List[MatchItem], max_gap: int = 1) -> List[Dict[str, Any]]:
    if not entries:
        return []
    clusters: List[Dict[str, Any]] = []
    current = {
        "start_line": entries[0].cline,
        "end_line": entries[0].cline,
        "items": [asdict(entries[0])],
    }
    for e in entries[1:]:
        if e.cline - current["end_line"] <= max_gap:
            current["end_line"] = e.cline
            current["items"].append(asdict(e))
        else:
            clusters.append(current)
            current = {
                "start_line": e.cline,
                "end_line": e.cline,
                "items": [asdict(e)],
            }
    clusters.append(current)
    return clusters

def _normalize_triples(per_type: Dict[str, List[Tuple[List[str], int, int]]]) -> Dict[str, List[Tuple[List[str], int, int]]]:
    norm: Dict[str, List[Tuple[List[str], int, int]]] = {}
    for k, items in per_type.items():
        if k == "HEADER_SEGMENT":
            # leave as-is; these are already [[values], line]
            norm[k] = items
            continue
        fixed: List[Tuple[List[str], int, int]] = []
        for it in items:
            if isinstance(it, (list, tuple)):
                if len(it) == 3:
                    vals, line, cline = it
                elif len(it) == 2:
                    vals, line = it
                    cline = line
                else:
                    # skip malformed
                    continue
                fixed.append([vals, line, cline])
        if fixed:
            norm[k] = fixed
    return norm

def parse_email_body(body: str, max_gap: int = 1, strategy: str = "bottom-up") -> Dict[str, Any]:
    if not isinstance(body, str):
        body = ""
    body = _extract_visible_text(body)
    hdr = parse_header_block(body)
    pats = compile_patterns()
    per_type = apply_regexes_per_line(body, pats)
    # add EMAILs from header values
    if "EMAIL" not in per_type:
        per_type["EMAIL"] = []
    email_re = pats["EMAIL"][0]
    for h in hdr.get("headers_list", []):
        emails = [m.group(0) for m in email_re.finditer(h.get("value", ""))]
        if emails:
            per_type["EMAIL"].append([emails, h.get("line", 0)])
    # add HEADER_SEGMENT entities
    if "HEADER_SEGMENT" not in per_type:
        per_type["HEADER_SEGMENT"] = []
    for seg in hdr.get("segments", []):
        per_type["HEADER_SEGMENT"].append([seg["keys"], seg["start_line"]])
    # Normalize triples to ensure all non-HEADER_SEGMENT entries are in [vals, line, cline] form
    per_type = _normalize_triples(per_type)
    # Only return clusters, combining clusters from regex matches and header segments.
    flat = flatten_entries({k: v for k, v in per_type.items() if k != "HEADER_SEGMENT"})
    body_clusters = cluster_by_lines(flat, max_gap=max_gap)
    body_clusters = _normalize_cluster_lines(body_clusters)
    # Build header_clusters from header segments
    header_clusters: List[Dict[str, Any]] = []
    for seg in hdr.get("segments", []):
        items = []
        for ent in seg.get("entries", []):
            items.append({
                "type": ent["normalized_key"],
                "values": [ent.get("value", "")],
                "line": ent.get("line", seg.get("start_line", 0)),
                "cline": ent.get("line", seg.get("cstart", 0)),
            })
        header_clusters.append({
            "start_line": seg.get("start_line", 0),
            "end_line": seg.get("end_line", seg.get("start_line", 0)),
            "items": items,
        })
    # Merge and sort clusters
    all_clusters = sorted(body_clusters + header_clusters, key=lambda c: c.get("start_line", 0))

    # Strategy selection
    mode = (strategy or "bottom-up").lower()
    if mode == "bottom-up":
        # Walk from bottom until first real cut (a header cluster) and stop there.
        selected: List[Dict[str, Any]] = []
        i = len(all_clusters) - 1
        HEADER_KEYS = {"FROM","TO","CC","BCC","SUBJECT","DATE","SENT","REPLY_TO","SENDER"}
        while i >= 0:
            c = all_clusters[i]
            selected.append(c)
            # A header cluster contains only/mostly header keys; we detect it by presence of any header key
            if any((it.get("type") in HEADER_KEYS) for it in c.get("items", [])):
                break
            i -= 1
        # Compute body window before reversing
        # Identify cut position (header cluster) from the bottom-up scan
        cut_start_line = 0
        cut_end_line = 0
        if selected:
            last_appended = selected[-1]
            HEADER_KEYS = {"FROM","TO","CC","BCC","SUBJECT","DATE","SENT","REPLY_TO","SENDER"}
            if any((it.get("type") in HEADER_KEYS) for it in last_appended.get("items", [])):
                cut_start_line = last_appended.get("start_line", 0)
                cut_end_line = last_appended.get("end_line", 0)
        # Slice body text INCLUDING the header cut to the end
        lines_all = body.splitlines()
        # 1-based to 0-based index; if no header detected, start from 0
        start_idx = (cut_start_line - 1) if cut_start_line > 0 else 0
        if start_idx < 0:
            start_idx = 0
        body_slice = lines_all[start_idx:]
        # Trim leading/trailing empty lines in the slice
        while body_slice and not body_slice[0].strip():
            body_slice.pop(0)
        while body_slice and not body_slice[-1].strip():
            body_slice.pop()
        # Recompute visible start line after trimming
        visible_start_line = start_idx + 1
        # Adjust for any leading empties we popped by scanning back from original start
        if body_slice:
            # find first non-empty from start_idx in original lines
            for k in range(start_idx, len(lines_all)):
                if lines_all[k].strip():
                    visible_start_line = k + 1
                    break
        body_window = {
            "start_line": visible_start_line if body_slice else 0,
            "end_line": len(lines_all) if body_slice else 0,
            "text": "\n".join(body_slice)
        }
        # Now present clusters in chronological order (ascending by start_line)
        selected.reverse()
        return {"clusters": selected, "strategy": "bottom-up", "body_window": body_window}
    else:
        return {"clusters": all_clusters, "strategy": "top-down"}
