"""toolcontract CLI: lint | inspect | test | report | doctor.

Fail-closed rules (gate §6):
- lint / inspect / report never contact any target and never execute tests.
- test executes ONLY against the --target supplied in that invocation;
  with no --target it refuses and exits 2. There is no default target.
"""

import argparse
import json
import sys

from toolcontract import __version__
from toolcontract.core import SEVERITY_ORDER, at_or_above, lint_spec, operations
from toolcontract.loader import load_spec
from toolcontract.report import format_text, sarif_text
from toolcontract.tester import generate_cases, run_cases


def _load_or_fail(path):
    try:
        return load_spec(path)
    except Exception as exc:
        print(f"error: could not load spec {path}: {exc}", file=sys.stderr)
        return None


def _emit(text, out):
    if out:
        with open(out, "w", encoding="utf-8") as fh:
            fh.write(text)
    else:
        sys.stdout.write(text)


def _cmd_lint(args):
    spec = _load_or_fail(args.spec)
    if spec is None:
        return 2
    findings = lint_spec(spec)
    if args.format == "json":
        _emit(json.dumps([f.to_dict() for f in findings], indent=2) + "\n", args.out)
    else:
        _emit(format_text(findings, args.spec), args.out)
    return 1 if at_or_above(findings, args.fail_on) else 0


def _cmd_report(args):
    spec = _load_or_fail(args.spec)
    if spec is None:
        return 2
    findings = lint_spec(spec)
    if args.format == "sarif":
        _emit(sarif_text(findings, args.spec), args.out)
    elif args.format == "json":
        _emit(json.dumps([f.to_dict() for f in findings], indent=2) + "\n", args.out)
    else:
        _emit(format_text(findings, args.spec), args.out)
    return 1 if at_or_above(findings, args.fail_on) else 0


def _cmd_inspect(args):
    spec = _load_or_fail(args.spec)
    if spec is None:
        return 2
    ops = list(operations(spec))
    n_params = 0
    for _, _, op in ops:
        n_params += len(op.get("parameters") or [])
    schemas = ((spec.get("components") or {}).get("schemas") or {})
    findings = lint_spec(spec)
    print(f"spec: {args.spec}")
    print(f"title: {(spec.get('info') or {}).get('title', '(untitled)')}")
    print(f"paths: {len(spec.get('paths') or {})}  operations: {len(ops)}  "
          f"operation parameters: {n_params}  component schemas: {len(schemas)}")
    print(f"lint findings: {len(findings)} "
          f"(run 'toolcontract lint {args.spec}' for detail)")
    print("checked: constraint gaps, required/enum consistency, "
          "response completeness — static only; no target contacted.")
    return 0


def _cmd_test(args):
    if not args.target:
        print("error: refusing to run tests — no --target was supplied. "
              "toolcontract test executes requests only against a staging "
              "target you explicitly authorize in this invocation; there is "
              "no default target.", file=sys.stderr)
        return 2
    spec = _load_or_fail(args.spec)
    if spec is None:
        return 2
    cases = generate_cases(spec)
    report = run_cases(spec, args.target, cases)
    if args.format == "json":
        _emit(json.dumps(report, indent=2) + "\n", args.out)
    else:
        lines = [
            "ToolContract Guard — staging behaviour verification",
            f"Spec: {args.spec}",
            f"Target (explicitly authorized for this run): {args.target}",
            f"Cases generated from declared constraints: {len(cases)}",
            f"Cases executed: {report['cases_run']}  checked: {report['checked']}  "
            f"inaccessible: {report['inaccessible']}",
            f"Discrepancies (documented vs observed): {len(report['discrepancies'])}",
            "",
        ]
        for r in report["results"]:
            mark = {"ok": "OK", "discrepancy": "DISCREPANCY",
                    "inaccessible": "INACCESSIBLE"}[r["outcome"]]
            lines.append(f"[{mark}] {r['id']} -> HTTP {r['status']}")
            if r["note"]:
                lines.append(f"    {r['note']}")
        lines.append("")
        lines.append("Checked means the target was reached and its behaviour "
                     "was compared with the spec. Inaccessible cases were not "
                     "checked and are never counted as passes.")
        _emit("\n".join(lines) + "\n", args.out)
    return 1 if report["discrepancies"] else 0


def _cmd_doctor(args):
    print(f"doctor: toolcontract {__version__} OK; python "
          f"{sys.version.split()[0]}; commands: lint, inspect, test, report")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="toolcontract",
        description="Lint an authored OpenAPI/JSON-Schema spec for prose-only "
                    "constraints, verify staging behaviour, emit SARIF for CI.")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("lint", help="static lint of an authored spec (never executes anything)")
    p.add_argument("spec")
    p.add_argument("--format", choices=["text", "json"], default="text")
    p.add_argument("--fail-on", choices=list(SEVERITY_ORDER), default="high")
    p.add_argument("--out")
    p.set_defaults(fn=_cmd_lint)

    p = sub.add_parser("inspect", help="static summary of an authored spec")
    p.add_argument("spec")
    p.set_defaults(fn=_cmd_inspect)

    p = sub.add_parser("test", help="execute generated boundary tests against an authorized staging target")
    p.add_argument("--spec", required=True)
    p.add_argument("--target", default=None,
                   help="staging base URL you authorize for this run (required; no default)")
    p.add_argument("--format", choices=["text", "json"], default="text")
    p.add_argument("--out")
    p.set_defaults(fn=_cmd_test)

    p = sub.add_parser("report", help="lint findings as text, JSON, or SARIF")
    p.add_argument("--spec", required=True)
    p.add_argument("--format", choices=["text", "json", "sarif"], default="text")
    p.add_argument("--fail-on", choices=list(SEVERITY_ORDER), default="high")
    p.add_argument("--out")
    p.set_defaults(fn=_cmd_report)

    p = sub.add_parser("doctor", help="self-check")
    p.set_defaults(fn=_cmd_doctor)

    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
