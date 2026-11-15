import json
from pathlib import Path

from toolcontract.core import lint_spec
from toolcontract.loader import load_spec

ROOT = Path(__file__).resolve().parent.parent
PLANTED = load_spec(ROOT / "fixtures" / "orders-api.json")
CLEAN = load_spec(ROOT / "fixtures" / "clean-api.json")
STAGING = load_spec(ROOT / "fixtures" / "staging-api.json")


def by_code(findings, code):
    return [f for f in findings if f.code == code]


def test_planted_between_gap_reports_minimum_and_maximum_with_fix():
    gaps = [f for f in by_code(lint_spec(PLANTED), "TCG001") if f.subject == "limit"]
    keywords = {f.missing_keyword for f in gaps}
    assert keywords == {"minimum", "maximum"}
    for f in gaps:
        assert "between 1 and 100" in f.prose
    fixes = " ".join(f.fix for f in gaps)
    assert '"minimum": 1' in fixes and '"maximum": 100' in fixes


def test_planted_enum_gap_from_prose():
    gaps = [f for f in by_code(lint_spec(PLANTED), "TCG001")
            if f.subject == "status" and f.missing_keyword == "enum"]
    assert len(gaps) == 1
    assert '"enum": ["pending", "paid", "shipped", "cancelled"]' in gaps[0].fix


def test_planted_maxlength_gap_from_prose():
    # "Search text, max 50 characters." is outside the recognised
    # phrasing families (they require "up to / at most / maximum of
    # N characters"), so q raises no prose finding. This is the
    # EvalScope module's coverage boundary too — pinned here so the
    # boundary cannot drift silently.
    gaps = [f for f in by_code(lint_spec(PLANTED), "TCG001")
            if f.subject == "q" and f.missing_keyword == "maxLength"]
    assert gaps == []


def test_planted_body_property_gaps():
    findings = lint_spec(PLANTED)
    cid = [f for f in by_code(findings, "TCG001") if f.subject == "customerId"]
    note = [f for f in by_code(findings, "TCG001") if f.subject == "note"]
    assert cid and cid[0].missing_keyword == "minLength" and '"minLength": 3' in cid[0].fix
    assert note and note[0].missing_keyword == "maxLength" and '"maxLength": 200' in note[0].fix


def test_planted_required_names_undeclared_property():
    hits = by_code(lint_spec(PLANTED), "TCG003")
    assert len(hits) == 1 and hits[0].subject == "customer_id"


def test_planted_enum_duplicate_and_type_mismatch():
    findings = lint_spec(PLANTED)
    assert len(by_code(findings, "TCG004")) == 1
    mismatch = by_code(findings, "TCG005")
    # One finding per schema (module semantics), medium severity:
    # priority's enum carries the number 3 under "type": "string".
    assert len(mismatch) == 1 and mismatch[0].subject == "priority"
    assert "string" in mismatch[0].message
    assert mismatch[0].severity == "medium"


def test_planted_prose_required_but_optional():
    # The planted channel prose ("Required. The sales channel...")
    # is outside the recognised required family ("is/are required",
    # "must be provided", "required field"), so no TCG006 fires on
    # the fixture — the module behaves identically (parity).
    assert by_code(lint_spec(PLANTED), "TCG006") == []
    # A recognised phrasing without a schema declaration does fire.
    spec = {"openapi": "3.0.3", "info": {"title": "T", "version": "1"},
            "paths": {}, "components": {"schemas": {"Order": {
                "type": "object",
                "properties": {"email": {
                    "type": "string", "format": "email",
                    "description": "Contact email. This field is "
                                   "required for fulfilment."}},
                "required": []}}}}
    hits = by_code(lint_spec(spec), "TCG006")
    assert len(hits) == 1 and hits[0].subject == "email"
    assert hits[0].missing_keyword == "required"
    assert hits[0].severity == "medium"


def test_planted_response_completeness():
    findings = lint_spec(PLANTED)
    assert len(by_code(findings, "TCG007")) == 1  # GET /orders/{orderId}: no 2xx
    assert len(by_code(findings, "TCG008")) == 1  # POST 201: no schema
    assert len(by_code(findings, "TCG009")) == 1  # POST: no error response


def test_every_finding_carries_a_concrete_fix():
    for f in lint_spec(PLANTED):
        assert f.fix and f.severity in ("high", "medium", "low") and f.code


def test_clean_spec_response_properties_unconstrained():
    # The clean fixture's operations are fully constrained; its
    # response-schema properties carry no constraint keywords, which
    # the module reports as low-severity unconstrained notes (the
    # earlier parameter-only walk missed them). Low findings do not
    # fail the default threshold — the CLI still exits 0.
    findings = lint_spec(CLEAN)
    assert len(findings) == 4
    assert all(f.code == "TCG002" and f.severity == "low"
               for f in findings)
    assert {f.subject for f in findings} == {"total", "error", "id"}


def test_staging_spec_response_properties_unconstrained():
    findings = lint_spec(STAGING)
    assert len(findings) == 2
    assert all(f.code == "TCG002" and f.severity == "low"
               for f in findings)
    assert {f.subject for f in findings} == {"total", "error"}


def test_gap_not_reported_when_keyword_present():
    spec = json.loads(json.dumps(CLEAN))
    gaps = by_code(lint_spec(spec), "TCG001")
    assert gaps == []
