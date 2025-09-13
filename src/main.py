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

    # Defensive pipeline execution: keep previous data if a step returns None or errors
    def _run_step(mod, payload, email):
        try:
            res = mod.process(payload, email)
            if isinstance(res, dict) and res:
                return res
            return payload
        except Exception:
            return payload

    # Pipeline (order matters)
    data = _run_step(ai_email_parser, data, original)
    data = _run_step(ai_spacy_ner_email_parser, data, original)
    data = _run_step(ai_extract_crm, data, original)
    data = _run_step(ai_predict_intention, data, original)
    data = _run_step(ai_web, data, original)

    # Final: controller returns enriched data
    return ai_controller.handle(data, original)

def main():
    poller = IMAPPoller()
    poller.loop(handle_email)

if __name__ == "__main__":
    main()
