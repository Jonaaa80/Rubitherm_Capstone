# Finale Weiterverarbeitung: z.B. Routing, Speichern, Webhook-Aufruf, Ticket-Erstellung, Auto-Reply, etc.

from email.message import Message
import json

def handle(data: dict, email_obj: Message) -> None:
    # Demo: Ergebnis einfach als JSON ausgeben (in echt: DB, Queue, Webhook, ...)
    print("=== AI CONTROLLER RESULT ===")
    print(json.dumps(data, ensure_ascii=False, indent=2))
