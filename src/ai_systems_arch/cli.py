"""Command-line interface (`aiarch`) for validating blueprints and pricing routing TCO."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import TextIO

from .economics import evaluate_blueprint
from .report import recommend_option, render_json, render_markdown
from .schema import Severity, load_blueprint
from .validator import validate_blueprint


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="aiarch",
        description=(
            "Validate sovereign/regulated LLM architecture blueprints and model routing TCO."
        ),
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_val = sub.add_parser("validate", help="Validate one or more architecture YAML blueprints.")
    p_val.add_argument("files", nargs="+", type=Path)

    p_chk = sub.add_parser("check", help="Run architecture, sovereignty, and ROI gate checks.")
    p_chk.add_argument("file", type=Path)
    p_chk.add_argument("--fail-on", choices=["high", "warning"], default=None)

    p_eco = sub.add_parser("economics", help="Compute routing economics and gate report.")
    p_eco.add_argument("file", type=Path)
    p_eco.add_argument("--format", choices=["md", "json"], default="md")

    p_cmp = sub.add_parser("compare", help="Compare all YAML blueprints in a directory.")
    p_cmp.add_argument("directory", type=Path)
    p_cmp.add_argument("--format", choices=["md", "json"], default="md")

    return parser


def _cmd_validate(files: list[Path], stdout: TextIO, stderr: TextIO) -> int:
    had_error = False
    for path in files:
        try:
            bp = load_blueprint(path)
        except Exception as exc:
            print(f"INVALID {path}: {exc}", file=stderr)
            had_error = True
        else:
            print(
                f"VALID {path}: workload={bp.workload.id} "
                f"({len(bp.models)} models, {len(bp.options)} options)",
                file=stdout,
            )
    return 1 if had_error else 0


def _cmd_check(file: Path, fail_on: str | None, stdout: TextIO) -> int:
    bp = load_blueprint(file)
    findings = validate_blueprint(bp)
    high_n = sum(1 for f in findings if f.severity == Severity.HIGH)
    warn_n = sum(1 for f in findings if f.severity == Severity.WARNING)
    print(f"{file}: {high_n} high, {warn_n} warning", file=stdout)
    for f in findings:
        scope = f"[{f.option_id}]" if f.option_id else "[blueprint]"
        print(f"  {f.severity.value.upper():7s} {f.rule_id} {scope} {f.title}", file=stdout)

    if fail_on == "high" and high_n > 0:
        return 1
    if fail_on == "warning" and (high_n > 0 or warn_n > 0):
        return 1
    return 0


def _cmd_economics(file: Path, fmt: str, stdout: TextIO) -> int:
    bp = load_blueprint(file)
    economics = evaluate_blueprint(bp)
    findings = validate_blueprint(bp)
    if fmt == "json":
        stdout.write(render_json(bp, economics, findings))
    else:
        stdout.write(render_markdown(bp, economics, findings))
    return 0


def _cmd_compare(directory: Path, fmt: str, stdout: TextIO) -> int:
    files = sorted([*directory.glob("*.yaml"), *directory.glob("*.yml")])
    if not files:
        raise FileNotFoundError(f"no .yaml or .yml blueprints found in {directory}")

    rows: list[dict[str, object]] = []
    for path in files:
        bp = load_blueprint(path)
        economics = evaluate_blueprint(bp)
        findings = validate_blueprint(bp)
        best = recommend_option(economics, findings)
        rows.append(
            {
                "file": path.name,
                "workload_id": bp.workload.id,
                "sensitivity": bp.workload.data_sensitivity.value,
                "residency": bp.workload.residency.value,
                "recommended_option": best.option_id if best else None,
                "recommended_total_gbp": best.total_monthly_gbp if best else None,
                "recommended_savings_gbp": best.net_monthly_savings_gbp if best else None,
                "high_findings": sum(1 for f in findings if f.severity == Severity.HIGH),
                "warning_findings": sum(1 for f in findings if f.severity == Severity.WARNING),
            }
        )

    if fmt == "json":
        stdout.write(json.dumps(rows, indent=2) + "\n")
    else:
        lines = [
            "| Blueprint | Workload | Sensitivity / Residency | Recommended | Total/mo | Net Savings/mo |",  # noqa: E501
            "|---|---|---|---|---:|---:|",
        ]
        for r in rows:
            rec = str(r["recommended_option"] or "BLOCKED")
            tot = (
                f"£{r['recommended_total_gbp']:,.2f}"
                if r["recommended_total_gbp"] is not None
                else "-"
            )
            sav = (
                f"£{r['recommended_savings_gbp']:,.2f}"
                if r["recommended_savings_gbp"] is not None
                else "-"
            )
            lines.append(
                f"| `{r['file']}` | `{r['workload_id']}` | "
                f"`{r['sensitivity']}` / `{r['residency']}` | `{rec}` | {tot} | {sav} |"
            )
        stdout.write("\n".join(lines) + "\n")
    return 0


def main(
    argv: Sequence[str] | None = None,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> int:
    out = stdout if stdout is not None else sys.stdout
    err = stderr if stderr is not None else sys.stderr
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)

    if args.command == "validate":
        return _cmd_validate(args.files, out, err)
    if args.command == "check":
        return _cmd_check(args.file, args.fail_on, out)
    if args.command == "economics":
        return _cmd_economics(args.file, args.format, out)
    if args.command == "compare":
        return _cmd_compare(args.directory, args.format, out)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
