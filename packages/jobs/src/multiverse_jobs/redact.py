"""Logs stay free of secrets: anything that looks like one is cut before it is stored."""

import re

PATTERNS = (
    re.compile(r"(?i)\bbearer\s+[a-z0-9._~+/-]+=*"),
    re.compile(r"(?i)\b(api[_-]?key|token|secret|password|authorization)\b\s*[=:]\s*\S+"),
    re.compile(r"\b[0-9a-f]{32,}\b"),
    re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b"),
)
LIMIT = 400


def redact(message: str) -> str:
    """Hashes go too: a log line never needs one, and a key can look like one."""
    for pattern in PATTERNS:
        message = pattern.sub("[redacted]", message)
    return message[:LIMIT]
