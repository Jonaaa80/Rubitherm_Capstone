import os
import json
from pathlib import Path
from email.message import Message
import subprocess

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


def _call_ollama(prompt: str, model: str, timeout: int = 120) -> tuple[int, str, str]:
    proc = subprocess.run(
        ["ollama", "run", model],
        input=prompt,
        capture_output=True,
        text=True,
        timeout=timeout
    )
    return proc.returncode, proc.stdout, proc.stderr


def process(data: dict, email_obj: Message) -> dict:
    """
    Processes the parsed email data with an LLM (via Ollama) to extract signature information.
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

    # Build full prompt (do NOT force a recipient; only include if you explicitly want to guide the model)
    recipient = None  # optionally set from headers if desired
    full_prompt = f"{base_prompt}\n\nEmail text:\n{body_text}"
    if recipient:
        full_prompt += f"\n\nfor_recipient: {recipient}"
    debug["final_prompt_len"] = len(full_prompt)

    # Choose model (env override) and call Ollama
    model = os.getenv("OLLAMA_MODEL", "gpt-oss:20b")
    rc, out, err = -1, "", ""
    try:
        rc, out, err = _call_ollama(full_prompt, model)
        debug.update({"model": model, "returncode": rc, "stderr": err[:500], "stdout_head": out[:500]})
        if rc != 0 or not out.strip():
            # fallback to llama3
            rc2, out2, err2 = _call_ollama(full_prompt, "llama3")
            debug.update({"fallback_model": "llama3", "fallback_returncode": rc2, "fallback_stderr": err2[:500], "fallback_stdout_head": out2[:500]})
            if rc2 == 0 and out2.strip():
                out, err, rc = out2, err2, rc2
    except Exception as e:
        debug.update({"exception": str(e)})
        data["signature_error"] = {"reason": "ollama_exception", "diag": debug}
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
