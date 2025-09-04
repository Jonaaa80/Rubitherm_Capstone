from email.message import Message
# from ..utils.email_utils import extract_bodies
import requests
import certifi
from bs4 import BeautifulSoup
from transformers import pipeline
import warnings
warnings.filterwarnings("ignore")
warnings.filterwarnings("ignore", message=".*max_new_tokens.*")
warnings.filterwarnings("ignore", category=UserWarning)
from time import sleep
import re
from urllib.parse import urlparse, urlunparse
from urllib.parse import urljoin


LOW_VALUE_PHRASES = [
    "u heeft nog geen producten toegevoegd",
    "je winkelwagen is leeg",
    "warenkorb ist leer",
    "ihr warenkorb ist leer",
    "cookie",
    "cookies",
    "accept all",
    "alle akzeptieren",
    "privacy",
    "gdpr",
    "subscribe",
    "newsletter",
    "terms",
    "bedingungen",
    "we use cookies",
    "privacy policy",
]

LOW_VALUE_PHRASES += [
    "token",
    "csrf",
    "xsrf",
    "session",
    "authenticate",
    "authentication",
    "authorized",
    "login",
    "sign in",
    "sign-in",
    "user session",
    "profile",
    "account",
    "accept cookies",
    "cookie policy",
]


def _to_list(val):
    if val is None:
        return []
    if isinstance(val, list):
        return [str(x) for x in val if str(x).strip()]
    if isinstance(val, str):
        return [val] if val.strip() else []
    return [str(val)]


def _normalize_url(u: str) -> str:
    if not u:
        return ""
    s = u.strip().strip('>")\']').strip('<\'"(')
    # quick fix for accidental protocols in middle or missing scheme
    if s.startswith('www.'):
        s = 'http://' + s
    # parse and rebuild
    try:
        p = urlparse(s)
        scheme = p.scheme or 'http'
        netloc = p.netloc or p.path  # handle bare domains
        path = p.path if p.netloc else ''
        clean = urlunparse((scheme, netloc, path, '', '', ''))
        return clean
    except Exception:
        return s


def _filter_low_value_text(text: str) -> str:
    lines = []
    for ln in text.splitlines():
        low = ln.strip().lower()
        if not low:
            continue
        if any(p in low for p in LOW_VALUE_PHRASES):
            continue
        lines.append(ln)
    return "\n".join(lines)


def _extract_meta_summary(soup: BeautifulSoup) -> str:
    # Try meta description variants first
    cand = []
    for name in ("description",):
        tag = soup.find("meta", attrs={"name": name})
        if tag and tag.get("content"):
            cand.append(tag.get("content").strip())
    for prop in ("og:description", "twitter:description"):
        tag = soup.find("meta", attrs={"property": prop}) or soup.find("meta", attrs={"name": prop})
        if tag and tag.get("content"):
            cand.append(tag.get("content").strip())
    # Title + first heading
    title = soup.find("title")
    if title and title.text:
        cand.append(title.text.strip())
    h1 = soup.find("h1")
    if h1 and h1.text:
        cand.append(h1.text.strip())
    # Pick the longest non-empty candidate that is not low-value
    for c in sorted(set(cand), key=lambda x: len(x), reverse=True):
        low = c.lower()
        if any(p in low for p in LOW_VALUE_PHRASES):
            continue
        if len(c.split()) >= 6:
            return c
    return ""


# Load local summarizer
summarizer = pipeline("summarization", model="facebook/bart-large-cnn")
# summarizer = pipeline("summarization", model="t5-small")
# -------------------------------
# 1. Scrape Website Text
# -------------------------------


def scrape_website(url):
    """Fetch page text following redirects, try https, and common about pages.
    Returns (best_text, meta_summary_best) or ("", "") if none.
    """
    def _get(u: str) -> tuple[str, str, str]:
        try:
            # 1) Try with system CA bundle via certifi
            r = requests.get(
                u,
                headers={
                    "User-Agent": "Mozilla/5.0",
                    "Accept-Language": "de-DE,de;q=0.9,en;q=0.8,nl;q=0.7",
                },
                timeout=15,
                allow_redirects=True,
                verify=certifi.where(),
            )
        except requests.exceptions.SSLError as e_ssl:
            # 2) Retry disabling verification (as a last resort) – we still parse text, but log it
            try:
                print(f"SSL verify failed for {u}: {e_ssl}")
                r = requests.get(
                    u,
                    headers={
                        "User-Agent": "Mozilla/5.0",
                        "Accept-Language": "de-DE,de;q=0.9,en;q=0.8,nl;q=0.7",
                    },
                    timeout=15,
                    allow_redirects=True,
                    verify=False,
                )
            except Exception as e2:
                # 3) If https failed, try http downgrade
                if u.startswith("https://"):
                    try:
                        u_http = "http://" + u[len("https://"):]
                        r = requests.get(
                            u_http,
                            headers={
                                "User-Agent": "Mozilla/5.0",
                                "Accept-Language": "de-DE,de;q=0.9,en;q=0.8,nl;q=0.7",
                            },
                            timeout=15,
                            allow_redirects=True,
                            verify=False,
                        )
                    except Exception as e3:
                        print(f"HTTP get failed for {u} (and http fallback): {e3}")
                        return u, "", ""
                else:
                    print(f"HTTP get failed for {u}: {e2}")
                    return u, "", ""
        except Exception as e:
            print(f"HTTP get failed for {u}: {e}")
            return u, "", ""

        final = r.url
        soup = BeautifulSoup(r.text, "html.parser")
        meta_summary = _extract_meta_summary(soup)
        for tag in soup(["script", "style", "noscript"]):
            tag.extract()
        text = soup.get_text(separator="\n", strip=True)
        return final, text, meta_summary

    # Normalize and try https first
    base = _normalize_url(url)
    if base.startswith("http://"):
        https_try = "https://" + base[len("http://"):]
    else:
        https_try = base if base.startswith("https://") else base.replace("http://", "https://")

    tried = []
    candidates = []

    for u in [https_try, base]:
        if u and u not in tried:
            tried.append(u)
            final, text, meta_summary = _get(u)
            text = _filter_low_value_text(text)
            candidates.append((final, text, meta_summary))

    # If homepage fetched, also try common about/company pages on same host
    def _host_root(u: str) -> str:
        try:
            p = urlparse(u)
            return f"{p.scheme}://{p.netloc}/"
        except Exception:
            return u

    roots = { _host_root(candidates[0][0]) } if candidates else set()
    common_paths = [
        "about", "about-us", "company", "over-ons", "wie-wir-sind", "ueber-uns", "über-uns",
        "unternehmen", "firma", "mission", "services", "producten", "products"
    ]
    for root in list(roots):
        for path in common_paths:
            u = urljoin(root, path)
            if u in tried:
                continue
            tried.append(u)
            final, text, meta_summary = _get(u)
            text = _filter_low_value_text(text)
            if len(text.split()) >= 25:
                candidates.append((final, text, meta_summary))

    # Choose the best text by length, prefer meta summary if good
    best_text = ""
    best_meta = ""
    best_len = 0
    for final, txt, meta in candidates:
        if meta and len(meta.split()) >= 6:
            # prefer good meta once found
            if not best_meta or len(meta) > len(best_meta):
                best_meta = meta
        l = len(txt.split())
        if l > best_len:
            best_len = l
            best_text = txt
    return best_text, best_meta

# -------------------------------
# 3. Extract Objectives and Services
# -------------------------------


def extract_objective_service_text(text):
    lines = [p.strip() for p in text.splitlines() if len(p.strip()) > 30]
    if not lines:
        return ""
    # Multilingual keyword sets
    objective_keywords = [
        "mission", "objective", "goal", "vision", "purpose", "focus", "aim",
        "auftrag", "ziel", "vision", "leitbild", "fokus",
        "doel", "missie", "visie",
    ]
    service_keywords = [
        "service", "product", "offer", "specialize", "provide", "solutions", "design", "build", "manufacture",
        "dienstleistung", "produkt", "angebot", "lösungen", "entwickeln", "herstellen",
        "dienst", "producten", "oplossingen",
    ]
    objective_paragraphs = [p for p in lines if any(k in p.lower() for k in objective_keywords)]
    service_paragraphs = [p for p in lines if any(k in p.lower() for k in service_keywords)]
    combined = objective_paragraphs + service_paragraphs
    # Fallback: take first few informative lines
    if not combined:
        combined = lines[:12]
    out = " \n".join(combined)[:4000]
    low = out.lower()
    if any(p in low for p in ("token", "session", "login", "cookie")):
        return ""
    return out

# -------------------------------
# 4. Generate Crisp Summary
# -------------------------------


def generate_summary(text):
    text = text[:2000]  # HuggingFace token limit
    input_length = len(text.split())
    max_length = min(120,   input_length)  # Ensure max_length <= input_length
    min_length = min(40, max_length - 1) if max_length > 40 else 10
    result = summarizer(text, max_length=max_length,
                        min_length=min_length, do_sample=False)
    return result[0]['summary_text']

# ---------------------------------------------------------------------------------------------
# 5. Full Company Analyzer, base on url of company, give high level summary
# ---------------------------------------------------------------------------------------------


def analyze_company(url):
    text, meta = scrape_website(url)
    # If meta looks useful, return it directly
    if meta and len(meta.split()) >= 8 and not any(p in meta.lower() for p in ("token", "session", "login")):
        return meta
    if not text or len(text.split()) < 25:
        return "None"
    objective_service_text = extract_objective_service_text(text)
    if objective_service_text:
        try:
            summary = generate_summary(objective_service_text)
        except Exception:
            summary = objective_service_text[:300]
    else:
        summary = "None"
    return summary


def process(data: dict, email_obj: Message) -> dict:
    url_extracted_data = (data.get("ai_extract_crm", {})
                 .get("extracted_data", {})
                 .get("website"))
    
    url_signature = data.get("signature", {}).get("url")

    raw_urls = _to_list(url_extracted_data) + _to_list(url_signature)
    websites = []
    seen = set()
    for u in raw_urls:
        nu = _normalize_url(u)
        if not nu:
            continue
        if nu not in seen:
            seen.add(nu)
            websites.append(nu)
    print("websites:", websites)
    ai_web_data = {}
    for site in websites:
        summary = analyze_company(site)
        ai_web_data[site] = {"summary": summary}
    ai_web_data["_sources"] = websites
    data.setdefault("ai_web", ai_web_data)

    return data
