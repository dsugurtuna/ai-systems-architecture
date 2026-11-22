"""Documentation integrity tests matching README claims and ADR links to code."""

from __future__ import annotations

import io
import re

from ai_systems_arch.cli import build_parser, main
from tests.conftest import ROOT


def test_readme_real_output_matches_cli(monkeypatch: object) -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    found = re.search(r"Real output of `aiarch ([^`]+)`:\n\n```text\n(.*?)```", readme, re.S)
    assert found, "README must include real output of an aiarch command"
    argv = found.group(1).split()
    quoted = found.group(2)

    import pytest

    assert isinstance(monkeypatch, pytest.MonkeyPatch)
    monkeypatch.chdir(ROOT)
    out = io.StringIO()
    code = main(argv, stdout=out)
    assert code == 0
    assert out.getvalue() == quoted


def test_readme_commands_exist_and_adr_links_resolve() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    commands = set(re.findall(r"^aiarch (\w+)", readme, flags=re.MULTILINE))
    assert {"validate", "check", "economics", "compare"} <= commands
    known = set(build_parser()._subparsers._group_actions[0].choices)  # type: ignore[union-attr]
    assert commands <= known

    adrs = re.findall(r"\((docs/adrs/[^)]+)\)", readme)
    assert len(adrs) == 4
    for rel in adrs:
        assert (ROOT / rel).is_file(), f"Missing ADR referenced in README: {rel}"
