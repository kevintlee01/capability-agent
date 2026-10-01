"""Redact secrets and sensitive financial data before anything is persisted."""
import re

_PATTERNS = {
    "ssn": re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
    "card_number": re.compile(r"\b(?:\d[ -]?){13,19}\b"),
    "email": re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b"),
}

_SENSITIVE_FIELD_NAMES = {"password", "token", "api_key", "secret", "ssn", "card_number", "cvv"}


def redact_text(text: str) -> str:
    redacted = text
    for name, pattern in _PATTERNS.items():
        redacted = pattern.sub(f"[REDACTED_{name.upper()}]", redacted)
    return redacted


def redact_dict(data: dict) -> dict:
    """Recursively redact sensitive field names and scrub string values."""
    result = {}
    for key, value in data.items():
        if key.lower() in _SENSITIVE_FIELD_NAMES:
            result[key] = "[REDACTED]"
        elif isinstance(value, dict):
            result[key] = redact_dict(value)
        elif isinstance(value, str):
            result[key] = redact_text(value)
        else:
            result[key] = value
    return result
