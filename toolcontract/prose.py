"""Extract machine-checkable constraints stated in prose descriptions.

Each extractor returns (keyword, value, quote) tuples — the keyword is the
JSON-Schema keyword that would make the prose constraint checkable, the
value is the suggested value recovered from the prose, and the quote is
the exact prose fragment the constraint was recovered from.
"""

import re

_NUM = r"(-?\d+(?:\.\d+)?)"


def _num(text):
    try:
        return int(text)
    except ValueError:
        return float(text)


def _sentence_around(desc, start, end):
    lo = desc.rfind(".", 0, start)
    lo = 0 if lo < 0 else lo + 1
    hi = desc.find(".", end)
    hi = len(desc) if hi < 0 else hi + 1
    return desc[lo:hi].strip()


def extract_constraints(description):
    """Return a list of (keyword, value, quote) found in the prose."""
    if not description or not isinstance(description, str):
        return []
    desc = description
    found = []

    def add(keyword, value, m):
        quote = _sentence_around(desc, m.start(), m.end())
        if not any(k == keyword for k, _, _ in found):
            found.append((keyword, value, quote))

    # "between 1 and 100"
    m = re.search(rf"\bbetween\s+{_NUM}\s+and\s+{_NUM}", desc, re.I)
    if m:
        add("minimum", _num(m.group(1)), m)
        add("maximum", _num(m.group(2)), m)

    # Length constraints: any numeric bound whose context mentions characters.
    for m in re.finditer(
        rf"(?:max(?:imum)?\.?|at most|no more than|up to)\s+{_NUM}\s*(?:characters|chars)\b",
        desc, re.I):
        add("maxLength", int(float(m.group(1))), m)
    for m in re.finditer(
        rf"(?:min(?:imum)?\.?|at least)\s+{_NUM}\s*(?:characters|chars)\b",
        desc, re.I):
        add("minLength", int(float(m.group(1))), m)
    m = re.search(rf"\b{_NUM}\s*(?:characters|chars)\s+max", desc, re.I)
    if m:
        add("maxLength", int(float(m.group(1))), m)

    # Numeric bounds (skip ones already claimed by a character context).
    def _is_char_ctx(m):
        return bool(re.search(r"(characters|chars)\b", desc[m.start():m.end() + 12], re.I))

    for pat, kw in (
        (rf"(?:at most|no more than|maximum(?:\s+of)?|max\.?|<=)\s*{_NUM}\b", "maximum"),
        (rf"(?:at least|minimum(?:\s+of)?|min\.?|>=)\s*{_NUM}\b", "minimum"),
    ):
        for m in re.finditer(pat, desc, re.I):
            if _is_char_ctx(m):
                continue
            add(kw, _num(m.group(1)), m)

    # "one of: a, b, c" / "one of a | b | c"
    m = re.search(r"\bone of[:\s]+(.+)", desc, re.I)
    if m:
        raw = m.group(1).strip().rstrip(".")
        parts = re.split(r"\s*\|\s*|\s*,\s*|\s+or\s+|\s+and\s+", raw)
        values = [p.strip().strip("\"'`") for p in parts if p.strip()]
        if 1 < len(values) <= 20:
            add("enum", values, m)

    # "must match pattern X" / "pattern: X"
    m = re.search(r"(?:must match(?:\s+the)?\s+pattern|pattern[:\s]+)\s*`?(\S+?)`?(?:\s|\.|$)", desc, re.I)
    if m:
        add("pattern", m.group(1), m)

    # "valid email" -> format: email
    m = re.search(r"\bvalid email\b|\bemail address\b", desc, re.I)
    if m:
        add("format", "email", m)

    return found


def prose_says_required(description):
    return bool(description and isinstance(description, str)
                and re.search(r"\brequired\b", description, re.I))
