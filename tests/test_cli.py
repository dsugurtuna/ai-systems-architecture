"""CLI tests covering validate, check, economics, compare, sensitivity, and error paths."""

from __future__ import annotations

import io
import json
from pathlib import Path

from ai_systems_arch.cli import main
from tests.conftest import EXAMPLES


def test_cli_validate_examples_and_invalid_input(tmp_path: Path) -> None:
    out = io.StringIO()
    err = io.StringIO()
    files = [str(p) for p in sorted(EXAMPLES.glob("*.yaml"))]
    code = main(["validate", *files], stdout=out, stderr=err)
    assert code == 0
    assert err.getvalue() == ""
    assert out.getvalue().count("VALID ") == 4

    bad = tmp_path / "bad.yaml"
    bad.write_text("schema_version: '1.0'\nworkload: {}\n", encoding="utf-8")
    out_bad = io.StringIO()
    err_bad = io.StringIO()
    code_bad = main(["validate", str(bad)], stdout=out_bad, stderr=err_bad)
    assert code_bad == 1
    assert "INVALID " in err_bad.getvalue()


def test_cli_check_fail_on_high_and_warning_and_missing_file(tmp_path: Path) -> None:
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

    out_warn = io.StringIO()
    code_warn = main(
        ["check", str(EXAMPLES / "scientific-evidence-copilot.yaml"), "--fail-on", "warning"],
        stdout=out_warn,
    )
    assert code_warn == 1
    assert "ARCH-ECO-001" in out_warn.getvalue()

    err = io.StringIO()
    code_missing = main(["check", str(tmp_path / "missing.yaml")], stderr=err)
    assert code_missing == 1
    assert "ERROR " in err.getvalue()


def test_cli_economics_json_and_error_handling(tmp_path: Path) -> None:
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

    bad = tmp_path / "broken.yaml"
    bad.write_text(":::bad yaml:::", encoding="utf-8")
    err = io.StringIO()
    assert main(["economics", str(bad)], stderr=err) == 1
    assert "ERROR " in err.getvalue()


def test_cli_compare_examples_and_empty_dir(tmp_path: Path) -> None:
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

    out_json = io.StringIO()
    assert main(["compare", str(EXAMPLES), "--format", "json"], stdout=out_json) == 0
    rows = json.loads(out_json.getvalue())
    assert len(rows) == 4

    err_empty = io.StringIO()
    assert main(["compare", str(tmp_path)], stderr=err_empty) == 1
    assert "no .yaml or .yml blueprints found" in err_empty.getvalue()

    err_missing = io.StringIO()
    assert main(["compare", str(tmp_path / "nope")], stderr=err_missing) == 1
    assert "directory does not exist" in err_missing.getvalue()


def test_cli_sensitivity_markdown_json_and_errors() -> None:
    out_md = io.StringIO()
    code_md = main(
        ["sensitivity", str(EXAMPLES / "high-volume-document-triage.yaml")],
        stdout=out_md,
    )
    assert code_md == 0
    assert "885,539 req/mo" in out_md.getvalue()
    assert "Volume Sweep" in out_md.getvalue()

    out_json = io.StringIO()
    code_json = main(
        [
            "sensitivity",
            str(EXAMPLES / "regulated-financial-risk-triage.yaml"),
            "--format",
            "json",
        ],
        stdout=out_json,
    )
    assert code_json == 0
    payload = json.loads(out_json.getvalue())
    assert payload["winner_option_id"] == "opt-tiered-cascade"
    assert payload["breakeven_monthly_requests"] == 254_073

    err = io.StringIO()
    code_bad = main(
        [
            "sensitivity",
            str(EXAMPLES / "high-volume-document-triage.yaml"),
            "--winner",
            "unknown-opt",
        ],
        stderr=err,
    )
    assert code_bad == 1
    assert "unknown winner option" in err.getvalue()
