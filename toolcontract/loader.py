"""Spec loading: JSON (full) or the documented YAML subset. Stdlib only."""

import json
from pathlib import Path

from toolcontract import yamlmini


def load_spec(path):
    text = Path(path).read_text(encoding="utf-8")
    suffix = Path(path).suffix.lower()
    if suffix == ".json" or text.lstrip().startswith("{"):
        data = json.loads(text)
    elif suffix in (".yaml", ".yml"):
        data = yamlmini.parse(text)
    else:
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            data = yamlmini.parse(text)
    if not isinstance(data, dict):
        raise ValueError("spec root must be an object/mapping")
    return data


def resolve_ref(spec, node, _seen=None):
    """Resolve a local $ref (#/...) one chain at a time; returns the node."""
    seen = _seen or set()
    while isinstance(node, dict) and "$ref" in node:
        ref = node["$ref"]
        if not isinstance(ref, str) or not ref.startswith("#/") or ref in seen:
            return node
        seen.add(ref)
        cur = spec
        for part in ref[2:].split("/"):
            part = part.replace("~1", "/").replace("~0", "~")
            if not isinstance(cur, dict) or part not in cur:
                return node
            cur = cur[part]
        merged = dict(cur) if isinstance(cur, dict) else cur
        siblings = {k: v for k, v in node.items() if k != "$ref"}
        if isinstance(merged, dict):
            merged.update(siblings)
        node = merged
    return node
