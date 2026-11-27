"""Command-line interface (`aiarch`) for validating blueprints and pricing routing TCO."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import TextIO

import yaml

from .economics import evaluate_blueprint
from .report import recommend_option, render_json, render_markdown
from .schema import ArchitectureBlueprint, Severity, load_blueprint
from .sensitivity import (
    analyze_sensitivity,
    render_sensitivity_json,
    render_sensitivity_markdown,
)
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

    p_sen = sub.add_parser(
        "sensitivity",
        help="Analyse volume break-even and error-rate tipping points between top options.",
    )
    p_sen.add_argument("file", type=Path)
    p_sen.add_argument("--format", choices=["md", "json"], default="md")
    p_sen.add_argument("--winner", default=None, help="Option ID to treat as baseline winner.")
    p_sen.add_argument("--challenger", default=None, help="Option ID to compare against.")

    return parser


def _load_safe(path: Path, stderr: TextIO, prefix: str = "ERROR") -> ArchitectureBlueprint | None:
    try:
        return load_blueprint(path)
    except (OSError, yaml.YAMLError, ValueError) as exc:
        print(f"{prefix} {path}: {exc}", file=stderr)
        return None


def _cmd_validate(files: list[Path], stdout: TextIO, stderr: TextIO) -> int:
    had_error = False
    for path in files:
        bp = _load_safe(path, stderr, prefix="INVALID")
        if bp is None:
            had_error = True
        else:
            print(
                f"VALID {path}: workload={bp.workload.id} "
                f"({len(bp.models)} models, {len(bp.options)} options)",
                file=stdout,
            )
    return 1 if had_error else 0


def _cmd_check(file: Path, fail_on: str | None, stdout: TextIO, stderr: TextIO) -> int:
    bp = _load_safe(file, stderr)
    if bp is None:
        return 1
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


def _cmd_economics(file: Path, fmt: str, stdout: TextIO, stderr: TextIO) -> int:
    bp = _load_safe(file, stderr)
    if bp is None:
        return 1
    economics = evaluate_blueprint(bp)
    findings = validate_blueprint(bp)
    if fmt == "json":
        stdout.write(render_json(bp, economics, findings))
    else:
        stdout.write(render_markdown(bp, economics, findings))
    return 0


def _cmd_compare(directory: Path, fmt: str, stdout: TextIO, stderr: TextIO) -> int:
    if not directory.is_dir():
        print(f"ERROR {directory}: directory does not exist", file=stderr)
        return 1
    files = sorted([*directory.glob("*.yaml"), *directory.glob("*.yml")])
    if not files:
        print(f"ERROR {directory}: no .yaml or .yml blueprints found", file=stderr)
        return 1

    rows: list[dict[str, object]] = []
    for path in files:
        bp = _load_safe(path, stderr)
        if bp is None:
            return 1
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


def _cmd_sensitivity(
    file: Path,
    fmt: str,
    winner: str | None,
    challenger: str | None,
    stdout: TextIO,
    stderr: TextIO,
) -> int:
    bp = _load_safe(file, stderr)
    if bp is None:
        return 1
    try:
        report = analyze_sensitivity(bp, winner_id=winner, challenger_id=challenger)
    except ValueError as exc:
        print(f"ERROR {file}: {exc}", file=stderr)
        return 1

    if fmt == "json":
        stdout.write(render_sensitivity_json(report))
    else:
        stdout.write(render_sensitivity_markdown(report))
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
        return _cmd_check(args.file, args.fail_on, out, err)
    if args.command == "economics":
        return _cmd_economics(args.file, args.format, out, err)
    if args.command == "compare":
        return _cmd_compare(args.directory, args.format, out, err)
    if args.command == "sensitivity":
        return _cmd_sensitivity(args.file, args.format, args.winner, args.challenger, out, err)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
