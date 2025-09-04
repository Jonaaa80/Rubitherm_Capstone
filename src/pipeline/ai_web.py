import warnings
from urllib.parse import urljoin, urlparse, urlunparse
from email.message import Message
import requests
import certifi
from bs4 import BeautifulSoup
from transformers import pipeline
import urllib3

# ---------------------------
# Setup
# ---------------------------
warnings.filterwarnings("ignore")
warnings.filterwarnings("ignore", message=".*max_new_tokens.*")
warnings.filterwarnings("ignore", category=UserWarning)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

LOW_VALUE_PHRASES = [
    "cookie", "cookies", "accept all", "privacy", "gdpr",
    "subscribe", "newsletter", "terms", "bedingungen",
    "token", "csrf", "xsrf", "session", "authenticate", "login",
]

summarizer = pipeline("summarization", model="t5-large", tokenizer="t5-large")


# ---------------------------
# Helpers
# ---------------------------
def _to_list(val):
    if val is None:
        return []
    if isinstance(val, list):
        return [str(x).strip() for x in val if str(x).strip()]
    if isinstance(val, str):
        return [val.strip()] if val.strip() else []
    return [str(val)]


def _normalize_url(u: str) -> str:
    if not u:
        return ""
    s = u.strip().strip('>")\']').strip('<\'"(')
    if s.startswith('www.'):
        s = 'http://' + s
    try:
        p = urlparse(s)
        scheme = p.scheme or 'http'
        netloc = p.netloc or p.path
        path = p.path if p.netloc else ''
        return urlunparse((scheme, netloc, path, '', '', ''))
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
    cand = []
    for name in ("description",):
        tag = soup.find("meta", attrs={"name": name})
        if tag and tag.get("content"):
            cand.append(tag.get("content").strip())
    for prop in ("og:description", "twitter:description"):
        tag = soup.find("meta", attrs={"property": prop}) or soup.find(
            "meta", attrs={"name": prop})
        if tag and tag.get("content"):
            cand.append(tag.get("content").strip())
    title = soup.find("title")
    if title and title.text:
        cand.append(title.text.strip())
    h1 = soup.find("h1")
    if h1 and h1.text:
        cand.append(h1.text.strip())
    for c in sorted(set(cand), key=lambda x: len(x), reverse=True):
        low = c.lower()
        if any(p in low for p in LOW_VALUE_PHRASES):
            continue
        if len(c.split()) >= 6:
            return c
    return ""


# ---------------------------
# Scraper with SSL fallback
# ---------------------------
def scrape_website(url):
    def _get(u):
        try:
            r = requests.get(
                u, headers={"User-Agent": "Mozilla/5.0"}, timeout=15, verify=certifi.where())
        except requests.exceptions.SSLError as e_ssl:
            # print(f"SSL verify failed for {u}: {e_ssl}, retrying with verify=False")
            try:
                r = requests.get(
                    u, headers={"User-Agent": "Mozilla/5.0"}, timeout=15, verify=False)
            except Exception as e2:
                # print(f"Failed again for {u}: {e2}")
                return "", "", "error"
        except Exception as e:
            # print(f"HTTP get failed for {u}: {e}")
            return "", "", "error"

        final = r.url
        soup = BeautifulSoup(r.text, "html.parser")
        meta_summary = _extract_meta_summary(soup)
        for tag in soup(["script", "style", "noscript"]):
            tag.extract()
        text = soup.get_text(separator="\n", strip=True)
        return text, meta_summary, "success"

    base = _normalize_url(url)
    https_try = "https://" + \
        base[len("http://"):] if base.startswith("http://") else base
    candidates = []
    for u in [https_try, base]:
        txt, meta, status = _get(u)
        if txt:
            txt = _filter_low_value_text(txt)
            candidates.append((txt, meta, status))

    # Try common company pages
    if candidates:
        root = urlparse(candidates[0][0]).scheme + \
            "://" + urlparse(candidates[0][0]).netloc
        common_paths = ["about", "about-us", "company",
                        "mission", "vision", "services", "products"]
        for path in common_paths:
            u = urljoin(root, path)
            txt, meta, status = _get(u)
            if txt:
                txt = _filter_low_value_text(txt)
                candidates.append((txt, meta, status))

    best_text, best_meta = "", ""
    for txt, meta, status in candidates:
        if len(txt.split()) > len(best_text.split()):
            best_text = txt
        if meta and len(meta.split()) > len(best_meta.split()):
            best_meta = meta

    return best_text, best_meta, "success"


# ---------------------------
# Extract objectives & services
# ---------------------------
def extract_objective_service_text(text):
    paragraphs = [p.strip() for p in text.split("\n") if len(p.strip()) > 40]
    objective_keywords = ["mission", "objective",
                          "goal", "vision", "purpose", "focus", "aim"]
    service_keywords = ["service", "product", "offer", "specialize",
                        "provide", "solutions", "design", "build", "manufacture"]

    objective_paragraphs = [p for p in paragraphs if any(
        k in p.lower() for k in objective_keywords)]
    service_paragraphs = [p for p in paragraphs if any(
        k in p.lower() for k in service_keywords)]

    combined = objective_paragraphs + service_paragraphs
    if combined:
        return " ".join(combined[:15])[:4000]
    else:
        return " ".join(paragraphs[:10])[:4000]


# ---------------------------
# Generate summary (~200 words)
# ---------------------------
def generate_summary(text):
    text = text[:4000]
    max_length = min(300, len(text.split()))
    min_length = max(180, int(max_length * 0.7))
    try:
        result = summarizer(text, max_length=max_length,
                            min_length=min_length, do_sample=False, truncation=True)
        return result[0]['summary_text']
    except Exception:
        return " ".join(text.split()[:200])


# ---------------------------
# Analyze company
# ---------------------------
def analyze_company(url):
    text, meta, status = scrape_website(url)
    if status != "success":
        return {"summary": None, "status": status}

    if meta and len(meta.split()) >= 8:
        return {"summary": meta, "status": "success"}

    if not text or len(text.split()) < 25:
        return {"summary": None, "status": "empty"}

    obj_text = extract_objective_service_text(text)
    if obj_text:
        summary = generate_summary(obj_text)
    else:
        summary = None
    return {"summary": summary, "status": "success" if summary else "empty"}


# ---------------------------
# Process data
# ---------------------------
def process(data: dict, email_obj: Message) -> dict:
    url_extracted_data = data.get("ai_extract_crm", {}).get(
        "extracted_data", {}).get("website")
    url_signature = data.get("signature", {}).get("url")
    raw_urls = _to_list(url_extracted_data) + _to_list(url_signature)
    websites, seen = [], set()
    for u in raw_urls:
        nu = _normalize_url(u)
        if nu and nu not in seen:
            seen.add(nu)
            websites.append(nu)

    print("websites:", websites)
    ai_web_data = {}
    for site in websites:
        ai_web_data[site] = analyze_company(site)
    ai_web_data["_sources"] = websites
    data.setdefault("ai_web", ai_web_data)
    return data


# ---------------------------
# Example
# ---------------------------
# if __name__ == "__main__":
#     dummy_data = {
#         "ai_extract_crm": {"extracted_data": {"website": [
#             'nseindia.com', 'https://kit.edu', 'www.mpob.gov.my',
#             'https://mobility.indoramaventures.com/', 'https://www.indoramaventures.com'
#         ]}},
#         "signature": {"url": "research.gla.ac.uk"},
#     }

#     result = process(dummy_data, Message())
#     print("\nFinal structured data:\n", result)
