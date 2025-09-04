
from email.message import Message
from ..utils.email_utils import extract_bodies
from dotenv import load_dotenv
from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate
from langchain.output_parsers import StructuredOutputParser, ResponseSchema

# Lazy init
_initialized = False
_llm = None
_prompt = None
_parser = None
_format_instructions = None


def _init():
    global _initialized, _llm, _prompt, _parser, _format_instructions
    if _initialized:
        return
    load_dotenv()
    _llm = ChatGroq(
        model="llama-3.1-8b-instant",
        temperature=0,
        max_tokens=512,
    )
    schemas = [
        ResponseSchema(
            name="StatusAngebot",
            description="E-Mail enthält eine Angebotsanfrage, 1 wenn ja, 0 wenn nicht, 2 wenn unklar",
            type="Boolean",
        ),
        ResponseSchema(
            name="Universität",
            description="Anfrage von Universitäten oder Studenten, 1 wenn ja, 0 wenn nein, 2 wenn unklar",
            type="Boolean",
        ),
        ResponseSchema(
            name="PhaseCube",
            description="Anfrage enthält das Wort 'PhaseCube', 1 wenn ja, 0 wenn nein, 2 wenn unklar",
            type="Boolean",
        ),
        ResponseSchema(
            name="PhaseTube",
            description="Anfrage enthält das Wort 'PhaseTube', 1 wenn ja, 0 wenn nein, 2 wenn unklar",
            type="Boolean",
        ),
        ResponseSchema(
            name="PhaseDrum",
            description="Anfrage enthält das Wort 'PhaseDrum', 1 wenn ja, 0 wenn nein, 2 wenn unklar",
            type="Boolean",
        ),
    ]
    _parser = StructuredOutputParser.from_response_schemas(schemas)
    _format_instructions = _parser.get_format_instructions()
    _prompt = ChatPromptTemplate.from_template(
        """
Du bist ein Klassifizierer für E-Mails.
Du erhältst eine E-Mail im JSON-Format.

Aufgabe:
- Prüfe, ob es sich um eine Anfrage für ein Angebot handelt.
- Prüfe, ob die Anfrage von einer Universität oder einem Studenten kommt.
- Prüfe ob die Mail das Wort \"PhaseCube\" enthält.
- Prüfe ob die Mail das Wort \"PhaseTube\" enthält.
- Prüfe ob die Mail das Wort \"PhaseDrum\" enthält.
- Antworte mit 1 für Ja und 0 für Nein und 2 für Unklar.
- Antworte ausschließlich im JSON-Format gemäß den Vorgaben.

Hier sind Beispiele für Mail bodys die nach einem Angebot fragen:
"Können sie mir bitte ein Angebot zukommen lassen inkl. Lieferung nach Ingolstadt?"
"Gerne auch ein Angebot über die 1m3 RT69HC, welche Lieferformen sind hier möglich?"
"Ich freue mich über ein entsprechendes Angebot inklusive Versandkosten."
"Ich bitte Sie daher, mir die Preise für die folgenden Produkte jeweils einzeln mitzuteilen:"
"Please provide the offer for PCM encapsulated materials"
"Could you please send me a quotation for the following items?"

Hier sind Beispiele für Mail subjects die nach einem Angebot fragen:
"Anfrage Angebot"
"Anfrage für ein Angebot"
"Bitte um Angebot"
"Angebotserstellung"
"Request for Quotation"
"Quotation Request"
"Request for Quote"
"Request for Pricing"

Hier sind Beispiele für Mails von Universitäten oder Studenten:
"Ich bin Student an der Universität Stuttgart"
"Ich schreibe meine Masterarbeit an der Technischen Universität München"
"Wir sind eine Forschungsgruppe an der Universität Heidelberg"
"Ich bin Doktorand an der Universität Freiburg"
"We are a research team from the University of Cambridge"
"I am a graduate student at MIT working on a thesis"
"Our lab at Stanford University"
"As a student at ETH Zurich, I am conducting experiments"
"I am pursuing my PhD at the University of Tokyo"

Hier ist die E-Mail:
{mail}

Formatvorgaben:
{format_instructions}
"""
    )
    _initialized = True


def process(data: dict, email_obj: Message) -> dict:
    """Notebook-nahe Prozessfunktion. Fügt 'klassifikation' hinzu.
    Bewahrt Kompatibilität: Falls bereits vorhanden, nichts tun.
    """
    if "klassifikation" in data:
        return data
    _init()
    plain, html = extract_bodies(email_obj)
    body = plain or html or ""
    mail_json = {
        "from": email_obj.get("From"),
        "to": email_obj.get("To"),
        "subject": email_obj.get("Subject"),
        "date": email_obj.get("Date"),
        "body": body,
    }
    prompt = _prompt.format(format_instructions=_format_instructions, mail=mail_json)
    try:
        resp = _llm.invoke(prompt)
        parsed = _parser.parse(resp.content)
    except Exception as e:  # noqa: BLE001
        data["klassifikation"] = {"error": str(e)}
        return data
    # Direkt wie im Notebook ohne Normalisierung ablegen
    data["klassifikation_raw"] = parsed
    data["klassifikation"] = parsed
    return data
