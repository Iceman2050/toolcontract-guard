"""Boundary test generation + execution against an authorized target.

Execution happens ONLY here, and ONLY against the --target the user
supplied for this invocation. There is no default target anywhere in
this codebase; the CLI refuses to run `test` without one (fail closed).
"""

import json
import re
import urllib.error
import urllib.parse
import urllib.request

from toolcontract.core import operations
from toolcontract.loader import resolve_ref


def sample_value(schema, spec=None):
    """A valid sample value for a schema, from its declared constraints."""
    schema = resolve_ref(spec, schema) if spec else schema
    if not isinstance(schema, dict):
        return "sample"
    if "example" in schema:
        return schema["example"]
    if "default" in schema:
        return schema["default"]
    if schema.get("enum"):
        return schema["enum"][0]
    stype = schema.get("type", "string")
    if stype == "integer":
        v = schema.get("minimum", 1)
        if schema.get("maximum") is not None:
            v = min(v, schema["maximum"])
        return int(v)
    if stype == "number":
        v = schema.get("minimum", 1)
        if schema.get("maximum") is not None:
            v = min(v, schema["maximum"])
        return v
    if stype == "boolean":
        return True
    if stype == "array":
        return [sample_value(schema.get("items") or {}, spec)]
    if stype == "object":
        out = {}
        for name in schema.get("required") or []:
            prop = (schema.get("properties") or {}).get(name) or {}
            out[name] = sample_value(prop, spec)
        return out
    # string
    n = schema.get("minLength", 1) or 1
    if schema.get("pattern"):
        return "sample"
    return "x" * max(1, n)


def _mutations(schema, base):
    """Yield (kind, value, expect) boundary mutations for a scalar schema."""
    stype = schema.get("type", "string")
    if schema.get("enum"):
        yield ("enum-valid", schema["enum"][0], "accept")
        invalid = "__toolcontract_invalid__"
        while invalid in schema["enum"]:
            invalid += "x"
        yield ("enum-invalid", invalid, "reject")
    if stype in ("integer", "number"):
        cast = int if stype == "integer" else float
        if schema.get("minimum") is not None:
            yield ("minimum", cast(schema["minimum"]), "accept")
            yield ("below-minimum", cast(schema["minimum"]) - 1, "reject")
        if schema.get("maximum") is not None:
            yield ("maximum", cast(schema["maximum"]), "accept")
            yield ("above-maximum", cast(schema["maximum"]) + 1, "reject")
    if stype == "string":
        if schema.get("minLength"):
            yield ("min-length", "x" * schema["minLength"], "accept")
            if schema["minLength"] >= 1:
                yield ("below-min-length", "x" * (schema["minLength"] - 1), "reject")
        if schema.get("maxLength") is not None:
            yield ("max-length", "x" * schema["maxLength"], "accept")
            yield ("above-max-length", "x" * (schema["maxLength"] + 1), "reject")
        if schema.get("pattern"):
            bad = "!!!invalid!!!"
            if not re.search(schema["pattern"], bad):
                yield ("pattern-violation", bad, "reject")


def generate_cases(spec):
    """Generate boundary cases from the declared constraints of the spec."""
    cases = []

    def add(op_loc, method, path, kind, detail, expect, query, path_values,
            body, subject):
        cases.append({
            "id": f"{method.upper()} {path} :: {subject} :: {kind}",
            "operation": op_loc, "method": method, "path": path,
            "kind": kind, "detail": detail, "expect": expect,
            "query": query, "path_values": path_values, "body": body,
            "subject": subject,
        })

    for path, method, op in operations(spec):
        op_loc = f"{method.upper()} {path}"
        path_item = (spec.get("paths") or {}).get(path) or {}
        params = []
        for raw in (path_item.get("parameters") or []) + (op.get("parameters") or []):
            p = resolve_ref(spec, raw)
            if isinstance(p, dict) and p.get("name"):
                params.append(p)

        base_query, base_path_values = {}, {}
        for p in params:
            schema = resolve_ref(spec, p.get("schema") or {})
            val = sample_value(schema, spec)
            if p.get("in") == "path":
                base_path_values[p["name"]] = val
            elif p.get("in") == "query":
                base_query[p["name"]] = val

        body_schema = None
        base_body = None
        body = resolve_ref(spec, op.get("requestBody") or {})
        for media in (body.get("content") or {}).values():
            if isinstance(media, dict) and media.get("schema"):
                body_schema = resolve_ref(spec, media["schema"])
                base_body = sample_value(body_schema, spec)
                break

        add(op_loc, method, path, "baseline",
            "all parameters/body at valid sample values", "accept",
            dict(base_query), dict(base_path_values),
            json.loads(json.dumps(base_body)) if base_body is not None else None,
            "baseline")

        for p in params:
            name = p["name"]
            schema = resolve_ref(spec, p.get("schema") or {})
            for kind, value, expect in _mutations(schema, None):
                q, pv = dict(base_query), dict(base_path_values)
                if p.get("in") == "path":
                    pv[name] = value
                else:
                    q[name] = value
                add(op_loc, method, path, kind,
                    f"{name}={value!r} (declared "
                    f"{ {k: schema[k] for k in ('minimum','maximum','minLength','maxLength','enum','pattern') if k in schema} })",
                    expect, q, pv,
                    json.loads(json.dumps(base_body)) if base_body is not None else None,
                    name)
            if p.get("required") and p.get("in") == "query":
                q = dict(base_query)
                q.pop(name, None)
                add(op_loc, method, path, "missing-required",
                    f"required query parameter '{name}' omitted", "reject",
                    q, dict(base_path_values),
                    json.loads(json.dumps(base_body)) if base_body is not None else None,
                    name)

        if isinstance(body_schema, dict):
            required_list = body_schema.get("required") or []
            for pname, pschema in (body_schema.get("properties") or {}).items():
                ps = resolve_ref(spec, pschema)
                for kind, value, expect in _mutations(ps, None):
                    b = json.loads(json.dumps(base_body)) if isinstance(base_body, dict) else {}
                    b[pname] = value
                    add(op_loc, method, path, kind,
                        f"body property {pname}={value!r}", expect,
                        dict(base_query), dict(base_path_values), b, pname)
                if pname in required_list:
                    b = json.loads(json.dumps(base_body)) if isinstance(base_body, dict) else {}
                    b.pop(pname, None)
                    add(op_loc, method, path, "missing-required",
                        f"required body property '{pname}' omitted", "reject",
                        dict(base_query), dict(base_path_values), b, pname)
    return cases


def _type_ok(value, stype):
    if stype == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if stype == "number":
        return (isinstance(value, (int, float)) and not isinstance(value, bool))
    if stype == "string":
        return isinstance(value, str)
    if stype == "boolean":
        return isinstance(value, bool)
    if stype == "array":
        return isinstance(value, list)
    if stype == "object":
        return isinstance(value, dict)
    return True


def validate_value(value, schema, spec, where="$"):
    """Validate a JSON value against the schema subset we document.

    Returns a list of violation strings (empty = conforms)."""
    schema = resolve_ref(spec, schema) if spec else schema
    if not isinstance(schema, dict):
        return []
    out = []
    stype = schema.get("type")
    if stype and not _type_ok(value, stype):
        return [f"{where}: expected type {stype}, got "
                f"{'null' if value is None else type(value).__name__} "
                f"(value {value!r})"]
    if "enum" in schema and value not in schema["enum"]:
        out.append(f"{where}: {value!r} not in enum {schema['enum']}")
    if stype in ("integer", "number") and isinstance(value, (int, float)):
        if schema.get("minimum") is not None and value < schema["minimum"]:
            out.append(f"{where}: {value} < minimum {schema['minimum']}")
        if schema.get("maximum") is not None and value > schema["maximum"]:
            out.append(f"{where}: {value} > maximum {schema['maximum']}")
    if stype == "string" and isinstance(value, str):
        if schema.get("minLength") is not None and len(value) < schema["minLength"]:
            out.append(f"{where}: length {len(value)} < minLength {schema['minLength']}")
        if schema.get("maxLength") is not None and len(value) > schema["maxLength"]:
            out.append(f"{where}: length {len(value)} > maxLength {schema['maxLength']}")
        if schema.get("pattern") and not re.search(schema["pattern"], value):
            out.append(f"{where}: {value!r} does not match pattern {schema['pattern']}")
    if stype == "object" and isinstance(value, dict):
        for name in schema.get("required") or []:
            if name not in value:
                out.append(f"{where}: required property '{name}' missing")
        for name, pschema in (schema.get("properties") or {}).items():
            if name in value:
                out.extend(validate_value(value[name], pschema, spec,
                                          f"{where}.{name}"))
    if stype == "array" and isinstance(value, list) and schema.get("items"):
        for i, item in enumerate(value):
            out.extend(validate_value(item, schema["items"], spec, f"{where}[{i}]"))
    return out


def _success_schema(spec, op):
    for code, resp in (op.get("responses") or {}).items():
        if str(code).startswith("2"):
            resp = resolve_ref(spec, resp)
            for media in (resp.get("content") or {}).values():
                if isinstance(media, dict) and media.get("schema"):
                    return resolve_ref(spec, media["schema"])
    return None


def _request(target, case):
    path = case["path"]
    for name, val in case["path_values"].items():
        path = path.replace("{" + name + "}", urllib.parse.quote(str(val), safe=""))
    url = target.rstrip("/") + path
    if case["query"]:
        url += "?" + urllib.parse.urlencode(case["query"])
    data, headers = None, {}
    if case["body"] is not None:
        data = json.dumps(case["body"]).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers,
                                 method=case["method"].upper())
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status, resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")


def run_cases(spec, target, cases=None):
    """Execute cases against the authorized target; compare with the spec.

    Returns a report dict: cases run, per-case results, discrepancies.
    A discrepancy is a documented-vs-observed divergence — including the
    silent-failure class: HTTP 200 whose body violates the documented
    response schema."""
    cases = cases if cases is not None else generate_cases(spec)
    ops = {(p, m): op for p, m, op in operations(spec)}
    results, discrepancies = [], []
    for case in cases:
        try:
            status, body_text = _request(target, case)
        except Exception as exc:  # unreachable target: not checked, say so
            results.append({**case, "status": None, "outcome": "inaccessible",
                            "note": f"request failed: {exc}"})
            continue
        outcome, note = "ok", ""
        if case["expect"] == "accept" and status >= 400:
            outcome = "discrepancy"
            note = (f"spec allows this input but the target rejected it "
                    f"with HTTP {status}")
            discrepancies.append({**case, "status": status,
                                  "kind": "rejects-allowed", "note": note})
        elif case["expect"] == "reject" and status < 400:
            outcome = "discrepancy"
            note = (f"spec forbids this input but the target accepted it "
                    f"with HTTP {status} (silent failure: no error surfaced)")
            discrepancies.append({**case, "status": status,
                                  "kind": "accepts-forbidden", "note": note})
        elif status >= 500:
            outcome = "discrepancy"
            note = f"target returned HTTP {status} (server error)"
            discrepancies.append({**case, "status": status,
                                  "kind": "server-error", "note": note})
        if outcome == "ok" and case["kind"] == "baseline" and 200 <= status < 300:
            op = ops.get((case["path"], case["method"]))
            schema = _success_schema(spec, op) if op else None
            if schema is not None:
                try:
                    payload = json.loads(body_text) if body_text.strip() else None
                    violations = validate_value(payload, schema, spec)
                except json.JSONDecodeError:
                    violations = ["response body is not valid JSON"]
                if violations:
                    outcome = "discrepancy"
                    note = ("HTTP %d returned but the body violates the "
                            "documented response schema: %s"
                            % (status, "; ".join(violations)))
                    discrepancies.append({**case, "status": status,
                                          "kind": "response-schema",
                                          "note": note})
        results.append({**case, "status": status, "outcome": outcome,
                        "note": note})
    return {
        "target": target,
        "cases_run": len(results),
        "checked": sum(1 for r in results if r["outcome"] != "inaccessible"),
        "inaccessible": sum(1 for r in results if r["outcome"] == "inaccessible"),
        "discrepancies": discrepancies,
        "results": results,
    }
