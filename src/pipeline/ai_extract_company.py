# Platzhalter: Extrahiert Firmen-/Organisation-Informationen
# Ersetzt durch LLM oder Regex/Heuristiken.

from email.message import Message

def process(data: dict, email_obj: Message) -> dict:
    to = email_obj.get("To", "")
    subject = email_obj.get("Subject", "")
    data.setdefault("company", {})
    if to.endswith("@yourdomain.com"):
        data["company"]["target_org"] = "yourcompany"
    if "angebot" in subject.lower():
        data["company"]["topic"] = "offer"
    return data
