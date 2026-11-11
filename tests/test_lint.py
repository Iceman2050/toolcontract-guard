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
    gaps = [f for f in by_code(lint_spec(PLANTED), "TCG001")
            if f.subject == "q" and f.missing_keyword == "maxLength"]
    assert len(gaps) == 1 and '"maxLength": 50' in gaps[0].fix


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
    assert len(mismatch) == 1 and "integer" in mismatch[0].message


def test_planted_prose_required_but_optional():
    hits = by_code(lint_spec(PLANTED), "TCG006")
    assert len(hits) == 1 and hits[0].subject == "channel"


def test_planted_response_completeness():
    findings = lint_spec(PLANTED)
    assert len(by_code(findings, "TCG007")) == 1  # GET /orders/{orderId}: no 2xx
    assert len(by_code(findings, "TCG008")) == 1  # POST 201: no schema
    assert len(by_code(findings, "TCG009")) == 1  # POST: no error response


def test_every_finding_carries_a_concrete_fix():
    for f in lint_spec(PLANTED):
        assert f.fix and f.severity in ("high", "medium", "low") and f.code


def test_clean_spec_lints_clean():
    assert lint_spec(CLEAN) == []


def test_staging_spec_lints_clean():
    assert lint_spec(STAGING) == []


def test_gap_not_reported_when_keyword_present():
    spec = json.loads(json.dumps(CLEAN))
    gaps = by_code(lint_spec(spec), "TCG001")
    assert gaps == []
