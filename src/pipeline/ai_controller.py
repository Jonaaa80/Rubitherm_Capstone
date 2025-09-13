def extract_name_from_ai_extractor(crm_email: 'AiExtractCRM', nlp) -> tuple[str, str]:
    """
    Build a full name string from crm_email extracted_data.first_name and last_name,
    then use spaCy NER to split it into (first_name, last_name).
    Returns ("", "") if no valid name is available.
    """
    crm_first = crm_email.extracted_data.first_name or ""
    crm_last = crm_email.extracted_data.last_name or ""
    crm_full_name = f"{crm_first} {crm_last}".strip()
    if crm_full_name:
        return extract_name_from_signature(
            SignatureData(full_name=crm_full_name, role=None, company=None,
                          address=[], phone=[], email=[], url=[]), nlp)
    return ("", "")
# Finale Weiterverarbeitung: z.B. Routing, Speichern, Webhook-Aufruf, Ticket-Erstellung, Auto-Reply, etc.

from email.message import Message
import json
from dataclasses import dataclass, asdict
from typing import List, Optional
from email.utils import parseaddr
import spacy
from ..rest_worker import is_email_exist_in_crm, is_person_name_exist_in_crm, create_person_in_crm 

# Load spaCy model for name extraction (shared across calls)
try:
    # Prefer better German model if available
    nlp = spacy.load("de_core_news_md")
except Exception:
    try:
        # Fallback to multilingual small model
        nlp = spacy.load("xx_ent_wiki_sm")
    except Exception:
        # Last resort: blank multilingual pipeline (no NER)
        nlp = spacy.blank("xx")


@dataclass
class SignatureData:
    full_name: Optional[str]
    role: Optional[str]
    company: Optional[str]
    address: List[str]
    phone: List[str]
    email: List[str]
    url: List[str]


# New dataclass and extraction function for klassifikation_raw
@dataclass
class KlassifikationRaw:
    StatusAngebot: int
    Universität: int
    PhaseCube: int
    PhaseTube: int
    PhaseDrum: int


def extract_klassifikation(data: dict) -> KlassifikationRaw:
    """
    Extracts the klassifikation_raw information from the AI-parsed data and
    returns it as a strongly-typed KlassifikationRaw structure.
    """
    klass = data.get("klassifikation_raw", {})
    return KlassifikationRaw(
        StatusAngebot=klass.get("StatusAngebot", 0),
        Universität=klass.get("Universität", 0),
        PhaseCube=klass.get("PhaseCube", 0),
        PhaseTube=klass.get("PhaseTube", 0),
        PhaseDrum=klass.get("PhaseDrum", 0),
    )

# Dataclass and extraction function for final 'klassifikation'
@dataclass
class Klassifikation:
    StatusAngebot: int
    Universität: int
    PhaseCube: int
    PhaseTube: int
    PhaseDrum: int

def extract_klassifikation_final(data: dict) -> Klassifikation:
    """
    Extracts the final 'klassifikation' information from the AI-parsed data and
    returns it as a strongly-typed Klassifikation structure.
    """
    klass = data.get("klassifikation", {})
    return Klassifikation(
        StatusAngebot=klass.get("StatusAngebot", 0),
        Universität=klass.get("Universität", 0),
        PhaseCube=klass.get("PhaseCube", 0),
        PhaseTube=klass.get("PhaseTube", 0),
        PhaseDrum=klass.get("PhaseDrum", 0),
    )

# New dataclass and extraction function for ai_web
@dataclass
class AiWebEntry:
    url: str
    summary: str
    status: str

@dataclass
class AiWebData:
    entries: List[AiWebEntry]
    sources: List[str]

def extract_ai_web(data: dict) -> AiWebData:
    """
    Extracts the ai_web information and returns it as a strongly-typed AiWebData structure.
    """
    ai_web = data.get("ai_web", {})
    sources = ai_web.get("_sources", [])
    entries: List[AiWebEntry] = []
    for key, value in ai_web.items():
        if key == "_sources":
            continue
        summary = value.get("summary", "")
        status = value.get("status", "")
        entries.append(AiWebEntry(url=key, summary=summary, status=status))
    return AiWebData(entries=entries, sources=sources)


# New dataclasses and extraction function for ai_extract_crm
@dataclass
class AiExtractCRMData:
    first_name: Optional[str]
    last_name: Optional[str]
    company: List[str]
    customer_phone: List[str]
    email: List[str]
    roles: List[str]
    address: List[str]
    website: List[str]
    tags: List[str]

@dataclass
class AiExtractCRM:
    extracted_by: Optional[str]
    extracted_data: AiExtractCRMData

def extract_ai_extract_crm(data: dict) -> AiExtractCRM:
    """
    Extracts the ai_extract_crm information and returns it as a strongly-typed AiExtractCRM structure.
    """
    crm = data.get("ai_extract_crm", {})
    extracted_by = crm.get("extracted_by")
    extracted_data = crm.get("extracted_data", {})

    return AiExtractCRM(
        extracted_by=extracted_by,
        extracted_data=AiExtractCRMData(
            first_name=extracted_data.get("first_name"),
            last_name=extracted_data.get("last_name"),
            company=extracted_data.get("company", []),
            customer_phone=extracted_data.get("customer_phone", []),
            email=extracted_data.get("email", []),
            roles=extracted_data.get("roles", []),
            address=extracted_data.get("address", []),
            website=extracted_data.get("website", []),
            tags=extracted_data.get("tags", []),
        )
    )


# Extended dataclasses and extraction function for updated ai_extract_crm structure
@dataclass
class AiExtractCRMDataExtended:
    first_name: Optional[str]
    last_name: Optional[str]
    company: List[str]
    customer_phone: List[str]
    email: List[str]
    roles: Optional[List[str]]
    address: List[str]
    website: Optional[List[str]]
    message: Optional[str]
    tags: List[str]

@dataclass
class AiExtractCRMExtended:
    extracted_by: Optional[str]
    extracted_data: AiExtractCRMDataExtended

def extract_ai_extract_crm_extended(data: dict) -> AiExtractCRMExtended:
    """
    Extracts the ai_extract_crm information (extended) and returns it as a strongly-typed AiExtractCRMExtended structure.
    Handles cases where customer_phone or address may be a single string instead of a list,
    and includes an optional message field.
    """
    crm = data.get("ai_extract_crm", {})
    extracted_by = crm.get("extracted_by")
    extracted_data = crm.get("extracted_data", {})

    # Normalize fields that may be single values into lists
    def to_list(value):
        if value is None:
            return []
        if isinstance(value, list):
            return value
        return [value]

    return AiExtractCRMExtended(
        extracted_by=extracted_by,
        extracted_data=AiExtractCRMDataExtended(
            first_name=extracted_data.get("first_name"),
            last_name=extracted_data.get("last_name"),
            company=to_list(extracted_data.get("company")),
            customer_phone=to_list(extracted_data.get("customer_phone")),
            email=to_list(extracted_data.get("email")),
            roles=extracted_data.get("roles") if extracted_data.get("roles") else None,
            address=to_list(extracted_data.get("address")),
            website=to_list(extracted_data.get("website")),
            message=extracted_data.get("message"),
            tags=to_list(extracted_data.get("tags")),
        )
    )

# Variant-specific CRM dataclasses (based on extracted_by)
@dataclass
class DirectEmailCRMData:
    first_name: Optional[str]
    last_name: Optional[str]
    company: List[str]
    customer_phone: List[str]
    email: List[str]
    roles: List[str]
    address: List[str]
    website: List[str]
    tags: List[str]
    message: Optional[str] = None  # usually absent in direct emails

@dataclass
class DirectEmailCRM:
    extracted_by: Optional[str]
    extracted_data: DirectEmailCRMData

@dataclass
class FormInquiryCRMData:
    first_name: Optional[str]
    last_name: Optional[str]
    company: List[str]
    customer_phone: List[str]          # normalize string -> [string]
    email: List[str]
    roles: Optional[List[str]]         # may be null
    address: List[str]                 # normalize string -> [string]
    website: Optional[List[str]]       # may be null
    tags: List[str]
    message: Optional[str]             # present for form inquiry

@dataclass
class FormInquiryCRM:
    extracted_by: Optional[str]
    extracted_data: FormInquiryCRMData

def extract_ai_extract_crm_form_variant(data: dict):
    """
    Returns a variant-typed CRM object depending on `extracted_by`:
    - DirectEmailCRM for 'direct_email_extractor'
    - FormInquiryCRM for 'form_inquiry_extractor'
    Normalizes scalar fields to lists where appropriate.
    """
    crm = data.get("ai_extract_crm", {}) or {}
    extracted_by = crm.get("extracted_by")

    def to_list(value):
        if value is None:
            return []
        if isinstance(value, list):
            return value
        return [value]

    payload = crm.get("extracted_data", {}) or {}

    if extracted_by == "form_inquiry_extractor":
        form_data = FormInquiryCRMData(
            first_name=payload.get("first_name"),
            last_name=payload.get("last_name"),
            company=to_list(payload.get("company")),
            customer_phone=to_list(payload.get("customer_phone")),
            email=to_list(payload.get("email")),
            roles=payload.get("roles") if payload.get("roles") else None,
            address=to_list(payload.get("address")),
            website=to_list(payload.get("website")),
            tags=to_list(payload.get("tags")),
            message=payload.get("message"),
        )
        return FormInquiryCRM(extracted_by=extracted_by, extracted_data=form_data)
    else:
        # default to direct email variant
        direct_data = DirectEmailCRMData(
            first_name=payload.get("first_name"),
            last_name=payload.get("last_name"),
            company=to_list(payload.get("company")),
            customer_phone=to_list(payload.get("customer_phone")),
            email=to_list(payload.get("email")),
            roles=to_list(payload.get("roles")),
            address=to_list(payload.get("address")),
            website=to_list(payload.get("website")),
            tags=to_list(payload.get("tags")),
            message=payload.get("message"),
        )
        return DirectEmailCRM(extracted_by=extracted_by, extracted_data=direct_data)

def extract_signature(data: dict) -> SignatureData:
    """
    Extracts the signature information from the AI-parsed data and
    returns it as a strongly-typed SignatureData structure.
    """
    sig = data.get("signature", {})
    return SignatureData(
        full_name=sig.get("full_name"),
        role=sig.get("role"),
        company=sig.get("company"),
        address=sig.get("address", []),
        phone=sig.get("phone", []),
        email=sig.get("email", []),
        url=sig.get("url", []),
    )

def extract_name_from_signature(signature: SignatureData, nlp) -> tuple[str, str]:
    """
    Uses spaCy NER to split the full name from SignatureData into (first_name, last_name).
    Designed to work for European languages and preserve academic/professional titles like 'Dr.'.
    """
    full_name = signature.full_name or ""
    if not full_name.strip():
        return ("", "")
    doc = nlp(full_name)
    # Collect person-like tokens
    tokens = [ent.text for ent in doc.ents if ent.label_ in ("PERSON", "PER")]
    # Fallback: if no entities detected, split by space
    if not tokens:
        parts = full_name.split()
    else:
        parts = " ".join(tokens).split()

    # Preserve title if present (Dr., Prof., etc.)
    title = ""
    first_name = ""
    last_name = ""
    # Simple heuristic: if first token ends with '.' and is short, treat as title
    if parts and (parts[0].endswith(".") or parts[0].lower() in ("dr", "prof", "mr", "mrs")):
        title = parts.pop(0)

    if parts:
        first_name = parts.pop(0)
    if parts:
        last_name = " ".join(parts)

    if title:
        first_name = f"{title} {first_name}".strip()

    return (first_name.strip(), last_name.strip())


# --- Name refinement helpers using email address ---
import re

def _tokenize_name(name: str) -> list[str]:
    """
    Split a name string by common delimiters and whitespace into tokens.
    Keeps tokens with length >= 2 and strips leading/trailing punctuation.
    """
    if not name:
        return []
    parts = re.split(r"[,\|/;]+|\s+", name.strip())
    tokens: list[str] = []
    for p in parts:
        t = re.sub(r"^[^\w]+|[^\w]+$", "", p, flags=re.UNICODE)
        if len(t) >= 2:
            tokens.append(t)
    return tokens

def _best_token_match_in_email(tokens: list[str], email: str) -> str | None:
    """
    Find the longest token that appears in the email's local-part (before @).
    Returns the best matching token, or None if no token matches.
    """
    if not tokens or not email:
        return None
    local = email.split("@", 1)[0].lower()
    best = None
    for tok in tokens:
        lt = tok.lower()
        if lt in local:
            if best is None or len(lt) > len(best):
                best = lt
    if best is None:
        return None
    # Return the original-cased token
    for t in tokens:
        if t.lower() == best:
            return t
    return best

def refine_names_with_email(first_name: str, last_name: str, email: str) -> tuple[str, str]:
    """
    If first_name or last_name contain multiple tokens, try to match tokens against the email address.
    Choose the longest matching token as the refined candidate for that field.
    Otherwise, keep the original value.
    """
    fn_tokens = _tokenize_name(first_name)
    ln_tokens = _tokenize_name(last_name)

    if len(fn_tokens) > 1:
        best_fn = _best_token_match_in_email(fn_tokens, email)
        if best_fn:
            first_name = best_fn

    if len(ln_tokens) > 1:
        best_ln = _best_token_match_in_email(ln_tokens, email)
        if best_ln:
            last_name = best_ln

    return first_name, last_name

def detect_external_emails(from_email: str, signature: SignatureData, crm: AiExtractCRM) -> str:
    """
    Collect candidate emails from:
      - from_email (parsed from meta.from),
      - signature.email (SignatureData),
      - crm.extracted_data.email (AiExtractCRM),
    then filter out any that contain '@rubitherm' (case-insensitive) and de-duplicate.
    Return exactly one email string:
      • Prefer `from_email` if it is among the filtered candidates.
      • Otherwise return the first remaining candidate.
      • Return "" if none remain.
    """
    candidates: List[str] = []

    # 1) Meta.from (already parsed)
    if from_email:
        candidates.append(from_email)

    # 2) From signature block
    if signature and signature.email:
        candidates.extend(signature.email)

    # 3) From ai_extract_crm
    if crm and crm.extracted_data and crm.extracted_data.email:
        candidates.extend(crm.extracted_data.email)

    # Normalize, filter, and de-duplicate
    seen = set()
    result: List[str] = []
    for e in candidates:
        if not e:
            continue
        e_norm = e.strip()
        if not e_norm:
            continue
        lower = e_norm.lower()
        # Ignore any rubitherm address if it contains '@rubitherm'
        if "@rubitherm" in lower:
            continue
        if lower not in seen:
            seen.add(lower)
            result.append(e_norm)

    # Prefer from_email if present among filtered candidates
    fe = (from_email or "").strip()
    if fe:
        fe_low = fe.lower()
        for r in result:
            if r.lower() == fe_low:
                return r
    # Otherwise return the first remaining candidate, or empty string if none
    return result[0] if result else ""

def handle(data: dict, email_obj: Message) -> dict:
    """
    Final processing hook. Returns the `data` dictionary without attaching
    any additional typed structures. Cleans up legacy `_typed` if present.
    """
    # Ensure legacy typed attachments are removed to keep JSON serializable
    if isinstance(data, dict) and "_typed" in data:
        try:
            data.pop("_typed", None)
        except Exception:
            pass

    # Attach typed views for downstream consumers
    signature_data = extract_signature(data)
    klassifikation_raw = extract_klassifikation(data)
    klassifikation = extract_klassifikation_final(data)
    ai_web_data = extract_ai_web(data)

    # Precompute CRM variants for later typed attachment
    extracted_by = (data.get("ai_extract_crm", {}) or {}).get("extracted_by")
    crm_email = extract_ai_extract_crm(data)         # normalized direct-email view
    crm_form = extract_ai_extract_crm_form_variant(data)           # either DirectEmailCRM or FormInquiryCRM
    
    from_addr_header = (data.get("meta", {}) or {}).get("from", "")
    _, from_email = parseaddr(from_addr_header)
    
    data.setdefault("_typed", {})
    data["_typed"]["signature"] = asdict(signature_data)
    data["_typed"]["klassifikation_raw"] = asdict(klassifikation_raw)
    data["_typed"]["klassifikation"] = asdict(klassifikation)
    data["_typed"]["ai_web"] = asdict(ai_web_data)
    data["_typed"]["from_email"] = from_email

    detected_email = detect_external_emails(from_email, signature_data, crm_email)
    data["_typed"]["detected_email"] = detected_email

    # Extract first and last name from signature using spaCy NER
    # Assuming an `nlp` model is available in scope or imported elsewhere
    try:
        first_name, last_name = extract_name_from_signature(signature_data, nlp)
        data["_typed"]["extracted_name_nlp"] = {
            "first_name": first_name,
            "last_name": last_name
        }
    except Exception as e:
        data["_typed"]["extracted_name_nlp"] = {
            "first_name": "",
            "last_name": ""
        }

    # Also apply NLP extraction for names from ai_extract_crm
    try:
        first_name_ai_crm, last_name_ai_crm = extract_name_from_ai_extractor(crm_email, nlp)
    except Exception as e:
        first_name_ai_crm, last_name_ai_crm = ("", "")

    data["_typed"]["extracted_name_ai_extractor"] = {
        "first_name": first_name_ai_crm,
        "last_name": last_name_ai_crm
    }



    # Choose candidate email: prefer detected external email, fallback to from_email
    candidate_email = detected_email or from_email

    # Refine NLP-extracted name from signature using email tokens
    fn_nlp = data["_typed"]["extracted_name_nlp"].get("first_name", "") if "_typed" in data else ""
    ln_nlp = data["_typed"]["extracted_name_nlp"].get("last_name", "") if "_typed" in data else ""
    fn_nlp_ref, ln_nlp_ref = refine_names_with_email(fn_nlp, ln_nlp, candidate_email)
    data["_typed"]["extracted_name_nlp_refined"] = {
        "first_name": fn_nlp_ref,
        "last_name": ln_nlp_ref
    }

    # Refine AI-extractor name using email tokens
    fn_ai = data["_typed"]["extracted_name_ai_extractor"].get("first_name", "") if "_typed" in data else ""
    ln_ai = data["_typed"]["extracted_name_ai_extractor"].get("last_name", "") if "_typed" in data else ""
    fn_ai_ref, ln_ai_ref = refine_names_with_email(fn_ai, ln_ai, candidate_email)
    data["_typed"]["extracted_name_ai_extractor_refined"] = {
        "first_name": fn_ai_ref,
        "last_name": ln_ai_ref
    }

    email_exists = is_email_exist_in_crm(candidate_email)
    fullname_exists = is_person_name_exist_in_crm(fn_nlp_ref, ln_nlp_ref)

    # Create/update only if the record does not fully exist yet (missing email OR missing full name)
    if candidate_email and (not email_exists or not fullname_exists):
        # Try to choose a phone number from signature or CRM
        tel_number = ""
        if signature_data.phone:
            tel_number = signature_data.phone[0]
        elif crm_email.extracted_data.customer_phone:
            # crm_email.extracted_data.customer_phone is a list per our normalization
            tel_number = crm_email.extracted_data.customer_phone[0]
        try:
            create_person_in_crm(
                candidate_email,
                fn_nlp_ref,
                ln_nlp_ref,
                gender="",
                salutation="",
                title="",
                tel=tel_number or ""
            )
        except Exception:
            # Swallow exceptions to avoid breaking the pipeline; consider logging
            pass


    # Exclusive CRM variant handling (use precomputed variants; set exactly one typed key)
    # Ensure variant keys are not stale
    if "_typed" in data:
        for k in ("ai_extract_crm", "ai_extract_crm_form", "ai_extract_crm_direct"):
            if k in data["_typed"]:
                del data["_typed"][k]

    if extracted_by == "form_inquiry_extractor":
        # Only attach the form variant
        data["_typed"]["ai_extract_crm_form"] = asdict(crm_form)
    elif extracted_by == "direct_email_extractor":
        # Only attach the normalized direct-email view
        data["_typed"]["ai_extract_crm"] = asdict(crm_email)
    else:
        # Unknown or missing extractor: attach nothing
        pass



    return data