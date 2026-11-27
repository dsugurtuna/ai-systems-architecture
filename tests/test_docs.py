"""Documentation integrity tests matching README claims, CLI outputs, and doc links."""

from __future__ import annotations

import io
import re

import pytest

from ai_systems_arch.cli import build_parser, main
from tests.conftest import ROOT


def test_readme_real_output_matches_cli(monkeypatch: pytest.MonkeyPatch) -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    matches = list(
        re.finditer(r"Real output of `aiarch ([^`]+)`:\n\n```text\n(.*?)```", readme, re.S)
    )
    assert len(matches) >= 2, "README must include real CLI outputs for economics and sensitivity"

    monkeypatch.chdir(ROOT)
    for found in matches:
        argv = found.group(1).split()
        quoted = found.group(2)
        out = io.StringIO()
        code = main(argv, stdout=out)
        assert code == 0
        assert out.getvalue() == quoted


def test_readme_commands_exist_and_doc_links_resolve() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    commands = set(re.findall(r"^aiarch (\w+)", readme, flags=re.MULTILINE))
    assert {"validate", "check", "economics", "sensitivity", "compare"} <= commands
    known = set(build_parser()._subparsers._group_actions[0].choices)  # type: ignore[union-attr]
    assert commands <= known

    adrs = re.findall(r"\((docs/adrs/[^)]+)\)", readme)
    assert len(adrs) == 4
    for rel in adrs:
        assert (ROOT / rel).is_file(), f"Missing ADR referenced in README: {rel}"

    diagrams = re.findall(r"\((docs/diagrams/[^)]+)\)", readme)
    assert len(diagrams) >= 1
    for rel in diagrams:
        assert (ROOT / rel).is_file(), f"Missing diagram referenced in README: {rel}"
