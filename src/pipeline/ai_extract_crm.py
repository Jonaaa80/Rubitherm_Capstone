# Platzhalter: Extrahiert (oder errät) Personen-bezogene Informationen
# Ersetzt diese Logik durch echten LLM-Aufruf oder Regeln.

from email.message import Message
import re
import json
import spacy
from spacy.lang.en import English

# Load spaCy (en_core_web_sm)
nlp = spacy.load("en_core_web_sm")

# Regex to find the start of the signature block
SIGN_OFF_REGEX = re.compile(
    r"(?:Mit freundlichen Grüßen|Freundliche Grüße|Beste Grüße|Viele Grüße|Herzliche Grüße|"
    r"Liebe Grüße|Schöne Grüße|Grüße|Best regards|Kind regards|Regards|Sincerely|"
    r"Yours sincerely|Yours faithfully|Thank you|Thanks)",
    re.IGNORECASE
)

# Regex to find email headers to determine customer block
HEADER_REGEX = re.compile(
    r"^\s*(?:Von:|From:)",
    re.IGNORECASE | re.MULTILINE
)

# List of predefined tags
TAGS_LIST = [
    "heiz", "ish 2025", "kälte", "wärme", "kühlh", "lüftung", "tga",
    "messe", "medi", "pcm", "pharma", "logistik", "plan", "wett",
    "uni", "trak", "spei"
]

# List of generic email domains
GENERIC_DOMAINS = [
    "gmail.com", "outlook.com", "yahoo.com", "hotmail.com", "icloud.com",
    "web.de", "posteo.de", "googlemail.com", "live.com", "aol.com",
    "msn.com", "mail.ru"
]


# -------------------------------
# Signature Block finder
# -------------------------------
def get_signature_block(lines: list) -> list:
    """
    Scans lines from the bottom to find the signature block.
    """
    for i in range(len(lines) - 1, -1, -1):
        if SIGN_OFF_REGEX.search(lines[i]):
            return lines[i+1:]
    return lines[-10:]

# -------------------------------
# Tag Extractor
# -------------------------------
def extract_tags(text: str) -> list:
    """
    Extracts predefined tags from the given text.
    """
    found_tags = set()
    text_lower = text.lower()
    for tag in TAGS_LIST:
        if tag in text_lower:
            found_tags.add(tag.title())
    return list(found_tags)

# -------------------------------
# Form Inquiry Extractor
# -------------------------------
def form_inquiry_extractor(text: str) -> dict:
    data = {}
    name_match = re.search(r"Name:\s*(.*)", text)
    if name_match:
        name_parts = name_match.group(1).strip().split()
        if len(name_parts) >= 2:
            data["first_name"] = name_parts[0]
            data["last_name"] = " ".join(name_parts[1:])
    email_match = re.search(r"E-?Mail:\s*([\w\.-]+@[\w\.-]+)", text)
    if email_match:
        data["email"] = email_match.group(1)
    company_match = re.search(r"Company:\s*(.*)", text)
    if company_match:
        data["company"] = company_match.group(1).strip()
    phone_match = re.search(r"Phone:\s*([\d\+][\d\s]+)", text)
    if phone_match:
        data["customer_phone"] = re.sub(r"\s+", "", phone_match.group(1))
    country_match = re.search(r"Country:\s*(.*)", text)
    if country_match:
        data["country"] = country_match.group(1).strip()
    
    data["message"] = None
    if email_match:
        tail = text[email_match.end():]
        tail = tail.lstrip()
        
        stop_patterns = [
            r"\bVon:\b", r"\bGesendet:\b",
            r"\bAn:\b", r"\bBetreff:\b", r"\bFrom:\b", r"\bSent:\b", r"\bTo:\b", r"\bSubject:\b",
            r"(?:Mit freundlichen Grüßen|Freundliche Grüße|Beste Grüße|Viele Grüße|Herzliche Grüße|"
            r"Liebe Grüße|Schöne Grüße|Grüße|Best greetings|Best regards|Kind regards|Regards|Sincerely|"
            r"Yours sincerely|Yours faithfully|Thank you|Thanks)"
        ]
        
        first_cut = len(tail)
        for p in stop_patterns:
            m = re.search(p, tail, re.IGNORECASE)
            if m:
                first_cut = min(first_cut, m.start())

        candidate = tail[:first_cut].strip()
        
        salutation_re = re.compile(r"(?m)^\s*(Sehr|Dear|Hello|Hi|Guten|Good|Kind)\b", re.IGNORECASE)
        s = salutation_re.search(candidate)
        if s:
            data["message"] = candidate[s.start():].strip()
        else:
            if candidate:
                data["message"] = candidate
            else:
                data["message"] = tail.strip() if tail.strip() else None

    if "country" in data:
        data["address"] = data.pop("country")
    
    return {
        "extracted_data": {
            "first_name": data.get("first_name"),
            "last_name": data.get("last_name"),
            "company": data.get("company"),
            "customer_phone": data.get("customer_phone"),
            "email": data.get("email"),
            "roles": None,
            "address": data.get("address"),
            "website": None,
            "message": data.get("message"),
            "tags": [],
        },
        "extracted_by": "form_inquiry_extractor",
    }

# -------------------------------
# Direct Email Extractor
# -------------------------------
def direct_email_extractor(text: str) -> dict:
    """
    Extracts contact information from direct emails based on the provided logic.
    """
    first_name, last_name, email = None, None, None
    companies = []
    
    # Step 1: Extract Name, Email, and Company from 'Von:/From:' line (Highest priority)
    header_match = re.search(
        r"^\s*(?:Von:|From:)\s*(?P<name_part>.+?)?\s*<(?P<email>[^>]+)>",
        text,
        re.IGNORECASE | re.MULTILINE,
    )

    if header_match:
        email = header_match.group("email").strip()

        # Split name from "Von: Name <email>"
        name_part = header_match.group("name_part")
        if name_part:
            # Clean up the name part and split into first/last name
            clean_name_part = re.sub(r"\(.*\)|['\"]|\s-\s.*", "", name_part).strip()
            # Remove trailing commas
            clean_name_part = re.sub(r",+$", "", clean_name_part)
            name_parts = clean_name_part.split()
            if len(name_parts) >= 2:
                first_name = name_parts[0]
                last_name = " ".join(name_parts[1:])
            else:
                if name_parts:
                    first_name = name_parts[0]

        # Extract company from the domain if it's not generic or internal
        domain = email.split('@')[-1]
        if domain:
            dl = domain.lower()
            if dl not in [d.lower() for d in GENERIC_DOMAINS] and "rubitherm" not in dl:
                companies.append(domain.split('.')[0].replace('-', ' ').replace('_', ' ').title())
                if 'gov.my' in dl:
                    companies = ['MPOB']


    # Step 2: Find signature block for other info
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    signature_lines = get_signature_block(lines)
    signature_text = "\n".join(signature_lines)

    # Fallback: if no explicit first/last name yet, try NER on signature
    if not first_name and not last_name and signature_text:
        doc_sig = nlp(signature_text)
        persons = [ent.text.strip() for ent in doc_sig.ents if ent.label_ in ("PERSON", "PER")]
        if persons:
            # Heuristic: take the first person-like string that isn't a role line
            for cand in persons:
                if any(w.lower() in cand.lower() for w in ("gmbh", "inc", "corp", "director", "manager", "geschaeftsfuehrer", "geschäftsführer")):
                    continue
                parts = cand.split()
                if len(parts) >= 2:
                    first_name, last_name = parts[0], " ".join(parts[1:])
                    break

    # Step 3: Regex-based extraction (for clear patterns)
    emails_from_sig = [
        e for e in re.findall(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}", signature_text)
        if not re.search(r"\.(?:png|jpg|jpeg|gif)@", e, re.IGNORECASE) and not e.lower().startswith("image")
    ]
    raw_websites = re.findall(r"(?:https?://[^\s<>]+|www\.[^\s<>]+)", signature_text)
    websites = []
    for w in raw_websites:
        w = w.strip().strip('>')
        # If in format www.example.com<https://example.com/>, take the https part
        if '<' in w:
            parts = w.split('<')
            # choose the part that looks like it has a scheme
            https_parts = [p for p in parts if p.startswith(('http://', 'https://'))]
            w = https_parts[0] if https_parts else parts[0]
        if w.startswith('www.'):
            w = 'http://' + w
        if w not in websites:
            websites.append(w)
    phones = re.findall(r"(?:\+?\d[\d\s\-\(\)]{6,}\d)", signature_text)
    phones = [re.sub(r"\s{2,}", " ", p).strip() for p in phones]

    # Step 4: Fallback company name from signature block if not found in Von line
    if not companies:
        company_regex = re.compile(
            r"\b(?:GmbH|Ltd|Inc|Corp|LLC|LLP|Co\.|S\.A\.|S\.p\.A\.|Pty|PLC)\b",
            re.IGNORECASE
        )
        for line in signature_lines:
            if company_regex.search(line):
                companies.append(line.strip())
                break

    # Step 5: Extract Roles and Address from signature block
    roles = []
    role_keywords = ['manager', 'director', 'supervisor', 'officer', 'head', 'lead',
                     'coordinator', 'specialist', 'consultant', 'planning', 'purchasing', 'engineer']
    for line in signature_lines:
        line_lower = line.lower()
        if any(role_word in line_lower for role_word in role_keywords):
            roles.append(line.strip())
    
    # Address extraction using spaCy and then a regex fallback
    company_addresses = []
    doc = nlp(signature_text)
    for ent in doc.ents:
        if ent.label_ in ("GPE", "LOC"):
            if re.search(r"\d", ent.text) or len(ent.text.split()) > 1:
                company_addresses.append(ent.text.strip())
    
    # Address Regex Fallback (if spaCy finds nothing)
    if not company_addresses:
        address_regex_fallback = re.compile(
            r"\b[a-zA-Z\s]{8,},?\s*\d{1,}\b"
        )
        for line in signature_lines:
            if address_regex_fallback.search(line) and len(line.strip()) <= 15:
                company_addresses.append(line.strip())

    # Final email list consolidation
    final_emails = []
    if email:
        final_emails.append(email)
    
    for e in emails_from_sig:
        if "rubitherm" not in e.lower() and e not in final_emails:
            final_emails.append(e)
    
    # Clean up phone numbers and other single-value lists
    customer_phone = list(set(phones))
    if not customer_phone:
        customer_phone = None
    elif len(customer_phone) == 1:
        customer_phone = customer_phone[0]

    return {
        "extracted_data": {
            "first_name": first_name,
            "last_name": last_name,
            "company": list(set(companies)),
            "customer_phone": customer_phone,
            "email": list(set(final_emails)),
            "roles": list(set(roles)),
            "address": list(set(company_addresses)),
            "website": list(set(websites)),
            "tags": [],
        },
        "extracted_by": "direct_email_extractor",
    }

# -------------------------------
# Dispatcher
# -------------------------------
def extract_email_data(text: str) -> dict:
    """
    Main function to extract data from an email by first identifying the customer's block
    and then dispatching to the appropriate extractor.
    """
    # Step 1: Find the start of the customer's email block (bottom-up)
    lines = text.splitlines()
    customer_block_start = 0
    for i in range(len(lines) - 1, -1, -1):
        if HEADER_REGEX.search(lines[i]):
            customer_block_start = i
            break
    
    customer_block_text = "\n".join(lines[customer_block_start:])

    # Step 2: Extract tags from the customer block
    tags = extract_tags(customer_block_text)

    # Step 3: Dispatch to the correct extractor based on form-like patterns
    if "Name:" in customer_block_text and "Company:" in customer_block_text and "E-Mail:" in customer_block_text:
        result = form_inquiry_extractor(customer_block_text)
    else:
        result = direct_email_extractor(customer_block_text)

    # Step 4: Add tags to the final result and ensure all fields exist
    result["extracted_data"]["tags"] = tags
    
    # Ensure all required keys exist in the final output
    required_keys = ["first_name", "last_name", "company", "customer_phone", "email", "roles", "address", "website"]
    if result["extracted_by"] == "form_inquiry_extractor":
        for key in required_keys:
            if key not in result["extracted_data"]:
                result["extracted_data"][key] = None
    
    if isinstance(result["extracted_data"].get("company"), str):
        result["extracted_data"]["company"] = [result["extracted_data"]["company"]]
    if isinstance(result["extracted_data"].get("email"), str):
        result["extracted_data"]["email"] = [result["extracted_data"]["email"]]

    result["extracted_data"].setdefault("first_name", None)
    result["extracted_data"].setdefault("last_name", None)
    
    return result

# -------------------------------
# Intergration
# -------------------------------

def process(data: dict, email_obj: Message) -> dict:
    sender = email_obj.get("From", "")
    subject = email_obj.get("Subject", "")
    
    # Get the raw email body
    email_body = ""
    if email_obj.is_multipart():
        for part in email_obj.walk():
            if part.get_content_type() == "text/plain":
                email_body = part.get_payload(decode=True).decode('utf-8', errors='ignore')
                break
    else:
        email_body = email_obj.get_payload(decode=True).decode('utf-8', errors='ignore')


    #extracted_data = extract_email_data(data.get("body", ""))
    extracted_data = extract_email_data(data.get("body", ""))
    



    # Merge extracted data into the main 'data' dictionary
    # Create the 'body' section as requested
    #data.setdefault("ai_extract_crm", {})
    #data["ai_extract_crm"]['extracted_data'].update(extracted_data.get("extracted_data", {}))
    #data["ai_extract_crm"]['extracted_by'].update(extracted_data.get("extracted_data", {}).get("extracted_by",{}))


    crm = data.setdefault("ai_extract_crm", {})
    # 1) extracted_data (Inhalte) mergen
    inner = extracted_data.get("extracted_data", {})
    if isinstance(inner, dict):
        crm.setdefault("extracted_data", {}).update(inner)

    # 2) extracted_by ermitteln (erst Top-Level, sonst nested in extracted_data)
    extracted_by = extracted_data.get("extracted_by")
    if extracted_by is None and isinstance(inner, dict):
        extracted_by = inner.get("extracted_by")

    # Accept either a string (common in our extractors) or a dict
    if isinstance(extracted_by, dict):
        crm["extracted_by"] = {**crm.get("extracted_by", {}), **extracted_by}
    elif isinstance(extracted_by, str):
        crm["extracted_by"] = extracted_by
    else:
        # fallback for older extractors: name not provided
        crm.setdefault("extracted_by", "ai_extract_crm")
    return data