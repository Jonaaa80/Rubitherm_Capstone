from email.message import Message
from ..utils.email_utils import extract_bodies


def process(data: dict, email_obj: Message) -> dict:
    plain, html = extract_bodies(email_obj)
    text = (plain or html or "").lower()
    data.setdefault("website", "sumarize")
   
    return data
