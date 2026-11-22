"""Shared fixtures and helpers for ai-systems-architecture tests."""

from __future__ import annotations

from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
EXAMPLES = ROOT / "examples"


def sample_blueprint_dict(**overrides: Any) -> dict[str, Any]:
    """Return a valid baseline blueprint dict for concise rule testing."""
    data: dict[str, Any] = {
        "schema_version": "1.0",
        "workload": {
            "id": "wl-test",
            "title": "Test Workload",
            "domain": "Enterprise Operations",
            "monthly_requests": 20_000,
            "avg_input_tokens": 2_000,
            "avg_output_tokens": 500,
            "data_sensitivity": "confidential",
            "residency": "uk_eu",
            "action_profile": "draft_only",
            "p95_latency_sla_ms": 3_000,
            "human_review_rate": 0.10,
            "review_minutes_per_item": 2.0,
            "reviewer_hourly_gbp": 60.0,
            "rework_cost_per_error_gbp": 100.0,
            "baseline_cost_per_task_gbp": 1.00,
        },
        "models": [
            {
                "id": "m-primary",
                "label": "UK Private Primary",
                "deployment_mode": "private_cloud_endpoint",
                "residency_supported": ["uk_eu", "sovereign_vpc"],
                "zero_data_retention": True,
                "input_gbp_per_1m_tokens": 2.0,
                "output_gbp_per_1m_tokens": 8.0,
                "cache_hit_discount": 0.5,
                "fixed_monthly_infra_gbp": 500.0,
                "p95_latency_ms": 1_200,
                "escaped_error_rate": 0.005,
                "supports_tool_calling": True,
            },
            {
                "id": "m-fallback",
                "label": "Self-Hosted Fallback",
                "deployment_mode": "self_hosted_open_weights",
                "residency_supported": ["uk_eu", "sovereign_vpc", "air_gapped"],
                "zero_data_retention": True,
                "input_gbp_per_1m_tokens": 0.2,
                "output_gbp_per_1m_tokens": 0.5,
                "cache_hit_discount": 0.4,
                "fixed_monthly_infra_gbp": 1_000.0,
                "p95_latency_ms": 800,
                "escaped_error_rate": 0.01,
                "supports_tool_calling": True,
            },
        ],
        "options": [
            {
                "id": "opt-main",
                "name": "Primary with Fallback",
                "primary_model": "m-primary",
                "fallback_model": "m-fallback",
                "cache_hit_rate": 0.4,
            }
        ],
        "controls": {
            "egress_restricted": True,
            "audit_log_enabled": True,
            "runtime_guardrails": True,
            "eval_gate_enabled": True,
            "kill_switch_enabled": True,
        },
    }
    for k, v in overrides.items():
        data[k] = v
    return data
