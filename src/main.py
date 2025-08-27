from .imap_worker import IMAPPoller
from .pipeline import ai_web, ai_extract_person, ai_extract_company, ai_predict_intention, ai_controller
from .utils.email_utils import extract_bodies

def handle_email(email_obj):
    data = {
        "meta": {
            "from": email_obj.get("From"),
            "to": email_obj.get("To"),
            "subject": email_obj.get("Subject"),
            "message_id": email_obj.get("Message-ID"),
            "date": email_obj.get("Date"),
        }
    }

    # Pipeline
    data = ai_extract_person.process(data, email_obj)
    data = ai_extract_company.process(data, email_obj)
    data = ai_predict_intention.process(data, email_obj)
    data = ai_web.process(data, email_obj)

    # Final
    ai_controller.handle(data, email_obj)

def main():
    poller = IMAPPoller()
    poller.loop(handle_email)

if __name__ == "__main__":
    main()
