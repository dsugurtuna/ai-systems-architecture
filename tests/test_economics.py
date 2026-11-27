"""Total cost of ownership (TCO), latency, standby, and review economics unit tests."""

from __future__ import annotations

import pytest

from ai_systems_arch.economics import (
    evaluate_blueprint,
    evaluate_option,
    option_routed_tokens,
)
from ai_systems_arch.schema import ArchitectureBlueprint
from tests.conftest import sample_blueprint_dict


def test_single_model_economics_exact_math_with_ops() -> None:
    raw = sample_blueprint_dict()
    raw["models"] = [
        {
            "id": "m1",
            "label": "M1",
            "deployment_mode": "private_cloud_endpoint",
            "residency_supported": ["uk_eu"],
            "zero_data_retention": True,
            "input_gbp_per_1m_tokens": 2.0,
            "output_gbp_per_1m_tokens": 10.0,
            "cache_hit_discount": 0.5,
            "fixed_monthly_infra_gbp": 250.0,
            "ops_monthly_gbp": 100.0,
            "p95_latency_ms": 1_000,
            "escaped_error_rate": 0.01,
        }
    ]
    raw["workload"].update(
        {
            "monthly_requests": 10_000,
            "avg_input_tokens": 1_000,
            "avg_output_tokens": 500,
            "human_review_rate": 0.2,
            "review_minutes_per_item": 3.0,
            "reviewer_hourly_gbp": 60.0,
            "rework_cost_per_error_gbp": 50.0,
            "baseline_cost_per_task_gbp": 2.0,
        }
    )
    raw["options"] = [
        {
            "id": "opt1",
            "name": "Opt1",
            "primary_model": "m1",
            "cache_hit_rate": 0.5,
        }
    ]
    bp = ArchitectureBlueprint.model_validate(raw)
    econ = evaluate_option(bp, bp.options[0])

    # Input: 10M tokens * 2.0 * (1 - 0.5 * 0.5) = 15.0
    # Output: 5M tokens * 10.0 = 50.0 -> token_cost = 65.0
    # Fixed (250.0) + Ops (100.0) = 350.0 -> total inference = 415.0
    # Human review: 10_000 * 0.2 * (3/60) * 60 = 6_000.0
    # Rework: 10_000 * 0.01 * 50 = 5_000.0
    # Total = 11_415.0; Baseline = 20_000.0; Savings = 8_585.0
    assert econ.token_cost_gbp == pytest.approx(65.0)
    assert econ.fixed_and_ops_gbp == pytest.approx(350.0)
    assert econ.standby_infra_gbp == pytest.approx(0.0)
    assert econ.inference_gbp == pytest.approx(415.0)
    assert econ.human_review_gbp == pytest.approx(6_000.0)
    assert econ.rework_gbp == pytest.approx(5_000.0)
    assert econ.total_monthly_gbp == pytest.approx(11_415.0)
    assert econ.net_monthly_savings_gbp == pytest.approx(8_585.0)
    assert econ.p95_latency_ms == 1_000
    assert econ.deployment_summary == "private_cloud_endpoint"
    assert econ.routing_mode == "single"


def test_fallback_charges_standby_only_not_active_fixed_infra() -> None:
    raw = sample_blueprint_dict()
    # m-fallback has fixed_monthly_infra_gbp=1000.0; default standby_monthly_infra_gbp=0.0
    bp_zero = ArchitectureBlueprint.model_validate(raw)
    econ_zero = evaluate_option(bp_zero, bp_zero.options[0])
    assert econ_zero.standby_infra_gbp == pytest.approx(0.0)
    assert econ_zero.fixed_and_ops_gbp == pytest.approx(500.0)

    raw_standby = sample_blueprint_dict()
    raw_standby["models"][1]["standby_monthly_infra_gbp"] = 200.0
    bp_standby = ArchitectureBlueprint.model_validate(raw_standby)
    econ_standby = evaluate_option(bp_standby, bp_standby.options[0])
    assert econ_standby.standby_infra_gbp == pytest.approx(200.0)
    assert econ_standby.inference_gbp == pytest.approx(econ_zero.inference_gbp + 200.0)


def test_sequential_cascade_vs_pre_router_token_and_latency_accounting() -> None:
    raw_seq = sample_blueprint_dict()
    raw_seq["options"][0].update(
        {
            "escalation_model": "m-fallback",
            "escalation_rate": 0.20,
            "routing_mode": "sequential_cascade",
        }
    )
    bp_seq = ArchitectureBlueprint.model_validate(raw_seq)
    econ_seq = evaluate_blueprint(bp_seq)[0]

    # Primary executes 100% (40M in * 2.0 * 0.8 + 10M out * 8.0 = 64 + 80 = 144.0)
    # Escalation executes 20% (8M in * 0.2 * 0.84 + 2M out * 0.5 = 1.344 + 1.0 = 2.344)
    # Active fixed: 500 + 1000 = 1500.0 -> total inference = 1646.344
    assert econ_seq.token_cost_gbp == pytest.approx(146.34, abs=0.01)
    assert econ_seq.inference_gbp == pytest.approx(1_646.34, abs=0.01)
    assert econ_seq.blended_error_rate == pytest.approx(0.006)
    assert econ_seq.routing_mode == "sequential_cascade"
    assert "->" in econ_seq.deployment_summary
    assert option_routed_tokens(bp_seq, bp_seq.options[0]) == {
        "m-primary": 50_000_000,
        "m-fallback": 10_000_000,
    }

    raw_pre = sample_blueprint_dict()
    raw_pre["options"][0].update(
        {
            "escalation_model": "m-fallback",
            "escalation_rate": 0.20,
            "routing_mode": "pre_router",
        }
    )
    bp_pre = ArchitectureBlueprint.model_validate(raw_pre)
    econ_pre = evaluate_blueprint(bp_pre)[0]

    # Pre-router skips 20% of primary tokens: 0.8 * 144.0 + 2.344 = 117.544
    assert econ_pre.token_cost_gbp == pytest.approx(117.54, abs=0.01)
    assert econ_pre.inference_gbp == pytest.approx(1_617.54, abs=0.01)
    assert econ_pre.blended_error_rate == pytest.approx(0.006)
    assert econ_pre.p95_latency_ms < econ_seq.p95_latency_ms
    assert option_routed_tokens(bp_pre, bp_pre.options[0]) == {
        "m-primary": 40_000_000,
        "m-fallback": 10_000_000,
    }


def test_p95_latency_is_smooth_across_five_percent_threshold() -> None:
    latencies: list[int] = []
    for rate in (0.01, 0.049, 0.050, 0.051, 0.20, 0.50, 1.0):
        raw = sample_blueprint_dict()
        raw["options"][0].update(
            {
                "escalation_model": "m-fallback",
                "escalation_rate": rate,
                "routing_mode": "sequential_cascade",
            }
        )
        bp = ArchitectureBlueprint.model_validate(raw)
        latencies.append(evaluate_option(bp, bp.options[0]).p95_latency_ms)

    # Monotonically non-decreasing, smooth across 0.049 -> 0.050 (no >20ms step cliff)
    assert latencies == sorted(latencies)
    assert abs(latencies[2] - latencies[1]) <= 20
    assert latencies[-1] == 2_000


def test_model_aware_human_review_multiplier_and_overrides() -> None:
    raw_base = sample_blueprint_dict()
    bp_base = ArchitectureBlueprint.model_validate(raw_base)
    econ_base = evaluate_option(bp_base, bp_base.options[0])
    # Baseline: 20_000 * 0.10 * (2/60) * 60 = 4_000.0
    assert econ_base.human_review_gbp == pytest.approx(4_000.0)

    raw_mult = sample_blueprint_dict()
    raw_mult["models"][0]["review_rate_multiplier"] = 1.5
    raw_mult["models"][0]["review_minutes_per_item"] = 3.0
    bp_mult = ArchitectureBlueprint.model_validate(raw_mult)
    econ_mult = evaluate_option(bp_mult, bp_mult.options[0])
    # 20_000 * 0.15 * (3/60) * 60 = 9_000.0
    assert econ_mult.human_review_gbp == pytest.approx(9_000.0)

    # Clamped at 1.0 review rate when multiplier exceeds 1.0 / human_review_rate
    raw_clamp = sample_blueprint_dict()
    raw_clamp["models"][0]["review_rate_multiplier"] = 20.0
    bp_clamp = ArchitectureBlueprint.model_validate(raw_clamp)
    econ_clamp = evaluate_option(bp_clamp, bp_clamp.options[0])
    # 20_000 * 1.0 * (2/60) * 60 = 40_000.0
    assert econ_clamp.human_review_gbp == pytest.approx(40_000.0)
