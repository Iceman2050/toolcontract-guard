"""Constraint-gap linting for an authored OpenAPI / JSON Schema spec.

Every finding carries: a stable code, a severity, a location, the prose
quote when a prose-implied constraint was detected, the missing keyword,
and the concrete schema fix. Findings state what was checked; the tool
never claims certification.
"""

import json

from toolcontract.loader import resolve_ref
from toolcontract.prose import extract_constraints, prose_says_required

SEVERITY_ORDER = {"low": 0, "medium": 1, "high": 2}
CONSTRAINT_KEYWORDS = ("minimum", "maximum", "exclusiveMinimum",
                       "exclusiveMaximum", "minLength", "maxLength",
                       "pattern", "format", "enum", "minItems", "maxItems",
                       "multipleOf", "const")
HTTP_METHODS = ("get", "put", "post", "delete", "patch", "options", "head", "trace")


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


def _snippet(keyword, value):
    return f'"{keyword}": {json.dumps(value)}'


def _type_name(value):
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return "null"


def _schema_gap_checks(findings, spec, schema, location, subject, check_unconstrained):
    """Prose-gap + unconstrained checks for one parameter/property schema."""
    if not isinstance(schema, dict):
        return
    desc = schema.get("description", "")
    for keyword, value, quote in extract_constraints(desc):
        if keyword not in schema:
            findings.append(Finding(
                "TCG001", "high", location, subject,
                f"description states a {keyword} constraint in prose but the "
                f"schema declares no '{keyword}' keyword — an AI agent (or any "
                f"machine reader) cannot see this constraint",
                fix=f"add {_snippet(keyword, value)} to the schema of '{subject}'",
                prose=quote, missing_keyword=keyword))
    if check_unconstrained:
        stype = schema.get("type")
        if stype in ("string", "integer", "number") and not any(
                k in schema for k in CONSTRAINT_KEYWORDS):
            findings.append(Finding(
                "TCG002", "low", location, subject,
                f"{stype} parameter/property declares no machine-checkable "
                f"constraint at all (no minimum/maximum/minLength/maxLength/"
                f"pattern/enum/format)",
                fix=f"declare the intended constraint on '{subject}', e.g. "
                    f"{_snippet('maxLength', 255)} or {_snippet('minimum', 0)} "
                    f"as appropriate"))


def _schema_consistency_checks(findings, spec, schema, location):
    """required/enum consistency for every schema object in the document."""
    if not isinstance(schema, dict):
        return
    props = schema.get("properties")
    required = schema.get("required")
    if isinstance(required, list) and isinstance(props, dict):
        for name in required:
            if name not in props:
                findings.append(Finding(
                    "TCG003", "high", location, str(name),
                    f"'required' names '{name}' but no property '{name}' is "
                    f"declared in 'properties' — the requirement can never be "
                    f"satisfied as written",
                    fix=f"declare a '{name}' property, or remove \"{name}\" "
                        f"from 'required'"))
    enum = schema.get("enum")
    if isinstance(enum, list):
        if not enum:
            findings.append(Finding(
                "TCG011", "medium", location, "enum",
                "enum is empty — no value can ever validate",
                fix="declare at least one allowed value in 'enum'"))
        seen, dupes = set(), set()
        for v in enum:
            key = json.dumps(v, sort_keys=True)
            if key in seen:
                dupes.add(key)
            seen.add(key)
        for d in sorted(dupes):
            findings.append(Finding(
                "TCG004", "medium", location, "enum",
                f"enum contains the duplicate value {d}",
                fix=f"remove the duplicate {d} from 'enum'"))
        declared = schema.get("type")
        if declared in ("string", "integer", "number", "boolean"):
            for v in enum:
                if _type_name(v) != declared and not (
                        declared == "number" and _type_name(v) == "integer"):
                    findings.append(Finding(
                        "TCG005", "high", location, "enum",
                        f"enum value {json.dumps(v)} is type "
                        f"'{_type_name(v)}' but the schema type is '{declared}'",
                        fix=f"change {json.dumps(v)} to a {declared} value in "
                            f"'enum', or correct the schema 'type'"))


def _walk_schemas(findings, spec, node, location):
    """Recursively apply consistency checks to every schema-shaped node
    anywhere in the document (components, parameters, request bodies,
    responses). A node counts as schema-shaped when it carries
    'properties', 'enum', or a list-valued 'required'."""
    if isinstance(node, dict):
        if "properties" in node or "enum" in node \
                or isinstance(node.get("required"), list):
            _schema_consistency_checks(findings, spec, node, location)
        for key, value in node.items():
            _walk_schemas(findings, spec, value, f"{location}/{key}")
    elif isinstance(node, list):
        for idx, item in enumerate(node):
            _walk_schemas(findings, spec, item, f"{location}[{idx}]")


def operations(spec):
    """Yield (path, method, operation_dict)."""
    for path, item in (spec.get("paths") or {}).items():
        if not isinstance(item, dict):
            continue
        for method in HTTP_METHODS:
            op = item.get(method)
            if isinstance(op, dict):
                yield path, method, op


def lint_spec(spec):
    """Run every lint check class against a parsed spec. Returns findings."""
    findings = []

    # Consistency checks across components + all inline schemas.
    _walk_schemas(findings, spec, spec.get("components") or {},
                  "#/components")
    _walk_schemas(findings, spec, spec.get("paths") or {}, "#/paths")

    for path, method, op in operations(spec):
        op_loc = f"{method.upper()} {path}"

        # -- parameters -------------------------------------------------
        params = []
        path_item = (spec.get("paths") or {}).get(path) or {}
        for raw in (path_item.get("parameters") or []) + (op.get("parameters") or []):
            param = resolve_ref(spec, raw)
            if isinstance(param, dict) and param.get("name"):
                params.append(param)
        for param in params:
            name = param.get("name")
            schema = resolve_ref(spec, param.get("schema") or {})
            loc = f"{op_loc} parameter '{name}'"
            merged = dict(schema)
            if "description" not in merged and param.get("description"):
                merged["description"] = param["description"]
            _schema_gap_checks(findings, spec, merged, loc, name,
                               check_unconstrained=True)
            if prose_says_required(merged.get("description", "")) \
                    and not param.get("required"):
                findings.append(Finding(
                    "TCG006", "medium", loc, name,
                    f"description says '{name}' is required but the parameter "
                    f"is declared optional (required is not true)",
                    fix=f"set \"required\": true on parameter '{name}', or "
                        f"remove the word 'required' from its description",
                    prose=merged.get("description")))

        # -- request body properties ------------------------------------
        body = resolve_ref(spec, (op.get("requestBody") or {}))
        for media in ((body.get("content") or {}).values()):
            raw_schema = media.get("schema") if isinstance(media, dict) else None
            if raw_schema is None:
                continue
            schema = resolve_ref(spec, raw_schema)
            required_list = schema.get("required") or []
            for pname, pschema in (schema.get("properties") or {}).items():
                ps = resolve_ref(spec, pschema)
                loc = f"{op_loc} request body property '{pname}'"
                _schema_gap_checks(findings, spec, ps, loc, pname,
                                   check_unconstrained=True)
                if prose_says_required(ps.get("description", "")) \
                        and pname not in required_list:
                    findings.append(Finding(
                        "TCG006", "medium", loc, pname,
                        f"description says '{pname}' is required but it is "
                        f"not in the request body's 'required' list",
                        fix=f"add \"{pname}\" to the request body's "
                            f"'required' list, or remove 'required' from "
                            f"its description",
                        prose=ps.get("description")))

        # -- response completeness ---------------------------------------
        responses = op.get("responses") or {}
        if not responses:
            findings.append(Finding(
                "TCG007", "high", op_loc, op_loc,
                "operation documents no responses at all",
                fix=f"document at least the success response and one error "
                    f"response for {op_loc}"))
        else:
            success = [c for c in responses
                       if str(c).startswith("2") or str(c) == "default"]
            strict_success = [c for c in responses if str(c).startswith("2")]
            if not strict_success:
                findings.append(Finding(
                    "TCG007", "high", op_loc, op_loc,
                    "operation documents no success (2xx) response",
                    fix=f"add a documented 2xx response with a response "
                        f"schema to {op_loc}"))
            for code in strict_success:
                resp = resolve_ref(spec, responses[code])
                if str(code) == "204":
                    continue
                content = resp.get("content") or {}
                has_schema = any(
                    isinstance(m, dict) and m.get("schema")
                    for m in content.values())
                if not has_schema:
                    findings.append(Finding(
                        "TCG008", "medium", op_loc, f"response {code}",
                        f"success response {code} documents no response "
                        f"schema — callers cannot verify what they received",
                        fix=f"add a 'schema' under the {code} response "
                            f"content of {op_loc}"))
                if not resp.get("description"):
                    findings.append(Finding(
                        "TCG010", "low", op_loc, f"response {code}",
                        f"response {code} has no description",
                        fix=f"add a 'description' to the {code} response "
                            f"of {op_loc}"))
            has_error = any(str(c).startswith(("4", "5")) or str(c) == "default"
                            for c in responses)
            if not has_error:
                findings.append(Finding(
                    "TCG009", "medium", op_loc, op_loc,
                    "operation documents no error (4xx/5xx) response — "
                    "rejections are undocumented, so a client cannot tell a "
                    "validation failure from success-shaped output",
                    fix=f"document at least one error response (e.g. 400) "
                        f"with an error schema for {op_loc}"))
    findings.sort(key=lambda f: (-SEVERITY_ORDER[f.severity], f.location, f.code))
    return findings


def at_or_above(findings, threshold):
    floor = SEVERITY_ORDER[threshold]
    return [f for f in findings if SEVERITY_ORDER[f.severity] >= floor]
