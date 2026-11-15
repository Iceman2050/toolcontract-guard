"""Secret scrubbing for quoted spec text.

Lint findings quote prose from the spec author's descriptions. A
description can accidentally carry a credential (``api_key = ...`` in
a legacy note), and a report must never echo it back. This module is
the same two-layer scrub the EvalScope core scanner applies: known
secret-format patterns, plus credential-assignment redaction (any
value assigned to a credential-named field is redacted whatever its
shape), with a fixed ``[REDACTED]`` marker that leaks neither length
nor prefix.
"""
import re

_REDACTED = "[REDACTED]"


def redact_value(_value):
    """A secret-like value is NEVER echoed back: fixed marker only."""
    return _REDACTED


# Known secret-format patterns (the core scanner's redact-flagged
# rules, pattern bodies unchanged).
_SECRET_PATTERNS = (
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),  # AWS access key id
    re.compile(r"(?i)\baws[_\- ]?secret(?:[_\- ]?access[_\- ]?key)?\b"
               r"\s*[:=]\s*['\"]?[A-Za-z0-9/+=]{32,}['\"]?"),
    re.compile(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}\b"),  # GitHub token
    re.compile(r"\bsk-[A-Za-z0-9]{20,}\b"),  # generic API key
    re.compile(r"(?i)\b(api[_-]?key|client[_-]?secret|auth[_-]?token|"
               r"access[_-]?token|passwd|password|db[_-]?password)\b"
               r"\s*[:=]\s*['\"][^'\"\s]{8,}['\"]"),
    re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"
               r"\.[A-Za-z0-9_-]{10,}\b"),  # JWT
)

# Credential-assignment scrubbing: field names are matched by
# component (split on _ / -), so benign names that merely contain a
# credential substring (keyboard=, monkey=) are left alone, and
# non-credential assignments (port=, host=) display normally.
_CRED_NAME_PARTS = frozenset({
    "key", "apikey", "secret", "token", "password", "passwd", "pwd",
    "credential", "credentials", "privatekey",
})
_CRED_NAME_EXACT = frozenset({
    "key", "apikey", "api_key", "secret", "token", "password", "passwd",
    "pwd", "credential", "credentials", "auth", "private_key",
})
_NON_SECRET_LITERALS = frozenset({
    "", "none", "null", "true", "false", "[redacted]", "redacted",
})
_ASSIGN_RE = re.compile(
    r"""(?P<prefix>["']?(?P<name>[A-Za-z][A-Za-z0-9_-]*)["']?\s*[:=]\s*)"""
    r"""(?:(?P<q>["'])(?P<qval>[^"']*)(?P=q)|(?P<bval>[^\s"',;\]\)\}]+))""")


def _is_credential_name(name):
    low = name.lower()
    if low in _CRED_NAME_EXACT:
        return True
    parts = re.split(r"[_-]+", low)
    return any(part in _CRED_NAME_PARTS for part in parts)


def _sub_assignment(match):
    if not _is_credential_name(match.group("name")):
        return match.group(0)
    quote = match.group("q")
    value = match.group("qval") if quote else match.group("bval")
    low = (value or "").strip().lower()
    if value is None or low in _NON_SECRET_LITERALS or \
            low.startswith("[redacted"):
        return match.group(0)
    if quote:
        return "%s%s[REDACTED]%s" % (match.group("prefix"), quote, quote)
    return "%s[REDACTED]" % match.group("prefix")


def _scrub_assignments(text):
    return _ASSIGN_RE.sub(_sub_assignment, text)


def scrub_text(text):
    """Replace every secret-like pattern in `text` with [REDACTED]."""
    text = _scrub_assignments(text)
    for pattern in _SECRET_PATTERNS:
        text = pattern.sub(redact_value(""), text)
    return _scrub_assignments(text)
