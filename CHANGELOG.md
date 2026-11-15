# Changelog

## 0.2.0 — 2026-11-15

Verdict alignment with the EvalScope `tool_contract` module. The
lint engine was re-based on the module's checks (Spec B) so this
standalone tool and the module return identical findings and exit
codes on the same specs; `tests/test_parity.py` pins the module's
verdicts on the module's own fixtures.

Behaviour changes relative to 0.1.0:

- Coverage extended to the module's sites: component schemas and
  response-body schemas (nested properties and array items
  included), not just parameters and request-body properties.
- An unconstrained note (TCG002) is no longer double-reported at a
  site that already carries a prose finding.
- Severities aligned to the module: prose-only length gaps
  (TCG001 minLength/maxLength) are medium (were high); enum type
  mismatch (TCG005) is medium (was high) and is reported once per
  schema (was once per value); missing error response (TCG009) is
  low (was medium).
- Prose-only required (TCG006) now carries `missing_keyword:
  required`, and the recognised required phrasings are the module's
  ("is/are required", "must be provided", "required field") — a
  bare "Required." no longer fires.
- Length phrasings follow the module's families: "max N
  characters" alone no longer yields a maxLength finding; "up to /
  at most / maximum of N characters" does.
- Non-OpenAPI documents are refused with exit 2 (previously a
  non-spec object could lint clean).
- TCG010 (response has no description) retired — outside the
  module's check set.
- SARIF output now honours the report command's `--fail-on`
  threshold, as the module's does.
- Quoted prose and messages are secret-scrubbed before printing
  (new `toolcontract/scrub.py`).

## 0.1.0 — 2026-11-11

Initial release: lint / inspect / test / report / doctor CLI,
prose-vs-schema constraint-gap checks, boundary test generation and
fail-closed staging execution, text + JSON + SARIF reports.
