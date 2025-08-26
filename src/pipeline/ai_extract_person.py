# Platzhalter: Extrahiert (oder errät) Personen-bezogene Informationen
# Ersetzt diese Logik durch echten LLM-Aufruf oder Regeln.

from email.message import Message

def process(data: dict, email_obj: Message) -> dict:
    sender = email_obj.get("From", "")
    subject = email_obj.get("Subject", "")
    # naive Heuristik
    data.setdefault("person", {})
    data["person"].setdefault("sender_raw", sender)
    if "<" in sender and ">" in sender:
        name = sender.split("<")[0].strip().strip('\'"')
        data["person"]["name_guess"] = name or data["person"].get("name_guess")
    # subject-based guess
    if "bewerbung" in subject.lower():
        data["person"]["context"] = "job_application"
    return data
