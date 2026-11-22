"""Total cost of ownership (TCO), latency, and error economics unit tests."""

from __future__ import annotations

import pytest

from ai_systems_arch.economics import evaluate_blueprint, evaluate_option
from ai_systems_arch.schema import ArchitectureBlueprint
from tests.conftest import sample_blueprint_dict


def test_single_model_economics_exact_math() -> None:
    raw = sample_blueprint_dict()
    # Simplify to single model without fixed infra or fallback for hand-checked calculation
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

    # Input: 10M tokens * 2.0 * (1 - 0.5 * 0.5) = 10 * 1.5 = 15.0
    # Output: 5M tokens * 10.0 = 50.0
    # Fixed infra: 250.0 -> total inference = 315.0
    # Human review: 10_000 * 0.2 * (3/60) * 60 = 6_000.0
    # Rework: 10_000 * 0.01 * 50 = 5_000.0
    # Total = 11_315.0; Baseline = 20_000.0; Savings = 8_685.0
    assert econ.inference_gbp == pytest.approx(315.0)
    assert econ.human_review_gbp == pytest.approx(6_000.0)
    assert econ.rework_gbp == pytest.approx(5_000.0)
    assert econ.total_monthly_gbp == pytest.approx(11_315.0)
    assert econ.net_monthly_savings_gbp == pytest.approx(8_685.0)
    assert econ.p95_latency_ms == 1_000
    assert econ.deployment_summary == "private_cloud_endpoint"


def test_tiered_cascade_blends_cost_error_and_latency() -> None:
    raw = sample_blueprint_dict()
    raw["options"][0].update(
        {
            "escalation_model": "m-fallback",
            "escalation_rate": 0.20,
        }
    )
    bp = ArchitectureBlueprint.model_validate(raw)
    econ = evaluate_blueprint(bp)[0]

    # Sequential cascade latency adds primary (1200) + escalation (800) when rate >= 5%
    assert econ.p95_latency_ms == 2_000
    # Blended error: 0.8 * 0.005 + 0.2 * 0.01 = 0.006
    assert econ.blended_error_rate == pytest.approx(0.006)
    assert "->" in econ.deployment_summary
