from email.message import Message
# from ..utils.email_utils import extract_bodies
import requests
from bs4 import BeautifulSoup
from transformers import pipeline
import warnings
warnings.filterwarnings("ignore")
warnings.filterwarnings("ignore", message=".*max_new_tokens.*")
warnings.filterwarnings("ignore", category=UserWarning)

# Optional JS rendering
try:
    from requests_html import HTMLSession
    JS_RENDER_AVAILABLE = True
except ImportError:
    JS_RENDER_AVAILABLE = False

# Load local summarizer
summarizer = pipeline("summarization", model="facebook/bart-large-cnn")
# summarizer = pipeline("summarization", model="t5-small")
# -------------------------------
# 1. Scrape Website Text
# -------------------------------


def scrape_website(url):
    text = ""
    try:
        r = requests.get(
            url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        soup = BeautifulSoup(r.text, "html.parser")
        for script in soup(["script", "style", "noscript"]):
            script.extract()
        text = " ".join(soup.stripped_strings)
    except Exception as e:
        print(f"Normal request failed: {e}")

    # Fallback to JS-rendered
    if len(text.split()) < 50 and JS_RENDER_AVAILABLE:
        try:
            session = HTMLSession()
            r = session.get(url)
            r.html.render(timeout=20)
            text = r.html.text
        except Exception as e:
            print(f"JS render failed: {e}")

    return text

# -------------------------------
# 3. Extract Objectives and Services
# -------------------------------


def extract_objective_service_text(text):
    paragraphs = [p.strip() for p in text.split("\n") if len(p.strip()) > 40]

    # Keywords
    objective_keywords = ["mission", "objective",
                          "goal", "vision", "purpose", "focus", "aim"]
    service_keywords = ["service", "product", "offer", "specialize",
                        "provide", "solutions", "design", "build", "manufacture"]

    # Extract paragraphs
    objective_paragraphs = [p for p in paragraphs if any(
        k in p.lower() for k in objective_keywords)]
    service_paragraphs = [p for p in paragraphs if any(
        k in p.lower() for k in service_keywords)]

    combined = objective_paragraphs + service_paragraphs
    if combined:
        return " ".join(combined)
    else:
        # fallback to first few paragraphs
        return " ".join(paragraphs[:10])

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
    text = scrape_website(url)
    objective_service_text = extract_objective_service_text(text)
    if objective_service_text:
        summary = generate_summary(objective_service_text)
    else:
        summary = "None"

    return summary


def process(data: dict, email_obj: Message) -> dict:
    # plain, html = extract_bodies(email_obj)
    if 'websites' in data:
        websites = data['websites']
    else:
        websites = ['https://www.asml.com', 'https://www.liwest.at', 'https://www.novem.com', 'https://www.steinhaus.net',
                    'https://www.ost.ch', 'https://www.audi.de', 'https://www.landpack.de', 'https://www.schaumaplast.de',
                    'https://www.zukunfts.haus', 'https://www.googlemail.com', 'https://www.federation.edu.au']
    websites_summary = []
    for website in websites:
        summary = analyze_company(website)
        websites_summary.append((website, summary))
    data.setdefault('summary', websites_summary)
    print(data)
    return data


process({}, {})
