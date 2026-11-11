import importlib.util
import threading
from pathlib import Path

import pytest

from toolcontract.cli import main
from toolcontract.loader import load_spec
from toolcontract.tester import generate_cases, run_cases, validate_value

ROOT = Path(__file__).resolve().parent.parent
STAGING = load_spec(ROOT / "fixtures" / "staging-api.json")


@pytest.fixture(scope="module")
def mock_url():
    spec = importlib.util.spec_from_file_location(
        "mock_server", ROOT / "fixtures" / "mock_server.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    srv = mod.make_server(0)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()


def test_cases_generated_from_declared_constraints():
    cases = generate_cases(STAGING)
    kinds = {(c["subject"], c["kind"], c["expect"]) for c in cases}
    assert ("limit", "minimum", "accept") in kinds
    assert ("limit", "below-minimum", "reject") in kinds
    assert ("limit", "maximum", "accept") in kinds
    assert ("limit", "above-maximum", "reject") in kinds
    assert ("status", "enum-valid", "accept") in kinds
    assert ("status", "enum-invalid", "reject") in kinds
    assert any(c["kind"] == "baseline" for c in cases)


def test_mock_discrepancies_detected_including_200_but_wrong(mock_url):
    report = run_cases(STAGING, mock_url)
    kinds = {d["kind"] for d in report["discrepancies"]}
    assert "accepts-forbidden" in kinds
    assert "response-schema" in kinds
    schema_hits = [d for d in report["discrepancies"] if d["kind"] == "response-schema"]
    assert "total" in schema_hits[0]["note"] and "200" in schema_hits[0]["note"]
    forbidden = [d for d in report["discrepancies"] if d["kind"] == "accepts-forbidden"]
    subjects = {d["subject"] for d in forbidden}
    assert "limit" in subjects and "status" in subjects
    assert report["inaccessible"] == 0 and report["checked"] == report["cases_run"]


def test_validate_value_type_and_required():
    schema = {"type": "object", "required": ["total"],
              "properties": {"total": {"type": "integer"}}}
    assert validate_value({"total": 3}, schema, None) == []
    assert validate_value({"total": "zero"}, schema, None)
    assert validate_value({}, schema, None)


def test_test_command_fails_closed_without_target(capsys):
    rc = main(["test", "--spec", str(ROOT / "fixtures" / "staging-api.json")])
    assert rc == 2
    assert "refusing" in capsys.readouterr().err


def test_test_command_against_mock_exits_1(mock_url, capsys):
    rc = main(["test", "--spec", str(ROOT / "fixtures" / "staging-api.json")
               if False else str(ROOT / "fixtures" / "staging-api.json"),
               "--target", mock_url])
    out = capsys.readouterr().out
    assert rc == 1 and "DISCREPANCY" in out
