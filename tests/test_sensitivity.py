"""Tests for sensitivity analysis and report gate formatting edge cases."""

from __future__ import annotations

import json

import pytest

from ai_systems_arch.economics import evaluate_blueprint
from ai_systems_arch.report import recommend_option, render_json, render_markdown
from ai_systems_arch.schema import ArchitectureBlueprint, load_blueprint
from ai_systems_arch.sensitivity import (
    analyze_sensitivity,
    render_sensitivity_json,
    render_sensitivity_markdown,
)
from ai_systems_arch.validator import validate_blueprint
from tests.conftest import EXAMPLES, sample_blueprint_dict


def test_sensitivity_breakeven_and_error_tipping_are_mathematically_exact() -> None:
    bp = load_blueprint(EXAMPLES / "high-volume-document-triage.yaml")
    report = analyze_sensitivity(bp)

    assert report.winner_option_id == "opt-self-hosted-open"
    assert report.challenger_option_id == "opt-private-frontier"
    assert report.breakeven_monthly_requests == 885_539
    assert report.breakeven_direction == "winner_cheaper_above"
    assert report.max_blended_error_delta == pytest.approx(0.000153, abs=1e-6)

    # Verify exact equality at break-even monthly_requests
    bp_be = bp.model_copy(
        update={"workload": bp.workload.model_copy(update={"monthly_requests": 885_539})}
    )
    econ_be = {e.option_id: e for e in evaluate_blueprint(bp_be)}
    assert (
        abs(
            econ_be["opt-self-hosted-open"].total_monthly_gbp
            - econ_be["opt-private-frontier"].total_monthly_gbp
        )
        < 1.0
    )

    # Verify plugging tipping error rate erodes the margin to ~0
    assert report.tipping_primary_error_rate is not None
    raw_tip = bp.model_dump()
    for m in raw_tip["models"]:
        if m["id"] == "uk-open-weights-cluster":
            m["escaped_error_rate"] = report.tipping_primary_error_rate
    bp_tip = ArchitectureBlueprint.model_validate(raw_tip)
    econ_tip = {e.option_id: e for e in evaluate_blueprint(bp_tip)}
    assert (
        abs(
            econ_tip["opt-self-hosted-open"].total_monthly_gbp
            - econ_tip["opt-private-frontier"].total_monthly_gbp
        )
        < 50.0
    )

    # Volume sweep triggers ARCH-CAP-002 at 3,200,000 req/mo
    high_pts = [pt for pt in report.volume_sweep if pt.monthly_requests >= 3_200_000]
    assert high_pts
    assert all("opt-self-hosted-open" in pt.capacity_warning_options for pt in high_pts)


def test_sensitivity_handles_shared_primary_model_cleanly() -> None:
    bp = load_blueprint(EXAMPLES / "scientific-evidence-copilot.yaml")
    report = analyze_sensitivity(bp)
    assert report.winner_option_id == "opt-grounded-cascade"
    assert report.challenger_option_id == "opt-cheap-unverified"
    # Higher error on shared small-cheap-model helps cascade; negative delta indicates direction
    assert report.max_primary_error_delta is not None
    assert report.max_primary_error_delta < 0.0

    md = render_sensitivity_markdown(report)
    assert "Break-even volume" in md
    payload = json.loads(render_sensitivity_json(report))
    assert payload["winner_option_id"] == "opt-grounded-cascade"


def test_sensitivity_single_option_blueprint() -> None:
    raw = sample_blueprint_dict()
    bp = ArchitectureBlueprint.model_validate(raw)
    report = analyze_sensitivity(bp)
    assert report.challenger_option_id is None
    assert report.breakeven_direction == "single_option"
    assert "only one option declared" in render_sensitivity_markdown(report)


def test_report_formats_blueprint_block_without_zero_high_zero_warn() -> None:
    raw = sample_blueprint_dict()
    raw["controls"]["egress_restricted"] = False
    bp = ArchitectureBlueprint.model_validate(raw)
    econ = evaluate_blueprint(bp)
    findings = validate_blueprint(bp)

    assert recommend_option(econ, findings) is None
    md = render_markdown(bp, econ, findings)
    assert "BLOCKED (0 high, 0 warn)" not in md
    assert "BLOCKED (blueprint gate)" in md
    assert "blueprint-level security" in md

    payload = json.loads(render_json(bp, econ, findings))
    assert payload["recommended_option_id"] is None
    assert payload["findings"][0]["rule_id"] == "ARCH-SEC-002"
    assert payload["findings"][0]["option_id"] is None


def test_report_formats_blueprint_warning_and_all_blocked_options() -> None:
    raw = sample_blueprint_dict()
    raw["controls"]["eval_gate_enabled"] = False
    bp = ArchitectureBlueprint.model_validate(raw)
    md = render_markdown(bp, evaluate_blueprint(bp), validate_blueprint(bp))
    assert "PASS (1 blueprint warn)" in md

    raw_blocked = sample_blueprint_dict()
    raw_blocked["models"][0]["zero_data_retention"] = False
    bp_blocked = ArchitectureBlueprint.model_validate(raw_blocked)
    econ = evaluate_blueprint(bp_blocked)
    findings = validate_blueprint(bp_blocked)
    assert recommend_option(econ, findings) is None
    assert "BLOCKED (1 high, 0 warn)" in render_markdown(bp_blocked, econ, findings)
