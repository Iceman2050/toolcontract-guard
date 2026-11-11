# Build Report — toolcontract-guard v0.1.0

**Date:** 2026-11-11
**Program:** GODMODE v2.0 Five Business Ideas, Idea 5 (final repo of the program)
**Overlap gate:** PROCEED (see `OVERLAP-GATE.md` in this folder — Trace2Contract
covers 0 of 8 ToolContract Guard scope items in substance). Gate §5 boundary
note is carried in the README in substance; gate §6 conditions are implemented:
spec-first CLI (`lint` / `inspect` / `test` / `report`); fail-closed
staging-only execution (no default target, no execution as a side effect of
lint — verified below); every finding carries the concrete schema fix; no HAR
parsing, no spec inference, no redaction absorbed from Trace2Contract;
differentiation from sop-contract stated explicitly in the README.
**Design:** stdlib-only Python (zero dependencies), JSON specs fully
supported, YAML accepted in a documented subset via a bundled mini-parser
(the sop-contract approach, stated honestly in the README).

## Test suite

```
$ python3 -m pytest -q
................................                                         [100%]
32 passed in 0.65s
```

Coverage by area: prose extraction (7), constraint-gap lint — planted
minimum/maximum, enum, maxLength, minLength gaps with prose quotes and
concrete fixes, every-finding-has-a-fix (5), required/enum consistency —
undeclared required name, enum duplicate, enum type mismatch,
prose-required mismatch (3), response completeness — missing success
response / response schema / error response (1 test asserting all three),
clean + staging specs lint to zero findings (3), case generation from
declared constraints (1), mock-server discrepancy detection incl. the
HTTP-200-but-wrong case (1), response-value validation (1), fail-closed
no-target refusal (1), `test` CLI exit code against the mock (1), SARIF
structure (1), checked/not-checked honesty language (1), CLI exit codes +
`--fail-on` threshold (2), SARIF report CLI + parseability (1),
inspect/doctor (1), lint JSON format (1), YAML-subset loading (1).

## Real fixture demonstrations (verbatim, local runs 2026-11-11)

Planted-gap lint — `fixtures/orders-api.json` (fictional orders API; full
output is 18 findings: 6 prose-gap TCG001 highs, TCG002 lows,
TCG003/TCG004/TCG005 consistency, TCG006/TCG007/TCG008/TCG009
completeness). Excerpt:

```
[HIGH] TCG001 GET /orders parameter 'limit' — limit
    description states a minimum constraint in prose but the schema declares no 'minimum' keyword — an AI agent (or any machine reader) cannot see this constraint
    prose: "Must be between 1 and 100."
    missing keyword: minimum
    fix: add "minimum": 1 to the schema of 'limit'
[HIGH] TCG001 GET /orders parameter 'limit' — limit
    description states a maximum constraint in prose but the schema declares no 'maximum' keyword — an AI agent (or any machine reader) cannot see this constraint
    prose: "Must be between 1 and 100."
    missing keyword: maximum
    fix: add "maximum": 100 to the schema of 'limit'
[HIGH] TCG001 GET /orders parameter 'status' — status
    description states a enum constraint in prose but the schema declares no 'enum' keyword — an AI agent (or any machine reader) cannot see this constraint
    prose: "One of: pending, paid, shipped, cancelled."
    missing keyword: enum
    fix: add "enum": ["pending", "paid", "shipped", "cancelled"] to the schema of 'status'
[HIGH] TCG003 #/paths//orders/post/requestBody/content/application/json/schema — customer_id
    'required' names 'customer_id' but no property 'customer_id' is declared in 'properties' — the requirement can never be satisfied as written
    fix: declare a 'customer_id' property, or remove "customer_id" from 'required'
```
lint exit code on the planted fixture: **1**. On `fixtures/clean-api.json`
and `fixtures/staging-api.json`: **0 findings, exit 0**.

Fail-closed proof:

```
$ toolcontract test --spec fixtures/staging-api.json
error: refusing to run tests — no --target was supplied. toolcontract test
executes requests only against a staging target you explicitly authorize in
this invocation; there is no default target.
exit=2
```

Staging verification against the local mock fixture
(`fixtures/mock_server.py`, localhost only — the mock deliberately accepts
everything and returns `total` as a string where the spec documents an
integer). Full verbatim output:

```
ToolContract Guard — staging behaviour verification
Spec: fixtures/staging-api.json
Target (explicitly authorized for this run): http://127.0.0.1:8792
Cases generated from declared constraints: 7
Cases executed: 7  checked: 7  inaccessible: 0
Discrepancies (documented vs observed): 4

[DISCREPANCY] GET /orders :: baseline :: baseline -> HTTP 200
    HTTP 200 returned but the body violates the documented response schema: $.total: expected type integer, got str (value 'zero')
[OK] GET /orders :: limit :: minimum -> HTTP 200
[DISCREPANCY] GET /orders :: limit :: below-minimum -> HTTP 200
    spec forbids this input but the target accepted it with HTTP 200 (silent failure: no error surfaced)
[OK] GET /orders :: limit :: maximum -> HTTP 200
[DISCREPANCY] GET /orders :: limit :: above-maximum -> HTTP 200
    spec forbids this input but the target accepted it with HTTP 200 (silent failure: no error surfaced)
[OK] GET /orders :: status :: enum-valid -> HTTP 200
[DISCREPANCY] GET /orders :: status :: enum-invalid -> HTTP 200
    spec forbids this input but the target accepted it with HTTP 200 (silent failure: no error surfaced)

Checked means the target was reached and its behaviour was compared with the spec. Inaccessible cases were not checked and are never counted as passes.
```
test exit code against the mock: **1** (4 discrepancies: 3 accepts-forbidden
+ 1 response-schema — the HTTP-200-but-wrong silent-failure case).

SARIF: `toolcontract report --spec fixtures/orders-api.json --format sarif`
→ valid SARIF 2.1.0, 18 results, exit 1 (verified by parsing the output).

## Ship record (verified 2026-11-11 from real output)

- Repo: https://github.com/Iceman2050/toolcontract-guard (public; initial
  commit fad7100).
- Topics staged in `TOPICS.md` before creation, applied via `gh repo edit`,
  and **read back via `gh repo view`: 18 topics** — ai-agents,
  api-documentation, api-testing, automation, cli, code-scanning,
  continuous-integration, contract-testing, developer-tools, devtools,
  github-actions, json-schema, llm, openapi, python, sarif,
  test-automation, testing.
- CI: GitHub Actions run **43060403724** — **success on the first run**,
  matrix Python 3.11 + 3.12 (no 3.9), verified from the actual run log:
  "32 passed" in both matrix jobs, plus the fixture-run step (doctor,
  clean lint exit 0, planted lint exit 1, SARIF parse check, no-target
  fail-closed exit 2).
- Release: https://github.com/Iceman2050/toolcontract-guard/releases/tag/v0.1.0
  (annotated tag v0.1.0 pushed; honest notes, no certification language).
- Attribution check: full-tree grep for "Muse" / "2HCQH1" before push —
  zero matches outside the pre-existing OVERLAP-GATE.md gate document,
  which was authored before this build and is not product surface.
- Registry: `~/workspace/github-godmode-v2/registry.yaml` appended with the
  toolcontract-guard entry (topics + CI run id); file re-parsed as valid YAML.
- Pushes this ship: initial commit push, tag push, and this report push —
  steady spacing, within the GitHub pace law.

## Honesty notes

All APIs in the fixtures are fictional; the mock server binds localhost
only and was the only target ever contacted — no external API was tested.
The tool audits a spec the user authored and tests only an API the user
explicitly points it at. The SilentProbe study is cited in the README in
one attributed line as motivation only; its dataset and results are not
reproduced.
