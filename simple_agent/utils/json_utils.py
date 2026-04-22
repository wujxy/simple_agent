from __future__ import annotations

import json


def safe_json_parse(text: str) -> dict | list | None:
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return None


def extract_json_from_text(text: str) -> dict | list | None:
    if not text:
        return None

    text = text.strip()

    # Strip markdown code fences
    if text.startswith("```json"):
        text = text[7:]
    elif text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    text = text.strip()

    # Bail early if text looks like source code, not JSON
    code_indicators = ("def ", "class ", "import ", "from ", "if __name__", "print(")
    if any(text.startswith(ind) for ind in code_indicators) and '"type"' not in text and "'type'" not in text:
        return None

    # Remove common prose prefixes
    for prefix in ("JSON:", "Response:", "Answer:", "Here's the JSON:", "The JSON is:"):
        if text.startswith(prefix):
            text = text[len(prefix):].strip()

    # Direct parse
    result = safe_json_parse(text)
    if result is not None:
        return result

    # Extract between outermost braces
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        result = safe_json_parse(text[start : end + 1])
        if result is not None:
            return result

    # Extract between outermost brackets
    start = text.find("[")
    end = text.rfind("]")
    if start != -1 and end != -1 and end > start:
        result = safe_json_parse(text[start : end + 1])
        if result is not None:
            return result

    return None
