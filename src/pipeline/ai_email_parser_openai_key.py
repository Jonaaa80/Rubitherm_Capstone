import os
from dotenv import load_dotenv

# Load variables from .env file
load_dotenv()
import json
from pathlib import Path
from email.message import Message
from openai import OpenAI

openai_api_key = os.getenv("OPENAI_API_KEY")
if not openai_api_key:
    raise EnvironmentError("OPENAI_API_KEY is not set. Please add it to your environment or .env file.")

OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5")

client = OpenAI(api_key=openai_api_key)


def _read_prompt_file() -> tuple[str, dict]:
    diag = {}
    # primary path: src/pipeline -> parent is src; utils is sibling
    primary = Path(__file__).resolve().parent.parent / "utils" / "email_parser_prompt.txt"
    candidates = [primary,
                  Path(__file__).resolve().parents[2] / "src" / "utils" / "email_parser_prompt.txt",
                  Path("src/utils/email_parser_prompt.txt").resolve()]
    for p in candidates:
        diag.setdefault("checked_paths", []).append(str(p))
        if p.exists():
            diag["prompt_path"] = str(p)
            diag["prompt_exists"] = True
            text = p.read_text(encoding="utf-8")
            diag["prompt_len"] = len(text)
            return text, diag
    diag["prompt_exists"] = False
    return "", diag


def _robust_json_parse(output: str) -> dict:
    # direct
    try:
        return json.loads(output)
    except Exception:
        pass
    # fenced code block ```json ... ```
    if "```" in output:
        import re
        m = re.search(r"```json\s*(\{[\s\S]*?\})\s*```", output, re.IGNORECASE)
        if m:
            return json.loads(m.group(1))
    # last braces
    start = output.rfind('{')
    end = output.rfind('}')
    if start != -1 and end != -1 and end > start:
        return json.loads(output[start:end+1])
    raise json.JSONDecodeError("No JSON object could be decoded", output, 0)


def process(data: dict, email_obj: Message) -> dict:
    """
    Processes the parsed email data with an LLM (via OpenAI) to extract signature information.
    Adds diagnostics under data["llm_debug"].
    """
    debug = {"stage": "start"}

    # Load prompt
    base_prompt, pdiag = _read_prompt_file()
    debug.update({"prompt_path": pdiag.get("prompt_path"),
                  "prompt_exists": pdiag.get("prompt_exists"),
                  "prompt_len": pdiag.get("prompt_len"),
                  "checked_paths": pdiag.get("checked_paths", [])})

    # Extract body text (prefer nested parsed.body_window; fallback to top-level; then to raw body)
    parsed = data.get("parsed") or {}
    body_window = (parsed.get("body_window") if isinstance(parsed, dict) else None) or data.get("body_window") or {}
    body_text = (body_window.get("text") or "").strip()
    if not body_text:
        # final fallback: use raw body if available
        body_text = (data.get("body") or "").strip()
    debug.update({
        "body_window_used": bool(body_window),
        "body_start_line": body_window.get("start_line") if isinstance(body_window, dict) else None,
        "body_end_line": body_window.get("end_line") if isinstance(body_window, dict) else None,
        "body_len": len(body_text)
    })

    if not base_prompt:
        data["signature_error"] = {"reason": "prompt_missing", "diag": debug}
        data["signature"] = {}
        data["llm_debug"] = debug
        return data

    if not body_text:
        data["signature_error"] = {"reason": "empty_body_window", "diag": debug}
        data["signature"] = {}
        data["llm_debug"] = debug
        return data

    # Build full prompt and include explicit FROM_ADDRESS when available
    from_address = None
    try:
        from_header = email_obj.get('From')
        if from_header:
            from_address = from_header
    except Exception:
        from_address = None
    if from_address:
        full_prompt = f"{base_prompt}\n\nFROM_ADDRESS: {from_address}\n\nEmail text:\n{body_text}"
    else:
        full_prompt = f"{base_prompt}\n\nEmail text:\n{body_text}"
    debug["from_address"] = from_address
    debug["final_prompt_len"] = len(full_prompt)

    try:
        response = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[
                {"role": "system", "content": "Extract the signature fields from the following email as JSON."},
                {"role": "user", "content": full_prompt},
            ],
            temperature=1,
        )
        out = response.choices[0].message.content
        debug.update({"model": OPENAI_MODEL})
    except Exception as e:
        debug.update({"exception": str(e)})
        data["signature_error"] = {"reason": "openai_exception", "diag": debug}
        data["signature"] = {}
        data["llm_debug"] = debug
        return data

    # Parse JSON
    try:
        signature = _robust_json_parse(out.strip())
        # Normalize signature fields
        if isinstance(signature, dict):
            signature.pop("for_recipient", None)
            # Ensure list fields exist
            for k in ("phone", "email", "url", "address"):
                if k not in signature or signature[k] is None:
                    signature[k] = []
            # Fallback: add emails found in header/body text (e.g., Von/From line included in body_window)
            if not signature.get("email"):
                import re
                email_re = re.compile(r"\b[a-z0-9._%+\-]+@[a-z0-9.\-]+\.[a-z]{2,}\b", re.IGNORECASE)
                found = email_re.findall(body_text)
                if found:
                    # dedupe while preserving order
                    seen = set()
                    dedup = []
                    for e in found:
                        if e.lower() not in seen:
                            dedup.append(e)
                            seen.add(e.lower())
                    signature["email"].extend(dedup)
        data["signature"] = signature
    except Exception as e:
        debug.update({"json_error": str(e), "raw_output_tail": out[-500:]})
        data["signature_error"] = {"reason": "json_parse_error", "diag": debug}
        data["signature"] = {}

    data["llm_debug"] = debug
    return data
