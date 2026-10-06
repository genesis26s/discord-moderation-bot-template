"""Centralized redaction. Every log/exception/user-facing string passes through here."""
from __future__ import annotations

import re
from typing import Any

# Anything matching these patterns is replaced before it can reach any sink.
_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    # IPv4
    (re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"), "[REDACTED_IP]"),
    # IPv6 (loose but safe: bracketed, or 4+ hex groups separated by colons)
    (re.compile(r"\[[0-9a-fA-F:]+\]"), "[REDACTED_IP]"),
    (re.compile(r"\b(?:[0-9a-fA-F]{1,4}:){3,}[0-9a-fA-F]{1,4}\b"), "[REDACTED_IP]"),
    # Bearer / auth
    (re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._\-]+"), "Bearer [REDACTED_TOKEN]"),
    (re.compile(r"(?i)\bBasic\s+[A-Za-z0-9+/=]+"), "Basic [REDACTED_TOKEN]"),
    # API keys / secrets key=value
    (re.compile(r"(?i)\b(api[_-]?key|token|secret|password|passwd|pwd|session(?:_?cookie)?|cookie|authorization)\s*[:=]\s*[^\s,;\"']+"), "[REDACTED_SECRET]"),
    # Discord token-shaped strings
    (re.compile(r"\b[MN][A-Za-z\d]{23}\.[\w-]{6}\.[\w-]{27,}\b"), "[REDACTED_TOKEN]"),
    # Roblox cookie
    (re.compile(r"(?i)\.ROBLOSECURITY=[^;\s]+"), "[REDACTED_COOKIE]"),
    # Long opaque hex (potential token/secret)
    (re.compile(r"\b[a-f0-9]{40,}\b"), "[REDACTED_HEX]"),
    # Emails (optional: mark redacted to avoid correlation leaks in logs)
    (re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b"), "[REDACTED_EMAIL]"),
]


class RedactionManager:
    """Apply all redaction patterns. Safe to call on any string."""

    @staticmethod
    def redact(value: Any) -> str:
        if value is None:
            return ""
        text = value if isinstance(value, str) else str(value)
        for pattern, replacement in _PATTERNS:
            text = pattern.sub(replacement, text)
        return text

    @staticmethod
    def redact_exception(exc: BaseException) -> str:
        """Return a redacted one-line summary of an exception."""
        try:
            text = f"{type(exc).__name__}: {exc}"
        except Exception:
            text = type(exc).__name__
        return RedactionManager.redact(text)

    @staticmethod
    def safe_headers(headers: Any) -> dict[str, str]:
        """Return only non-sensitive header names; values redacted."""
        out: dict[str, str] = {}
        try:
            items = dict(headers).items()
        except Exception:
            return out
        for k, v in items:
            kl = str(k).lower()
            if kl in {"authorization", "cookie", "set-cookie", "x-api-key", "proxy-authorization"}:
                out[str(k)] = "[REDACTED]"
            else:
                out[str(k)] = RedactionManager.redact(v)
        return out


# Convenience wrappers used everywhere in the verification package.
def r(value: Any) -> str:
    return RedactionManager.redact(value)


def rex(exc: BaseException) -> str:
    return RedactionManager.redact_exception(exc)
