"""Minimal YAML-subset parser (standard library only).

Supported subset — enough for typical hand-written OpenAPI documents:
  - ``key: value`` mappings, nested by indentation (spaces)
  - lists of scalars: ``- item``
  - lists of mappings: ``- name: x`` followed by more-indented keys
  - scalars: plain strings, 'single'/"double" quoted strings, integers,
    floats, true/false, null/~
  - flow lists ``[a, b]`` and the empty flow map ``{}`` / list ``[]``
  - ``#`` comments on their own line or after a value (outside quotes)

Not supported: anchors, tags, multi-line strings, flow mappings other
than ``{}``, multiple documents. Specs may also be written in JSON, which
is parsed with the standard ``json`` module instead. This limitation is
stated honestly in the README: JSON is the fully supported format; YAML
input is accepted in this documented subset.
"""


class YamlError(ValueError):
    pass


def _strip_comment(line):
    in_s = in_d = False
    for i, ch in enumerate(line):
        if ch == "'" and not in_d:
            in_s = not in_s
        elif ch == '"' and not in_s:
            in_d = not in_d
        elif ch == "#" and not in_s and not in_d and (i == 0 or line[i - 1] in " \t"):
            return line[:i]
    return line


def _scalar(text):
    text = text.strip()
    if text == "[]":
        return []
    if text == "{}":
        return {}
    if text.startswith("[") and text.endswith("]"):
        inner = text[1:-1].strip()
        if not inner:
            return []
        return [_scalar(part) for part in inner.split(",")]
    if len(text) >= 2 and text[0] == text[-1] and text[0] in "\"'":
        return text[1:-1]
    low = text.lower()
    if low in ("true", "false"):
        return low == "true"
    if low in ("null", "~", ""):
        return None
    try:
        return int(text)
    except ValueError:
        pass
    try:
        return float(text)
    except ValueError:
        pass
    return text


def _lines(text):
    out = []
    for raw in text.splitlines():
        line = _strip_comment(raw).rstrip()
        if not line.strip():
            continue
        indent = len(line) - len(line.lstrip(" "))
        out.append((indent, line.strip()))
    return out


def parse(text):
    """Parse YAML-subset text into dict/list/scalars."""
    lines = _lines(text)
    if not lines:
        return {}
    obj, nxt = _block(lines, 0, lines[0][0])
    if nxt != len(lines):
        raise YamlError(f"could not parse line: {lines[nxt][1]!r}")
    return obj


def _block(lines, i, indent):
    if lines[i][1].startswith("- ") or lines[i][1] == "-":
        return _list(lines, i, indent)
    return _map(lines, i, indent)


def _map(lines, i, indent):
    out = {}
    while i < len(lines):
        ind, content = lines[i]
        if ind < indent or content.startswith("- "):
            break
        if ind > indent:
            raise YamlError(f"unexpected indentation: {content!r}")
        if ":" not in content:
            raise YamlError(f"expected 'key: value': {content!r}")
        key, _, rest = content.partition(":")
        key = key.strip().strip("\"'")
        rest = rest.strip()
        i += 1
        if rest:
            out[key] = _scalar(rest)
        elif i < len(lines) and lines[i][0] > indent:
            out[key], i = _block(lines, i, lines[i][0])
        else:
            out[key] = None
    return out, i


def _list(lines, i, indent):
    out = []
    while i < len(lines):
        ind, content = lines[i]
        if ind != indent or not (content.startswith("- ") or content == "-"):
            break
        item_text = content[1:].strip()
        i += 1
        if not item_text:
            if i < len(lines) and lines[i][0] > indent:
                val, i = _block(lines, i, lines[i][0])
                out.append(val)
            else:
                out.append(None)
        elif ":" in item_text and not item_text.startswith(("[", "{", '"', "'")):
            # Inline first pair of a mapping; following more-indented
            # lines belong to the same mapping.
            key, _, rest = item_text.partition(":")
            entry = {}
            rest = rest.strip()
            if rest:
                entry[key.strip().strip("\"'")] = _scalar(rest)
            elif i < len(lines) and lines[i][0] > indent + 2:
                val, i = _block(lines, i, lines[i][0])
                entry[key.strip().strip("\"'")] = val
            else:
                entry[key.strip().strip("\"'")] = None
            if i < len(lines) and lines[i][0] > indent:
                more, i = _map(lines, i, lines[i][0])
                entry.update(more)
            out.append(entry)
        else:
            out.append(_scalar(item_text))
    return out, i
