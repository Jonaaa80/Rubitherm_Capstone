from .utils.email_parser import parse_email_body
from .imap_worker import IMAPPoller
from .pipeline import ai_web, ai_extract_crm, ai_predict_intention, ai_controller
#from .pipeline import ai_email_parser_openai_key
from .pipeline import ai_email_parser
from .pipeline import ai_spacy_ner_email_parser
from .utils.email_utils import extract_bodies, get_effective_message 

def handle_email(email_obj):
    original = get_effective_message(email_obj)

    bodies = extract_bodies(original) or []
    body = (bodies[0] if bodies else None) or ""
    data = {
        "meta": {
            "from": original.get("From"),
            "to": original.get("To"),
            "subject": original.get("Subject"),
            "message_id": original.get("Message-ID"),
            "date": original.get("Date"),
        },
        "title": original.get("Subject"),
        "body": body,
    }

    parsed = parse_email_body(body)
    data["parsed"] = parsed

    # Pipeline
    #data = ai_email_parser_openai_key.process(data, original)
    data = ai_email_parser.process(data, original)
    data = ai_spacy_ner_email_parser.process(data, original)
    data = ai_extract_crm.process(data, original)
    data = ai_predict_intention.process(data, original)
    data = ai_web.process(data, original)

    # Final
    ai_controller.handle(data, original)

def main():
    poller = IMAPPoller()
    poller.loop(handle_email)

if __name__ == "__main__":
    main()
