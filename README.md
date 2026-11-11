# toolcontract-guard

**Lint an API spec for the constraints an AI agent cannot see.**

An authored OpenAPI spec is the contract a machine reader — an AI agent,
a code generator, a client SDK — actually consumes. But authors routinely
state the real constraints in prose: a `description` that says *"must be
between 1 and 100"* while the schema declares no `minimum` or `maximum`.
The prose is invisible to machines, so the agent guesses, overflows the
limit, and the API rejects it — or worse, silently accepts it.

`toolcontract` closes that gap in three steps:

1. **`lint`** — static, spec-first. Finds constraints stated in prose
   `description` fields but missing as machine-checkable schema keywords
   (`minimum` / `maximum` / `minLength` / `maxLength` / `pattern` /
   `format` / `enum` / `required`), checks required/enum consistency and
   response-schema completeness. **Every finding names the parameter or
   property, quotes the prose, names the missing keyword, and gives the
   concrete schema fix.**
2. **`test`** — behaviour verification. Generates boundary test cases
   *from the declared constraints* (min, min−1, max, max+1, enum-valid,
   enum-invalid, missing-required, length and pattern violations) and
   executes them — **only against a staging `--target` you explicitly
   supply**. Documented-vs-observed discrepancies are reported, including
   the silent-failure class: HTTP 200 for input the spec forbids, and
   HTTP 200 whose body violates the documented response schema.
3. **`report`** — enforcement. Findings as a human-readable report, JSON,
   or **SARIF** for GitHub code-scanning, with a CI-meaningful exit code
   (non-zero when findings at or above `--fail-on` exist; default `high`).

Zero dependencies. Python 3.10+, standard library only.

## Install

```bash
pip install -e .
toolcontract doctor
```

## Quick start

```bash
# 1. Lint an authored spec (static — contacts nothing, executes nothing)
toolcontract lint fixtures/orders-api.json

# 2. Same findings as SARIF for CI / code-scanning
toolcontract report --spec fixtures/orders-api.json --format sarif --out findings.sarif.json

# 3. Verify behaviour against YOUR staging API (explicit target required)
toolcontract test --spec fixtures/staging-api.json --target http://127.0.0.1:8765
```

Exit codes: `lint` / `report` exit **1** when findings at or above
`--fail-on` (low/medium/high, default high) exist, else **0**. `test`
exits **1** when any discrepancy is found, **2** when it refuses to run
(no `--target`). All commands exit **2** on an unreadable spec.

## The fixture walk-through

`fixtures/orders-api.json` is a fictional orders API with **planted**
prose-only constraints. `toolcontract lint` catches, among others:

- `limit` — *"Must be between 1 and 100."* with no `minimum`/`maximum`
  → fix: add `"minimum": 1` / `"maximum": 100`
- `status` — *"One of: pending, paid, shipped, cancelled."* with no `enum`
- `q` — *"max 50 characters"* with no `maxLength`
- a `required` list naming `customer_id`, which is never declared
- an `enum` with a duplicate value and a value of the wrong type
- an operation with no success response, and one with no error response

`fixtures/clean-api.json` declares everything in the schema and lints
clean. `fixtures/staging-api.json` + `fixtures/mock_server.py` demonstrate
`test`: the mock is a localhost server whose behaviour deliberately
disagrees with its spec — it accepts `limit=101` and an invalid `status`,
and its 200 body carries `total` as a string where the schema documents
an integer. `toolcontract test` reports all of these as discrepancies.

## Fail-closed staging execution — the safety contract

- `test` has **no default target**. Without `--target` it refuses and
  exits 2. It never probes production, never guesses a URL from the spec,
  and never runs as a side effect of `lint`, `inspect`, or `report`.
- Tests run **only** against the target you point it at, in that
  invocation. Point it at staging, never at an API you do not own or are
  not authorized to test.
- Lint is purely static: it reads the spec you authored and nothing else.

## What is checked, what is not — honestly

- **Checked (lint):** prose-vs-schema constraint gaps on parameters and
  request-body properties; unconstrained string/integer/number parameters
  (low severity); `required` lists naming undeclared properties; enum
  duplicates, empty enums, and enum values whose type contradicts the
  schema type; prose claiming "required" for something declared optional;
  missing success responses, missing success-response schemas, missing
  error responses, undocumented responses.
- **Checked (test):** the generated boundary cases listed above, executed
  against your target, plus validation of the baseline success body
  against the documented response schema (subset: types, `required`,
  `enum`, numeric/length bounds, `pattern`, nested properties/items).
- **Not checked:** constraints the prose extractor does not recognise
  (it covers ranges, "at most/at least", character lengths, "one of:"
  lists, "must match pattern", and email format — novel phrasings can be
  missed); cross-parameter rules; auth behaviour; anything about an API
  you have not pointed the tool at. Cases that could not reach the target
  are reported **inaccessible — never as passes**.
- **A clean report is not a certification.** It means the checks above
  found nothing in the spec you provided. Findings state what was
  checked; this tool never certifies an API, a spec, or a vendor.

## Input formats

JSON specs are fully supported (standard `json` parser). YAML specs are
accepted in a documented subset (indentation-based mappings, lists,
scalars, flow lists, comments — no anchors, tags, or multi-line strings),
parsed by a bundled stdlib-only mini-parser, the same approach as the
sibling `sop-contract` tool. Spec-first always: there is **no HAR input**
(see the boundary note below).

## SARIF in CI

```yaml
- name: Lint the API contract
  run: |
    pip install -e .
    toolcontract report --spec openapi.json --format sarif --out toolcontract.sarif.json
- name: Upload SARIF
  if: always()
  uses: github/codeql-action/upload-sarif@v3
  with:
    sarif_file: toolcontract.sarif.json
```

## Motivation

Published research on real-world API specs (the SilentProbe study) found
that most API parameters declare no machine-checkable constraint, and
many state their constraints in prose only — the gap this tool lints for.

## How this differs from Trace2Contract

Trace2Contract (https://github.com/Iceman2050/trace2contract) goes from
*observed traffic to a spec*: give it a HAR capture and it creates a
minimal OpenAPI spec and status-code contract tests, with secret
redaction on by default. ToolContract Guard goes from *an authored spec
(and, with your permission, your staging API) to a verdict*: give it an
OpenAPI / JSON Schema spec and it lints for machine-checkable constraints
an AI agent cannot see — in particular constraints stated in prose
descriptions but missing from the schema — checks required/enum
consistency and response-schema completeness, generates and (only
against a staging target you authorize) executes boundary tests, reports
documented-vs-observed discrepancies including HTTP-200 silent failures,
and emits a report plus SARIF for CI enforcement. ToolContract Guard
takes no HAR input, infers no specs from traffic, and performs no secret
redaction of captures — that is Trace2Contract's job; a spec
Trace2Contract generates can be fed to ToolContract Guard as an ordinary
lint input. ToolContract Guard is also not sop-contract, which tests
agent behaviour against human-approved procedure contracts, not API
specs. Finally: ToolContract Guard is a developer workflow tool (lint +
permitted staging tests + actionable fixes + CI enforcement); it does
not reproduce the SilentProbe research study or its dataset — the
study's published finding, that most API parameters declare no
machine-checkable constraint and many state constraints in prose only,
is the problem this tool exists to catch in your spec. Tests run only
against a staging target you explicitly authorize; the tool never tests
an API you have not pointed it at.

## Layout

```
toolcontract/   cli.py (lint/inspect/test/report/doctor), core.py (lint),
                prose.py (prose constraint extraction), tester.py
                (case generation + authorized execution + response
                validation), report.py (text + SARIF), loader.py,
                yamlmini.py (documented YAML subset)
fixtures/       orders-api.json (planted gaps), clean-api.json,
                staging-api.json, mock_server.py (localhost mock whose
                behaviour deliberately disagrees with its spec)
tests/          pytest suite covering every command and check class
```

Built by Ingenious AI — https://getingeniousai.com
