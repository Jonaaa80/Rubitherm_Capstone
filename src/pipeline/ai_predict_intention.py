# Platzhalter: Bestimmt die Intention der E-Mail
# Hier würdest du klassifizieren, ob es sich z.B. um Anfrage, Beschwerde, Termin, Spam etc. handelt.

from email.message import Message
from ..utils.email_utils import extract_bodies

KEYWORDS = {
    "meeting": ["termin", "meeting", "call"],
    "complaint": ["beschwerde", "reklamation"],
    "sales": ["angebot", "preis", "kosten"],
}

def process(data: dict, email_obj: Message) -> dict:
  
   

    plain, html = extract_bodies(email_obj)
    text = (plain or html or "").lower()
    data.setdefault("intent", "unknown")
    for label, kws in KEYWORDS.items():
        if any(k in text for k in kws):
            data["intent"] = label
            break
    return data
