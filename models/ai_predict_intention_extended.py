# AI classification of emails by intention / content.

from email.message import Message
from ..utils.email_utils import extract_bodies

# Lazy init Flags / Container
_initialized = False
_llm_model = None
_prompt_template = None
_output_parser = None
_format_instructions = None
_parse_warnings_count = 0

# Allowed value sets
_ALLOWED = {
    "StatusAngebot": {0, 1, 2},
    "Universität": {0, 1, 2},
    "PhaseCube": {0, 1},
    "PhaseTube": {0, 1},
    "PhaseDrum": {0, 1},
}
_TRUE_TOKENS = {"1", "ja", "yes", "true", "y"}
_FALSE_TOKENS = {"0", "nein", "no", "false", "n"}


def _tok_to_int(raw, field):
    allowed = _ALLOWED[field]
    has_unsure = 2 in allowed
    if raw is None:
        return 2 if has_unsure else 0
    if isinstance(raw, int):
        return raw if raw in allowed else (2 if has_unsure else 0)
    s = str(raw).strip().lower()
    if s in _TRUE_TOKENS:
        return 1 if 1 in allowed else max(allowed)
    if s in _FALSE_TOKENS:
        return 0
    try:
        v = int(s)
        return v if v in allowed else (2 if has_unsure else 0)
    except Exception:  # noqa: BLE001
        return 2 if has_unsure else 0


def _normalize(parsed: dict):
    warnings = []
    normed = {}
    for field in _ALLOWED.keys():
        original = parsed.get(field)
        value = _tok_to_int(original, field)
        normed[field] = value
        if original is None:
            warnings.append(f"{field}: missing -> {value}")
        elif not (isinstance(original, int) and original == value):
            # Only warn if representation changed
            if str(original).strip().lower() not in (str(value),):
                warnings.append(f"{field}: '{original}' -> {value}")
    return normed, warnings

def _init():  # noqa: D401
    """Initialise once LLM, schema, parser and prompt."""
    global _initialized, _llm_model, _prompt_template, _output_parser, _format_instructions
    if _initialized:
        return
    # Imports only here to keep module import fast / optional deps
    from dotenv import load_dotenv
    from langchain_groq import ChatGroq
    from langchain_core.prompts import ChatPromptTemplate
    from langchain.output_parsers import StructuredOutputParser, ResponseSchema

    load_dotenv()

    _llm_model = ChatGroq(
        model="llama-3.1-8b-instant",
        temperature=0,
        max_tokens=512,
    )

    response_schemas = [
        ResponseSchema(
            name="StatusAngebot",
            description="E-Mail enthält eine Angebotsanfrage, 1 wenn ja, 0 wenn nicht, 2 wenn unklar",
            type="Integer",
        ),
        ResponseSchema(
            name="Universität",
            description="Anfrage von Universitäten oder Studenten, 1 wenn ja, 0 wenn nein, 2 wenn unklar",
            type="Integer",
        ),
        ResponseSchema(
            name="PhaseCube",
            description="Anfrage enthält das Wort 'PhaseCube', 1 wenn ja, 0 wenn nein (niemals 2)",
            type="Integer",
        ),
        ResponseSchema(
            name="PhaseTube",
            description="Anfrage enthält das Wort 'PhaseTube', 1 wenn ja, 0 wenn nein (niemals 2)",
            type="Integer",
        ),
        ResponseSchema(
            name="PhaseDrum",
            description="Anfrage enthält das Wort 'PhaseDrum', 1 wenn ja, 0 wenn nein (niemals 2)",
            type="Integer",
        ),
    ]

    _output_parser = StructuredOutputParser.from_response_schemas(response_schemas)
    _format_instructions = _output_parser.get_format_instructions()

    # Prompt (vereinfacht aus Notebook übernommen)
    from langchain_core.prompts import ChatPromptTemplate  # re-import for clarity
    _prompt_template = ChatPromptTemplate.from_template(
        """
Du bist ein Klassifizierer für E-Mails.
Du erhältst eine E-Mail im JSON-Format.

Aufgabe:
- Prüfe, ob es sich um eine Anfrage für ein Angebot handelt.
- Prüfe, ob die Anfrage von einer Universität oder einem Studenten kommt.
- Prüfe ob die Mail das Wort "PhaseCube" enthält.
- Prüfe ob die Mail das Wort "PhaseTube" enthält.
- Prüfe ob die Mail das Wort "PhaseDrum" enthält.
- Antworte für StatusAngebot und Universität mit 1 für Ja, 0 für Nein und 2 für Unklar.
- Antworte für PhaseCube / PhaseTube / PhaseDrum ausschließlich mit 0 (Nein) oder 1 (Ja). Falls unklar -> 0.
- Antworte ausschließlich im JSON-Format gemäß den Vorgaben.

Hier sind Beispiele für Mail bodys die nach einem Angebot fragen:
1. "ich würde ca 5 Kilo von dem PCM RT47 benötigen. Können sie mir bitte ein Angebot zukommen lassen inkl. Lieferung zur Audi AG Ingolstadt?"
2. "Könnten Sie uns daher bitte ein Angebot für ein Muster sowie für verschiedene Gebindegrößen erstellen?"
3. "Gerne auch ein Angebot über die 1m3 RT69HC, welche Lieferformen sind hier möglich?"
4. "Ich freue mich über ein entsprechendes Angebot inklusive Versandkosten."
5. "Um jedoch eine endgültige Entscheidung treffen zu können, benötige ich die wirtschaftlichen und finanziellen Details zu jedem einzelnen Produkt. Ich bitte Sie daher, mir die Preise für die folgenden Produkte jeweils einzeln mitzuteilen:"
6. "Please provide the offer for PCM encapsulated materials for the cold storage unit for the parameters below"

Hier sind Beispiele für Mail subjects die nach einem Angebot fragen:
1. "Anfrage Angebot PCM"
2. "Anfrage Angebot"
3. "Anfrage für ein Angebot"
4. "Bitte um Angebot"
5. "Angebotserstellung"
6. "Request for Quotation"
7. "Quotation Request"
8. "Request for Quote"
9. "Quote Request"
10. "Request for Pricing"

Hier sind Beispiele für Mails von Universitäten oder Studenten:
1. "Ich bin Student an der Universität Stuttgart und arbeite derzeit an einem Projekt"
2. "Ich schreibe meine Masterarbeit an der Technischen Universität München"
3. "Wir sind eine Forschungsgruppe an der Universität Heidelberg"
4. "Als Student der RWTH Aachen interessiere ich mich für Ihre Produkte"
5. "Ich bin Doktorand an der Universität Freiburg und untersuche thermische Energiespeicherung"
6. "We are a research team from the University of Cambridge"
7. "I am a graduate student at MIT working on a thesis related to phase change materials"
8. "Our lab at Stanford University is exploring new applications for PCM"
9. "As a student at ETH Zurich, I am conducting experiments on thermal storage"
10. "I am pursuing my PhD at the University of Tokyo and studying advanced materials"

Formatvorgaben:
{format_instructions}
E-Mail:
{mail}
"""
    )

    _initialized = True


def process(data: dict, email_obj: Message) -> dict:

    if "klassifikation" in data:  # idempotent
        return data

    _init()
    plain, html = extract_bodies(email_obj)
    body = plain or html or ""
    if not body and not (email_obj.get("Subject")):
        data.setdefault("klassifikation", {})
        return data

    mail_json = {
        "from": email_obj.get("From"),
        "to": email_obj.get("To"),
        "subject": email_obj.get("Subject"),
        "date": email_obj.get("Date"),
        "body": body,
    }

    try:
        prompt = _prompt_template.format(
            format_instructions=_format_instructions,
            mail=mail_json,
        )
        response = _llm_model.invoke(prompt)  # type: ignore
        parsed = _output_parser.parse(response.content)  # type: ignore
    except Exception as e:  # noqa: BLE001
        data.setdefault("klassifikation", {"error": str(e)})
        return data
    normed, warns = _normalize(parsed)
    data["klassifikation_raw"] = parsed
    data["klassifikation"] = {
        "status_angebot": normed["StatusAngebot"],
        "universitaet": normed["Universität"],
        "phasecube": normed["PhaseCube"],
        "phasetube": normed["PhaseTube"],
        "phasedrum": normed["PhaseDrum"],
    }
    # Derived convenience lists
    data["kategorien_aktiv"] = [
        k for k, cond in [
            ("angebot", data["klassifikation"]["status_angebot"] == 1),
            ("universitaet", data["klassifikation"]["universitaet"] == 1),
            ("phasecube", data["klassifikation"]["phasecube"] == 1),
            ("phasetube", data["klassifikation"]["phasetube"] == 1),
            ("phasedrum", data["klassifikation"]["phasedrum"] == 1),
        ] if cond
    ]
    data["unsicher_flags"] = [
        k for k, cond in [
            ("angebot", data["klassifikation"]["status_angebot"] == 2),
            ("universitaet", data["klassifikation"]["universitaet"] == 2),
        ] if cond
    ]
    if warns:
        global _parse_warnings_count  # noqa: PLW0603
        _parse_warnings_count += 1
        data["klassifikation_warnings"] = warns
        data["klassifikation_warning_total"] = _parse_warnings_count
    return data
