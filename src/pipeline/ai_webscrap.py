import requests
from bs4 import BeautifulSoup
import re
from urllib.parse import urljoin


def scrape_text(url):
    """Fetch and clean visible text from a webpage."""
    try:
        resp = requests.get(
            url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        resp.raise_for_status()
    except Exception as e:
        print(f"Error fetching {url}: {e}")
        return ""

    soup = BeautifulSoup(resp.text, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()

    text = soup.get_text(separator=" ", strip=True)
    text = re.sub(r"\s+", " ", text)
    return text


def find_relevant_pages(base_url, keywords):
    """Find pages by keyword relevance."""
    try:
        resp = requests.get(base_url, headers={
                            "User-Agent": "Mozilla/5.0"}, timeout=10)
        resp.raise_for_status()
    except Exception as e:
        print(f"Error fetching {base_url}: {e}")
        return [base_url]

    soup = BeautifulSoup(resp.text, "html.parser")
    links = [a.get("href") for a in soup.find_all("a", href=True)]

    relevant_pages = []
    for link in links:
        if any(k in link.lower() for k in keywords):
            full_link = urljoin(base_url, link)
            if full_link not in relevant_pages:
                relevant_pages.append(full_link)

    return relevant_pages


def summarize_text(text, max_sentences=3):
    """Generate a short, crisp company summary."""
    sentences = re.split(r'(?<=[.!?]) +', text)
    keywords = ["about", "vision", "mission", "objective", "focus", "establish",
                "function", "research", "development", "sustain", "industry"]

    scored = []
    for s in sentences:
        score = sum(k in s.lower() for k in keywords)
        if 40 < len(s) < 250:  # avoid junk sentences
            scored.append((score, s.strip()))

    scored.sort(key=lambda x: (-x[0], len(x[1])))
    top_sentences = [s for _, s in scored[:max_sentences]]
    return " ".join(top_sentences)


def company_profile(base_url):
    """Scrape summary + contacts separately for better results."""
    # Pages for summary
    summary_pages = [base_url] + find_relevant_pages(
        base_url, ["about", "vision", "mission", "who-we-are", "company", "corporate"])

    # Build summary
    summary_text = ""
    for page in summary_pages[:5]:
        summary_text += " " + scrape_text(page)
    summary = summarize_text(summary_text)

    return {
        "url": base_url,
        "summary": summary
    }


# Example usage
if __name__ == "__main__":
    urls = ["https://bathcanalcraft.co.uk",
            "https://www.kit.edu/", "https://mpob.gov.my/"]
    for url in urls:
        profile = company_profile(url)
        print(f"Website:{profile['url']} \nMission: {profile['summary']}\n")
