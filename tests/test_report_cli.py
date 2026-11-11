import json
from pathlib import Path

from toolcontract.cli import main
from toolcontract.core import lint_spec
from toolcontract.loader import load_spec
from toolcontract.report import build_sarif, format_text

ROOT = Path(__file__).resolve().parent.parent
PLANTED_PATH = ROOT / "fixtures" / "orders-api.json"
CLEAN_PATH = ROOT / "fixtures" / "clean-api.json"


def test_sarif_structure_and_results():
    findings = lint_spec(load_spec(PLANTED_PATH))
    sarif = build_sarif(findings, str(PLANTED_PATH))
    assert sarif["version"] == "2.1.0"
    run = sarif["runs"][0]
    assert run["tool"]["driver"]["name"] == "ToolContract Guard"
    assert len(run["results"]) == len(findings)
    first = run["results"][0]
    assert first["ruleId"].startswith("TCG") and "fix" in first["properties"]


def test_text_report_distinguishes_checked_and_not_checked():
    text = format_text(lint_spec(load_spec(PLANTED_PATH)), str(PLANTED_PATH))
    assert "Checked:" in text and "Not checked:" in text
    assert "certif" in text  # honesty language present


def test_cli_lint_exit_codes(capsys):
    assert main(["lint", str(PLANTED_PATH)]) == 1
    capsys.readouterr()
    assert main(["lint", str(CLEAN_PATH)]) == 0
    capsys.readouterr()


def test_cli_lint_fail_on_threshold(capsys):
    # Planted fixture has high findings; --fail-on low still fails, and the
    # clean fixture passes at every threshold.
    assert main(["lint", str(PLANTED_PATH), "--fail-on", "low"]) == 1
    capsys.readouterr()
    assert main(["lint", str(CLEAN_PATH), "--fail-on", "low"]) == 0
    capsys.readouterr()


def test_cli_report_sarif_exit_code_and_parseable(capsys):
    assert main(["report", "--spec", str(PLANTED_PATH), "--format", "sarif"]) == 1
    out = capsys.readouterr().out
    parsed = json.loads(out)
    assert parsed["version"] == "2.1.0" and parsed["runs"][0]["results"]
    assert main(["report", "--spec", str(CLEAN_PATH), "--format", "sarif"]) == 0
    capsys.readouterr()


def test_cli_inspect_and_doctor(capsys):
    assert main(["inspect", str(PLANTED_PATH)]) == 0
    out = capsys.readouterr().out
    assert "operations: 3" in out
    assert main(["doctor"]) == 0
    assert "OK" in capsys.readouterr().out


def test_cli_lint_json_format(capsys):
    assert main(["lint", str(PLANTED_PATH), "--format", "json"]) == 1
    data = json.loads(capsys.readouterr().out)
    assert any(d["missing_keyword"] == "maximum" for d in data)
