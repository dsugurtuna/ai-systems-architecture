"""CLI tests covering validate, check, economics, and compare."""

from __future__ import annotations

import io
import json

from ai_systems_arch.cli import main
from tests.conftest import EXAMPLES


def test_cli_validate_examples() -> None:
    out = io.StringIO()
    err = io.StringIO()
    files = [str(p) for p in sorted(EXAMPLES.glob("*.yaml"))]
    code = main(["validate", *files], stdout=out, stderr=err)
    assert code == 0
    assert err.getvalue() == ""
    assert out.getvalue().count("VALID ") == 4


def test_cli_check_fail_on_high() -> None:
    out = io.StringIO()
    code_sov = main(
        ["check", str(EXAMPLES / "sovereign-defence-briefing.yaml"), "--fail-on", "high"],
        stdout=out,
    )
    assert code_sov == 1
    assert "ARCH-SOV-001" in out.getvalue()

    out_ok = io.StringIO()
    code_fin = main(
        ["check", str(EXAMPLES / "regulated-financial-risk-triage.yaml"), "--fail-on", "high"],
        stdout=out_ok,
    )
    assert code_fin == 0


def test_cli_economics_json_and_recommendation() -> None:
    out = io.StringIO()
    code = main(
        ["economics", str(EXAMPLES / "regulated-financial-risk-triage.yaml"), "--format", "json"],
        stdout=out,
    )
    assert code == 0
    data = json.loads(out.getvalue())
    assert data["recommended_option_id"] == "opt-tiered-cascade"

    out_open = io.StringIO()
    code_open = main(
        ["economics", str(EXAMPLES / "high-volume-document-triage.yaml"), "--format", "json"],
        stdout=out_open,
    )
    assert code_open == 0
    data_open = json.loads(out_open.getvalue())
    assert data_open["recommended_option_id"] == "opt-self-hosted-open"


def test_cli_compare_examples() -> None:
    out = io.StringIO()
    code = main(["compare", str(EXAMPLES)], stdout=out)
    assert code == 0
    text = out.getvalue()
    assert "sovereign-defence-briefing.yaml" in text
    assert "regulated-financial-risk-triage.yaml" in text
    assert "high-volume-document-triage.yaml" in text
    assert "opt-sovereign-endpoint" in text
    assert "opt-tiered-cascade" in text
    assert "opt-grounded-cascade" in text
    assert "opt-self-hosted-open" in text
