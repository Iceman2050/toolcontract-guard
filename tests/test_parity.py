"""Parity with the EvalScope ``tool_contract`` module.

The fixtures in ``parity_fixtures/`` are the module's own test
fixtures, copied verbatim. The expected verdicts below are the
module's recorded verdicts on them (module lint classes mapped to
this tool's TCG codes), verified by differential runs of both CLIs
on 2026-11-15. If the module's checks ever change, these
expectations must be re-derived from a fresh differential run —
never adjusted to fit this tool's output.
"""
import json
from collections import Counter
from pathlib import Path

from toolcontract.cli import main
from toolcontract.core import lint_spec
from toolcontract.loader import load_spec

FIX = Path(__file__).resolve().parent / "parity_fixtures"


def verdicts(path):
    findings = lint_spec(load_spec(FIX / path))
    return Counter((f.code, f.severity, f.subject, f.missing_keyword)
                   for f in findings)


def test_module_orders_fixture_verdicts():
    # The module reports exactly 10 findings on its planted spec:
    # prose-only minimum/maximum/enum (high), prose-only maxLength
    # (medium), prose-claimed required (medium), one unconstrained
    # note (low), required-names-undeclared (high), enum duplicates
    # (medium), enum type mismatch (medium), no error response (low).
    assert verdicts("orders-api.json") == Counter({
        ("TCG001", "high", "quantity", "minimum"): 1,
        ("TCG001", "high", "quantity", "maximum"): 1,
        ("TCG001", "high", "channel", "enum"): 1,
        ("TCG001", "medium", "note", "maxLength"): 1,
        ("TCG006", "medium", "email", "required"): 1,
        ("TCG002", "low", "coupon", None): 1,
        ("TCG003", "high", "coupon_code", None): 1,
        ("TCG004", "medium", "priority", None): 1,
        ("TCG005", "medium", "retries", None): 1,
        ("TCG009", "low", "GET /orders/{order_id}", None): 1,
    })


def test_module_clean_fixtures_verdicts():
    assert verdicts("clean-api.json") == Counter()
    assert verdicts("staging-api.json") == Counter()
    assert verdicts("clean-api.yaml") == Counter()


def test_module_secret_fixture_verdict_and_no_leak(capsys):
    assert verdicts("secret-api.json") == Counter({
        ("TCG002", "low", "legacy_key", None): 1,
    })
    assert main(["lint", str(FIX / "secret-api.json"),
                 "--format", "json"]) == 0
    out = capsys.readouterr().out
    assert "tcPlanted" + "SecretValue98765" not in out
    assert "[REDACTED]" in out


def test_module_fixture_exit_codes(capsys):
    assert main(["lint", str(FIX / "orders-api.json")]) == 1
    capsys.readouterr()
    assert main(["lint", str(FIX / "clean-api.json")]) == 0
    capsys.readouterr()
    assert main(["lint", str(FIX / "staging-api.json")]) == 0
    capsys.readouterr()
    assert main(["lint", str(FIX / "secret-api.json")]) == 0
    capsys.readouterr()


def test_refusals_exit_2(tmp_path, capsys):
    not_api = tmp_path / "notapi.json"
    not_api.write_text('{"hello": "world"}')
    assert main(["lint", str(not_api)]) == 2
    capsys.readouterr()
    malformed = tmp_path / "bad.json"
    malformed.write_text("{not json")
    assert main(["lint", str(malformed)]) == 2
    capsys.readouterr()
    assert main(["lint", str(tmp_path / "missing.json")]) == 2
    capsys.readouterr()


def test_required_parameter_prose_quirk():
    # Module behaviour, ported faithfully: a parameter already
    # marked required whose prose matches the required family still
    # raises a prose-required finding.
    spec = {"openapi": "3.0.3", "info": {"title": "Q", "version": "1"},
            "paths": {"/things": {"get": {
                "parameters": [{
                    "name": "tenant", "in": "query", "required": True,
                    "description": "Tenant key. This field is required.",
                    "schema": {"type": "string", "maxLength": 64}}],
                "responses": {
                    "200": {"description": "OK", "content": {
                        "application/json": {"schema": {"type": "object"}}}},
                    "400": {"description": "Bad"}}}}}}
    hits = [f for f in lint_spec(spec) if f.code == "TCG006"]
    assert len(hits) == 1 and hits[0].severity == "medium"
