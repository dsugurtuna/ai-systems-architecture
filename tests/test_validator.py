"""Unit tests covering every deterministic sovereignty, security, latency, and ROI rule."""

from __future__ import annotations

from ai_systems_arch.schema import ArchitectureBlueprint
from ai_systems_arch.validator import validate_blueprint
from tests.conftest import sample_blueprint_dict


def _rule_ids(raw: dict[str, object]) -> set[str]:
    bp = ArchitectureBlueprint.model_validate(raw)
    return {f.rule_id for f in validate_blueprint(bp)}


def test_baseline_passes_all_gates() -> None:
    assert _rule_ids(sample_blueprint_dict()) == set()


def test_arch_sov_001_blocks_hosted_api_on_restricted_sovereign() -> None:
    raw = sample_blueprint_dict()
    raw["workload"]["data_sensitivity"] = "restricted_sovereign"
    raw["models"][0]["deployment_mode"] = "hosted_api"
    assert "ARCH-SOV-001" in _rule_ids(raw)


def test_arch_sov_002_requires_self_hosted_for_air_gapped() -> None:
    raw = sample_blueprint_dict()
    raw["workload"]["residency"] = "air_gapped"
    raw["models"][0]["residency_supported"].append("air_gapped")
    assert "ARCH-SOV-002" in _rule_ids(raw)


def test_arch_res_001_flags_unsupported_residency_even_on_fallback() -> None:
    raw = sample_blueprint_dict()
    raw["workload"]["residency"] = "sovereign_vpc"
    raw["models"][1]["residency_supported"] = ["uk_eu"]
    assert "ARCH-RES-001" in _rule_ids(raw)


def test_arch_ret_001_requires_zero_data_retention_for_confidential() -> None:
    raw = sample_blueprint_dict()
    raw["models"][0]["zero_data_retention"] = False
    assert "ARCH-RET-001" in _rule_ids(raw)


def test_arch_lat_001_flags_sla_breach() -> None:
    raw = sample_blueprint_dict()
    raw["workload"]["p95_latency_sla_ms"] = 1_000
    assert "ARCH-LAT-001" in _rule_ids(raw)


def test_arch_rel_001_flags_missing_fallback_at_scale() -> None:
    raw = sample_blueprint_dict()
    del raw["options"][0]["fallback_model"]
    assert "ARCH-REL-001" in _rule_ids(raw)


def test_arch_sec_001_flags_missing_guardrails_or_kill_switch_for_writes() -> None:
    raw = sample_blueprint_dict()
    raw["workload"]["action_profile"] = "writes_with_approval"
    raw["controls"]["kill_switch_enabled"] = False
    assert "ARCH-SEC-001" in _rule_ids(raw)


def test_arch_sec_002_flags_missing_egress_or_audit_for_sensitive_data() -> None:
    raw = sample_blueprint_dict()
    raw["controls"]["egress_restricted"] = False
    assert "ARCH-SEC-002" in _rule_ids(raw)


def test_arch_eval_001_warns_when_eval_gate_disabled() -> None:
    raw = sample_blueprint_dict()
    raw["controls"]["eval_gate_enabled"] = False
    assert "ARCH-EVAL-001" in _rule_ids(raw)


def test_arch_eco_001_warns_on_negative_net_savings() -> None:
    raw = sample_blueprint_dict()
    raw["workload"]["baseline_cost_per_task_gbp"] = 0.01
    assert "ARCH-ECO-001" in _rule_ids(raw)
