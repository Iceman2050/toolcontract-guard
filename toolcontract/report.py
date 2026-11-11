"""Human-readable reports and SARIF output for lint findings."""

import json

from toolcontract import __version__

_LEVEL = {"high": "error", "medium": "warning", "low": "note"}
_RULE_HELP = {
    "TCG001": "A constraint stated in a prose description is not declared as a machine-checkable schema keyword.",
    "TCG002": "A parameter/property declares no machine-checkable constraint at all.",
    "TCG003": "'required' names a property that is not declared.",
    "TCG004": "An enum contains a duplicate value.",
    "TCG005": "An enum value's type does not match the schema type.",
    "TCG006": "Prose says a parameter/property is required but it is declared optional.",
    "TCG007": "An operation documents no success (2xx) response.",
    "TCG008": "A success response documents no response schema.",
    "TCG009": "An operation documents no error (4xx/5xx) response.",
    "TCG010": "A response has no description.",
    "TCG011": "An enum is empty.",
}


def format_text(findings, spec_path):
    lines = [
        "ToolContract Guard — lint report",
        f"Spec checked: {spec_path}",
        "Checked: constraint gaps (prose vs schema keywords), required/enum "
        "consistency, response-schema completeness.",
        "Not checked: anything outside the authored spec — no target was "
        "contacted by lint, and no behaviour is certified by this report.",
        f"Findings: {len(findings)}",
        "",
    ]
    for f in findings:
        lines.append(f"[{f.severity.upper()}] {f.code} {f.location} — {f.subject}")
        lines.append(f"    {f.message}")
        if f.prose:
            lines.append(f"    prose: \"{f.prose}\"")
        if f.missing_keyword:
            lines.append(f"    missing keyword: {f.missing_keyword}")
        lines.append(f"    fix: {f.fix}")
    if not findings:
        lines.append("No findings. (This means the checks above found "
                     "nothing — it is not a certification.)")
    return "\n".join(lines) + "\n"


def build_sarif(findings, spec_path):
    rules, rule_index = [], {}
    for f in findings:
        if f.code not in rule_index:
            rule_index[f.code] = len(rules)
            rules.append({
                "id": f.code,
                "name": f.code,
                "shortDescription": {"text": _RULE_HELP.get(f.code, f.code)},
                "fullDescription": {"text": _RULE_HELP.get(f.code, f.code)},
                "help": {"text": _RULE_HELP.get(f.code, f.code)},
                "defaultConfiguration": {"level": _LEVEL[f.severity]},
            })
    results = []
    for f in findings:
        results.append({
            "ruleId": f.code,
            "ruleIndex": rule_index[f.code],
            "level": _LEVEL[f.severity],
            "message": {"text": f"{f.message} Fix: {f.fix}"},
            "locations": [{
                "physicalLocation": {
                    "artifactLocation": {"uri": spec_path},
                },
                "logicalLocations": [{
                    "name": f.subject,
                    "fullyQualifiedName": f.location,
                    "kind": "resource",
                }],
            }],
            "properties": {
                "severity": f.severity,
                "prose": f.prose,
                "missing_keyword": f.missing_keyword,
                "fix": f.fix,
            },
        })
    return {
        "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
        "version": "2.1.0",
        "runs": [{
            "tool": {"driver": {
                "name": "ToolContract Guard",
                "version": __version__,
                "informationUri": "https://github.com/Iceman2050/toolcontract-guard",
                "rules": rules,
            }},
            "results": results,
        }],
    }


def sarif_text(findings, spec_path):
    return json.dumps(build_sarif(findings, spec_path), indent=2) + "\n"
