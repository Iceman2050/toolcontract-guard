"""Constraint-gap linting for an authored OpenAPI spec.

The lint engine is aligned verdict-for-verdict with the EvalScope
``tool_contract`` module (Spec B): the same sites are walked
(component schemas, operation parameters, request/response body
schemas — nested properties included), the same prose phrasing
families are recognised (see ``prose.py``), the same severities are
assigned, an unconstrained note is only raised where no prose finding
already fired, and the same response-completeness rules apply.
Findings carry the repo's stable TCG codes; the mapping from the
module's check classes is:

    prose_only_minimum/maximum/enum/length/pattern/format -> TCG001
    unconstrained_parameter -> TCG002     required_undeclared -> TCG003
    enum_duplicate_values   -> TCG004     enum_type_mismatch  -> TCG005
    prose_only_required     -> TCG006     no_success_response -> TCG007
    success_response_no_schema -> TCG008  no_error_response   -> TCG009
    enum_empty              -> TCG011

Every finding carries a code, a severity, a location (JSON pointer),
the subject parameter/property, a message, the prose quote when a
prose-implied constraint was detected (secret-scrubbed), the missing
keyword, and the concrete schema fix. Findings state what was
checked; the tool never claims certification.
"""

import json

from toolcontract.prose import (
    AT_LEAST, AT_MOST, BETWEEN, BETWEEN_LEN, EMAIL, ENUM, GREATER,
    LEN_MAX, LEN_MIN, PATTERN, PATTERN2, REQUIRED, UUID,
    enum_values_from_prose, mentions_length)
from toolcontract.scrub import scrub_text

SEVERITY_ORDER = {"low": 0, "medium": 1, "high": 2, "critical": 3}
CONSTRAINT_KEYWORDS = ("minimum", "maximum", "exclusiveMinimum",
                       "exclusiveMaximum", "minLength", "maxLength",
                       "pattern", "format", "enum", "minItems",
                       "maxItems", "uniqueItems", "multipleOf")
HTTP_METHODS = ("get", "put", "post", "delete", "patch", "options",
                "head", "trace")

# Module check class -> (TCG code, severity, title).
_CLASS_INFO = {
    "prose_only_minimum": ("TCG001", "high",
                           "Prose-only numeric lower bound"),
    "prose_only_maximum": ("TCG001", "high",
                           "Prose-only numeric upper bound"),
    "prose_only_minlength": ("TCG001", "medium",
                             "Prose-only minimum length"),
    "prose_only_maxlength": ("TCG001", "medium",
                             "Prose-only maximum length"),
    "prose_only_enum": ("TCG001", "high", "Prose-only enumeration"),
    "prose_only_pattern": ("TCG001", "medium", "Prose-only pattern"),
    "prose_only_format": ("TCG001", "medium", "Prose-only format"),
    "prose_only_required": ("TCG006", "medium",
                            "Prose-claimed required field"),
    "unconstrained_parameter": ("TCG002", "low",
                                "Unconstrained parameter or property"),
    "required_undeclared": ("TCG003", "high",
                            "Required entry names an undeclared "
                            "property"),
    "enum_duplicate_values": ("TCG004", "medium",
                              "Duplicate enum values"),
    "enum_type_mismatch": ("TCG005", "medium",
                           "Enum value type contradicts schema type"),
    "enum_empty": ("TCG011", "medium", "Empty enum"),
    "no_success_response": ("TCG007", "high",
                            "Operation has no success response"),
    "success_response_no_schema": ("TCG008", "medium",
                                   "Success response has no schema"),
    "no_error_response": ("TCG009", "low",
                          "Operation documents no error response"),
}


class Finding:
    def __init__(self, code, severity, location, subject, message, fix,
                 prose=None, missing_keyword=None):
        self.code = code
        self.severity = severity
        self.location = location
        self.subject = subject
        self.message = message
        self.fix = fix
        self.prose = prose
        self.missing_keyword = missing_keyword

    def to_dict(self):
        return {
            "code": self.code, "severity": self.severity,
            "location": self.location, "subject": self.subject,
            "message": self.message,
            "prose": self.prose, "missing_keyword": self.missing_keyword,
            "fix": self.fix,
        }

    def __repr__(self):
        return f"Finding({self.code}, {self.location}, {self.subject})"


# ------------------------------------------------------------ traversal
# The traversal helpers mirror the EvalScope module's loader: local
# $ref chains are followed without merging siblings, operations are
# visited in deterministic (path, method) order with path-item and
# operation parameters merged (operation wins), and schema trees are
# walked through properties/items with $ref nodes yielded but never
# descended into (their definition site is walked separately).

def _pointer_escape(part):
    return str(part).replace("~", "~0").replace("/", "~1")


def _resolve(doc, schema):
    """Follow local ``$ref`` chains; returns the target schema dict.
    Non-local or unresolvable refs return the schema unchanged."""
    seen = set()
    while isinstance(schema, dict) and "$ref" in schema:
        ref = schema["$ref"]
        if not isinstance(ref, str) or not ref.startswith("#/") \
                or ref in seen:
            return schema
        seen.add(ref)
        node = doc
        try:
            for part in ref[2:].split("/"):
                node = node[part.replace("~1", "/").replace("~0", "~")]
        except (KeyError, TypeError):
            return schema
        schema = node
    return schema


def _iter_operations(doc):
    records = []
    paths = doc.get("paths") or {}
    for path in sorted(paths):
        item = paths[path] or {}
        shared = item.get("parameters") or []
        for method in HTTP_METHODS:
            operation = item.get(method)
            if not isinstance(operation, dict):
                continue
            merged = {}
            for param in list(shared) + list(
                    operation.get("parameters") or []):
                if isinstance(param, dict):
                    merged[(param.get("name"), param.get("in"))] = param
            records.append({
                "method": method.upper(),
                "path": path,
                "pointer": "/paths/%s/%s" % (_pointer_escape(path),
                                             method),
                "operation": operation,
                "parameters": list(merged.values()),
            })
    records.sort(key=lambda r: (r["path"],
                                HTTP_METHODS.index(r["method"].lower())))
    return records


def _walk_schema(doc, schema, pointer, parent=None, name=None):
    """Yield (pointer, name, schema, parent) for a schema tree."""
    if not isinstance(schema, dict):
        return
    yield pointer, name, schema, parent
    if "$ref" in schema:
        return
    props = schema.get("properties")
    if isinstance(props, dict):
        for prop_name in sorted(props):
            yield from _walk_schema(
                doc, props[prop_name],
                "%s/properties/%s" % (pointer,
                                      _pointer_escape(prop_name)),
                schema, prop_name)
    items = schema.get("items")
    if isinstance(items, dict):
        yield from _walk_schema(doc, items, pointer + "/items", schema,
                                (name + "[]") if name else "[]")


def operations(spec):
    """Yield (path, method, operation_dict). Kept for inspect/tester."""
    for path, item in (spec.get("paths") or {}).items():
        if not isinstance(item, dict):
            continue
        for method in HTTP_METHODS:
            op = item.get(method)
            if isinstance(op, dict):
                yield path, method, op


# -------------------------------------------------------------- findings

def _num(text):
    value = float(text)
    return int(value) if value == int(value) else value


def _make_finding(klass, pointer, subject, prose, missing_keyword,
                  suggested_fix, remediation, detail=None):
    code, severity, title = _CLASS_INFO[klass]
    message = title if detail is None else "%s: %s" % (title, detail)
    return Finding(
        code, severity, pointer, subject,
        scrub_text(message), scrub_text(suggested_fix),
        prose=scrub_text(prose) if prose else None,
        missing_keyword=missing_keyword)


def _prose_findings(pointer, operation, name, schema, parent_required):
    """Prose-vs-schema gap findings for one parameter/property site.
    Mirrors the module's _prose_findings exactly, including its
    parameter requiredness convention (see lint_spec)."""
    findings = []
    description = schema.get("description") or ""
    if not isinstance(description, str) or not description.strip():
        return findings, False
    declared = set(schema)

    def add(klass, keyword, fix):
        findings.append(_make_finding(
            klass, pointer, name, description, keyword, fix,
            "Declare the constraint in the schema so machines enforce "
            "it: %s" % fix))

    if mentions_length(description):
        match = BETWEEN_LEN.search(description)
        if match:
            if "minLength" not in declared:
                add("prose_only_minlength", "minLength",
                    'add "minLength": %d' % int(match.group(1)))
            if "maxLength" not in declared:
                add("prose_only_maxlength", "maxLength",
                    'add "maxLength": %d' % int(match.group(2)))
        else:
            match = LEN_MIN.search(description)
            if match and "minLength" not in declared:
                add("prose_only_minlength", "minLength",
                    'add "minLength": %d' % int(match.group(1)))
            match = LEN_MAX.search(description)
            if match and "maxLength" not in declared:
                add("prose_only_maxlength", "maxLength",
                    'add "maxLength": %d' % int(match.group(1)))
    else:
        match = BETWEEN.search(description)
        if match:
            if "minimum" not in declared:
                add("prose_only_minimum", "minimum",
                    'add "minimum": %s'
                    % json.dumps(_num(match.group(1))))
            if "maximum" not in declared:
                add("prose_only_maximum", "maximum",
                    'add "maximum": %s'
                    % json.dumps(_num(match.group(2))))
        else:
            match = AT_LEAST.search(description)
            if match and "minimum" not in declared:
                add("prose_only_minimum", "minimum",
                    'add "minimum": %s'
                    % json.dumps(_num(match.group(1))))
            match = AT_MOST.search(description)
            if match and "maximum" not in declared:
                add("prose_only_maximum", "maximum",
                    'add "maximum": %s'
                    % json.dumps(_num(match.group(1))))
            match = GREATER.search(description)
            if match and "minimum" not in declared:
                add("prose_only_minimum", "minimum",
                    'add "minimum": %s with "exclusiveMinimum": true'
                    % json.dumps(_num(match.group(1))))
    match = ENUM.search(description)
    if match and "enum" not in declared:
        values = enum_values_from_prose(match.group(1))
        if values:
            add("prose_only_enum", "enum",
                'add "enum": %s' % json.dumps(values))
    match = PATTERN.search(description) or PATTERN2.search(description)
    if match and "pattern" not in declared:
        add("prose_only_pattern", "pattern",
            'add "pattern": %s' % json.dumps(match.group(1).rstrip(".")))
    if "format" not in declared:
        if EMAIL.search(description):
            add("prose_only_format", "format", 'add "format": "email"')
        elif UUID.search(description):
            add("prose_only_format", "format", 'add "format": "uuid"')
    if parent_required is not None and name is not None:
        if REQUIRED.search(description) and name not in parent_required:
            add("prose_only_required", "required",
                'mark "%s" required in the schema (the parent '
                '"required" list, or "required": true for a parameter)'
                % name)
    return findings, bool(findings)


def _enum_type_ok(declared_type, value):
    if declared_type == "string":
        return isinstance(value, str)
    if declared_type == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if declared_type == "number":
        return isinstance(value, (int, float)) \
            and not isinstance(value, bool)
    if declared_type == "boolean":
        return isinstance(value, bool)
    return True


def _consistency_findings(pointer, operation, name, schema):
    findings = []

    def add(klass, subject, detail, fix):
        findings.append(_make_finding(
            klass, pointer, subject, "", None, fix, fix,
            detail=detail))

    if isinstance(schema.get("properties"), dict):
        props = schema["properties"]
        for entry in schema.get("required") or []:
            if entry not in props:
                add("required_undeclared", entry,
                    "required names %r" % entry,
                    'remove "%s" from "required" or declare the '
                    'property "%s"' % (entry, entry))
    enum = schema.get("enum")
    if isinstance(enum, list):
        if not enum:
            add("enum_empty", name, "empty enum",
                "declare at least one enum value or remove the enum")
        seen, dupes = [], []
        for value in enum:
            if value in seen and value not in dupes:
                dupes.append(value)
            seen.append(value)
        if dupes:
            add("enum_duplicate_values", name,
                "duplicates %r" % (dupes,),
                "remove the duplicate enum values %s"
                % json.dumps(dupes))
        declared_type = schema.get("type")
        if declared_type:
            bad = [v for v in enum
                   if not _enum_type_ok(declared_type, v)]
            if bad:
                add("enum_type_mismatch", name,
                    "values %r vs type %s" % (bad, declared_type),
                    "make every enum value match the declared type "
                    "%s, or change the schema type to match the values"
                    % declared_type)
    return findings


def _lint_site(doc, pointer, operation_label, name, schema,
               parent_required):
    findings, has_prose = _prose_findings(
        pointer, operation_label, name, schema, parent_required)
    findings.extend(_consistency_findings(
        pointer, operation_label, name, schema))
    declared = set(schema)
    if not has_prose and schema.get("type") in ("integer", "number",
                                                "string") \
            and not any(key in declared for key in CONSTRAINT_KEYWORDS):
        findings.append(_make_finding(
            "unconstrained_parameter", pointer, name,
            schema.get("description") or "", None,
            "declare at least one machine-checkable constraint "
            "(a bound, a length, a pattern/format, or an enum)",
            "Declare at least one machine-checkable constraint so "
            "the contract states what the machine will enforce."))
    return findings


def _lint_schema_tree(doc, root, pointer, operation_label):
    findings = []
    for node_pointer, name, schema, parent in _walk_schema(
            doc, root, pointer):
        parent_required = None
        if isinstance(parent, dict) and isinstance(
                parent.get("properties"), dict) and name is not None:
            parent_required = parent.get("required") or []
        findings.extend(_lint_site(
            doc, node_pointer, operation_label, name, schema,
            parent_required))
    return findings


def _response_findings(record):
    operation = record["operation"]
    label = "%s %s" % (record["method"], record["path"])
    findings = []
    responses = operation.get("responses") or {}
    keys = [str(key) for key in responses]
    success = [key for key in keys
               if key.startswith("2") or key.upper() == "2XX"]
    if not success:
        findings.append(_make_finding(
            "no_success_response", record["pointer"], label, "", None,
            "document at least one 2xx response",
            "Document at least one 2xx response for this operation."))
        return findings
    has_schema = False
    for key in responses:
        if str(key) not in success:
            continue
        content = (responses[key] or {}).get("content") or {}
        for media in content.values():
            if isinstance(media, dict) and isinstance(
                    media.get("schema"), dict):
                has_schema = True
    if not has_schema:
        findings.append(_make_finding(
            "success_response_no_schema", record["pointer"], label,
            "", None,
            "give the success response a schema",
            "Give the success response a schema so observed bodies "
            "can be judged against the documented contract."))
    has_error = any(key.startswith(("4", "5")) or key == "default"
                    for key in keys)
    if not has_error:
        findings.append(_make_finding(
            "no_error_response", record["pointer"], label, "", None,
            "document an error response (e.g. 400) for this operation",
            "Document an error response so rejections are part of "
            "the contract clients can rely on."))
    return findings


def lint_spec(spec):
    """Lint one parsed OpenAPI document. Pure and deterministic;
    verdict-aligned with the EvalScope tool_contract module."""
    doc = spec
    findings = []
    components = (doc.get("components") or {}).get("schemas") or {}
    for comp_name in sorted(components):
        findings.extend(_lint_schema_tree(
            doc, components[comp_name],
            "/components/schemas/%s" % comp_name, None))
    for record in _iter_operations(doc):
        label = "%s %s" % (record["method"], record["path"])
        operation = record["operation"]
        for idx, param in enumerate(record["parameters"]):
            if "$ref" in param:
                param = _resolve(doc, param)
            schema = dict(param.get("schema") or {})
            if "description" not in schema and param.get("description"):
                schema["description"] = param["description"]
            pointer = "%s/parameters/%d" % (record["pointer"], idx)
            findings.extend(_lint_site(
                doc, pointer, label, param.get("name"), schema,
                [] if param.get("required") else None))
        body = (operation.get("requestBody") or {}).get("content") or {}
        for media in body.values():
            if isinstance(media, dict) and isinstance(
                    media.get("schema"), dict) \
                    and "$ref" not in media["schema"]:
                findings.extend(_lint_schema_tree(
                    doc, media["schema"],
                    record["pointer"] + "/requestBody", label))
        for status, response in (operation.get("responses")
                                 or {}).items():
            content = (response or {}).get("content") or {}
            for media in content.values():
                if isinstance(media, dict) and isinstance(
                        media.get("schema"), dict) \
                        and "$ref" not in media["schema"]:
                    findings.extend(_lint_schema_tree(
                        doc, media["schema"],
                        "%s/responses/%s" % (record["pointer"], status),
                        label))
        findings.extend(_response_findings(record))
    findings.sort(key=lambda f: (-SEVERITY_ORDER[f.severity],
                                 f.location, f.code,
                                 f.subject or ""))
    return findings


def severity_counts(findings):
    counts = {severity: 0 for severity in
              ("critical", "high", "medium", "low")}
    for finding in findings:
        counts[finding.severity] = counts.get(finding.severity, 0) + 1
    return counts


def at_or_above(findings, threshold):
    floor = SEVERITY_ORDER[threshold]
    return [f for f in findings if SEVERITY_ORDER[f.severity] >= floor]
