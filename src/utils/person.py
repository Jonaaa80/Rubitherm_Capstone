from typing import Optional
from pydantic import BaseModel

import json
import re
from json import JSONDecodeError

try:
    import ollama  # type: ignore
except Exception as e:  # pragma: no cover
    ollama = None
    _OLLAMA_IMPORT_ERROR = e


class PersonInfo(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    title: Optional[str] = None
    company: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    city: Optional[str] = None
    country: Optional[str] = None
    website: Optional[str] = None
    linkedin: Optional[str] = None


# --- Extraction prompt and helpers ---

PROMPT_SYSTEM = """
You are an information extractor.
Return ONLY valid, minified JSON for the requested fields.
No prose, no code fences, no explanations, no markdown.
If a field is unknown, use null. Do not invent data.
The JSON object MUST have exactly these keys:
{"first_name": null, "last_name": null, "title": null, "company": null, "email": null, "phone": null, "city": null, "country": null, "website": null, "linkedin": null}
""".strip()

def make_user_prompt(email_text: str) -> str:
    return f"""
Extract the following fields from the email text:

- first_name
- last_name
- title
- company
- email
- phone
- city
- country
- website
- linkedin

Rules:
- Return a single JSON object with exactly these keys.
- Use null when unknown.
- Do not include any extra keys.

Email text:
\"\"\"{email_text}\"\"\"
""".strip()

def _extract_json_from_text(text: str) -> dict:
    """Extract a JSON object from text that may contain prose around it."""
    # Strip ```json ... ``` or ``` ... ``` fences if present
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL | re.IGNORECASE)
    if fenced:
        text = fenced.group(1)

    # Find all JSON object candidates and pick the longest
    candidates = re.findall(r"\{.*?\}", text, re.DOTALL)
    if not candidates:
        raise ValueError("No JSON object found in model response")
    best = max(candidates, key=len)
    return json.loads(best)

def extract_person_info_via_ollama(email_text: str) -> PersonInfo:
    """Call Ollama with a strict prompt, parse JSON, and return a validated PersonInfo."""
    if ollama is None:
        raise RuntimeError(
            "The 'ollama' package is not available. Install and start Ollama, "
            f"original import error: {_OLLAMA_IMPORT_ERROR!r}"
        )

    # --- Attempt 1: chat with JSON format enforced ---
    resp1 = ollama.chat(
        model="gpt-oss:20b",
        messages=[
            {"role": "system", "content": PROMPT_SYSTEM},
            {"role": "user", "content": make_user_prompt(email_text)},
        ],
        format="json",
        options={"temperature": 0},
        stream=False,
    )
    content = resp1.get("message", {}).get("content") or ""

    # --- Attempt 2: chat without JSON mode (some models/templates don't support 'format') ---
    if not content.strip():
        resp2 = ollama.chat(
            model="gpt-oss:20b",
            messages=[
                {"role": "system", "content": PROMPT_SYSTEM},
                {"role": "user", "content": make_user_prompt(email_text)},
            ],
            options={"temperature": 0},
            stream=False,
        )
        content = resp2.get("message", {}).get("content") or ""

    # --- Attempt 3: generate fallback (some setups prefer generate over chat) ---
    if not content.strip():
        prompt = PROMPT_SYSTEM + "\n\n" + make_user_prompt(email_text)
        resp3 = ollama.generate(
            model="gpt-oss:20b",
            prompt=prompt,
            options={"temperature": 0},
            stream=False,
        )
        content = resp3.get("response", "") or ""

    if not content.strip():
        raise RuntimeError("Ollama returned an empty response content after chat+generate attempts")

    # First try: direct JSON
    try:
        data = json.loads(content)
    except JSONDecodeError:
        # Fallback: extract JSON from mixed text
        data = _extract_json_from_text(content)

    # Validate against Pydantic model
    return PersonInfo.model_validate(data)


# Demo: validate from dict and Ollama extraction
if __name__ == "__main__":
    # Demo A: validate from dict
    example_dict = {
        "first_name": "Anna",
        "last_name": "Musterfrau",
        "title": "Dr.",
        "company": "Beispiel GmbH",
        "email": "anna.musterfrau@example.com",
        "phone": "+49 30 1234567",
        "city": "Berlin",
        "country": "Deutschland",
        "website": "https://beispiel.de",
        "linkedin": "https://linkedin.com/in/annamusterfrau"
    }
    person = PersonInfo.model_validate(example_dict)
    #print("Dict → PersonInfo:", person)

    # Demo B: extraction via Ollama (example email text)
    sample_email_text = (
        "Hallo, ich bin Dr. Anna Musterfrau, Product Lead bei Beispiel GmbH in Berlin, Deutschland. "
        "Sie erreichen mich unter anna.musterfrau@example.com oder +49 30 1234567. "
        "Meine Webseite ist https://beispiel.de und mein LinkedIn: https://linkedin.com/in/annamusterfrau"
    )
    email_text_1 = """Hey Dana, 
steps: 

1. Please check if the current shipping address is correct. You can update your shipping address anytime online in your account settings. 

2. Please give us the name that is displayed on the mailbox if the card has to be delivered to your workplace or an address which does not show your name on the mailbox. 

3. Please give us a call or reply to this e-mail, once your shipping address is up-to-date. Afterwards we will re-send your MasterCard to you and you can start enjoying N26 right away. 

4. If we do not receive a reply from you by 31.08.2016, we will assume you are probably not interested in N26 anymore. In that case we will have to cancel your account. 

If you have any further questions, please do not hesitate to contact us. 
Or check out our support center to find answers right away: https://n26.com/en/support/ 

Kind regards, 

Beatrice 
+49 (0) 30 364 286 880 
N26 Customer Service 
Klosterstraße 62 | 10179 Berlin"""

    email_text_2 = """Hey folks,

We’re excited to welcome you at Spiced this coming Tuesday, 24.06.2025!

In this email, you'll find all the details you'll need for your first day. For questions or concerns, please do not hesitate to reach out.

Spiced Address:

Ritterstr 12-14, 10969
Berlin Closest U-Bahn Moritzplatz (U8)
We're located to the right as you walk into the Hof.

Mobility
If you are coming to the school by bike you can park it in Hof 4. 

Arrival Time
Please arrive by 9:00 AM so that you can settle in and get some coffee/tea before diving into your first day. We will kick off the day at 9:15 AM with check-ins, a tour and welcome session - then move on to our regular curriculum. We'll finish the day by 6:00 PM.

Please bring the following items:

Laptop & power cord
Adapter (if you are from outside Germany)
20 EUR cash - exact change - as a deposit for your entry key card. You will get this back when you return the key card to us after the course
If you prefer to work with a monitor, you will need a cable to connect your laptop to a monitor (Thunderbolt - HDMI)
Headphones
SPICED provides coffee, tea and milk in our kitchen area. There are kettles, microwaves and fridges for your use.

Your Communication Platform: Discord
We’ll be using Discord as our main platform for announcements, group collaboration, and community chats throughout the Bootcamp.

How to Get Started:

Create a Discord account at discord.com

Join our server 👉 https://discord.gg/TRbqwQv4s7

Set up your profile with your real name and assign yourself the role for your Bootcamp (e.g., Web Dev, UX/UI, Cybersecurity).

Choose your cohort channel and start exploring!

💬 You’ll find channels for updates, Q&A, teamwork, and casual conversations.
🔔 Don’t forget to adjust your notification settings so you stay in the loop without the noise.

For more details on how Discord handles your data, you can check their Privacy Policy.


Read through our Student Guidebook. You have already signed the document as part of your student agreement.

And one last thing - please make sure to fill out our Emergency Contact form before the start of the bootcamp.



We are looking forward to meeting you in person! 🌶️


Keep it spicy,

Your Program Team

--
Filip Vuković (he/him)
Program Manager


filip@spiced-academy.com

www.spiced-academy.com

Ritterstrasse 12-14, 10969 Berlin
"""


    if ollama is not None:
        try:
            for label, txt in [
                ("sample_email_text", sample_email_text),
                ("email_text_1", email_text_1),
                ("email_text_2", email_text_2),
            ]:
                extracted = extract_person_info_via_ollama(txt)
                print(f"Ollama → PersonInfo ({label}):", extracted)
        except Exception as e:
            print("Ollama extraction failed:", e)
    else:
        print("Ollama not available; skipping Ollama demo.")