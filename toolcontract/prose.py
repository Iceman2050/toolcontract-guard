"""Extract machine-checkable constraints stated in prose descriptions.

The recognised phrasing families are the EvalScope ``tool_contract``
module's (Spec B): numeric ranges ("between 1 and 100", "at least",
"at most", "greater than"), length bounds ("at least / at most / up
to / maximum of N characters", "between N and M characters"),
enumerations ("one of: ..."), patterns ("must match pattern ...",
"pattern: ..."), named formats (email, UUID), and required claims
("is required", "must be provided", "required field").

Coverage is deliberately bounded to these families: novel phrasings
can be missed — e.g. "max 50 characters" and a bare "Required." are
outside them — and the reports say so. Each extractor returns
(keyword, value, quote) tuples; the quote is the full description the
constraint was recovered from.
"""

import re

# Phrasing families — the EvalScope tool_contract module's, verbatim.
BETWEEN = re.compile(
    r"between\s+(-?\d+(?:\.\d+)?)\s+and\s+(-?\d+(?:\.\d+)?)", re.I)
BETWEEN_LEN = re.compile(
    r"between\s+(\d+)\s+and\s+(\d+)\s*(?:characters|chars)\b", re.I)
LEN_MAX = re.compile(
    r"(?:at most|no more than|up to|maximum of)\s+(\d+)\s*"
    r"(?:characters|chars)\b", re.I)
LEN_MIN = re.compile(
    r"(?:at least|minimum of)\s+(\d+)\s*(?:characters|chars)\b", re.I)
AT_LEAST = re.compile(
    r"(?:at least|no fewer than|minimum of)\s+(-?\d+(?:\.\d+)?)", re.I)
AT_MOST = re.compile(
    r"(?:at most|no more than|maximum of)\s+(-?\d+(?:\.\d+)?)", re.I)
GREATER = re.compile(r"(?:greater than|more than)\s+(-?\d+(?:\.\d+)?)",
                     re.I)
ENUM = re.compile(r"one of:?\s+([^.;]+)", re.I)
PATTERN = re.compile(
    r"(?:must match|matching|matches)\s+(?:the\s+)?pattern\s+(\S+)", re.I)
PATTERN2 = re.compile(r"pattern:\s*(\S+)", re.I)
EMAIL = re.compile(r"valid\s+e-?mail|e-?mail\s+address\s+format", re.I)
UUID = re.compile(r"\bUUID\b")
REQUIRED = re.compile(
    r"\b(?:is|are)\s+required\b|\bmust be provided\b|\brequired field\b",
    re.I)


def _num(text):
    value = float(text)
    return int(value) if value == int(value) else value


def enum_values_from_prose(text):
    """Split a "one of:" tail into candidate enum values (>= 2)."""
    text = text.strip().rstrip(".")
    parts = re.split(r",|\bor\b|\|", text)
    values = []
    for part in parts:
        value = part.strip().strip("'\"").strip()
        if value.lower().startswith("and "):
            value = value[4:].strip()
        if value:
            values.append(value)
    return values if len(values) >= 2 else None


def mentions_length(description):
    return bool(re.search(r"characters|chars\b", description, re.I))


def extract_constraints(description):
    """Return a list of (keyword, value, quote) found in the prose.

    Mirrors the module's branching: when the prose mentions character
    lengths, only the length families apply to bounds; otherwise only
    the numeric families do. At most one value per keyword.
    """
    if not description or not isinstance(description, str):
        return []
    found = []

    def add(keyword, value):
        if not any(k == keyword for k, _, _ in found):
            found.append((keyword, value, description))

    if mentions_length(description):
        match = BETWEEN_LEN.search(description)
        if match:
            add("minLength", int(match.group(1)))
            add("maxLength", int(match.group(2)))
        else:
            match = LEN_MIN.search(description)
            if match:
                add("minLength", int(match.group(1)))
            match = LEN_MAX.search(description)
            if match:
                add("maxLength", int(match.group(1)))
    else:
        match = BETWEEN.search(description)
        if match:
            add("minimum", _num(match.group(1)))
            add("maximum", _num(match.group(2)))
        else:
            match = AT_LEAST.search(description)
            if match:
                add("minimum", _num(match.group(1)))
            match = AT_MOST.search(description)
            if match:
                add("maximum", _num(match.group(1)))
            match = GREATER.search(description)
            if match:
                add("minimum", _num(match.group(1)))
    match = ENUM.search(description)
    if match:
        values = enum_values_from_prose(match.group(1))
        if values:
            add("enum", values)
    match = PATTERN.search(description) or PATTERN2.search(description)
    if match:
        add("pattern", match.group(1).rstrip("."))
    if EMAIL.search(description):
        add("format", "email")
    elif UUID.search(description):
        add("format", "uuid")
    return found


def prose_says_required(description):
    """True when the prose claims requiredness in a recognised
    phrasing ("is/are required", "must be provided", "required
    field"). A bare "Required." is outside the families."""
    return bool(description and isinstance(description, str)
                and REQUIRED.search(description))
