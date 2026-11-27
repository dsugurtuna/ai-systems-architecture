"""Unit tests covering every deterministic sovereignty, capability, security, and ROI rule."""

from __future__ import annotations

from ai_systems_arch.schema import ArchitectureBlueprint, Severity
from ai_systems_arch.validator import validate_blueprint
from tests.conftest import sample_blueprint_dict


def _findings_tuples(raw: dict[str, object]) -> set[tuple[str, Severity, str | None]]:
    bp = ArchitectureBlueprint.model_validate(raw)
    return {(f.rule_id, f.severity, f.option_id) for f in validate_blueprint(bp)}


def test_baseline_passes_all_gates() -> None:
    assert _findings_tuples(sample_blueprint_dict()) == set()


def test_arch_sov_001_blocks_hosted_api_on_restricted_sovereign_and_confidential() -> None:
    for sensitivity in ("restricted_sovereign", "confidential"):
        raw = sample_blueprint_dict()
        raw["workload"]["data_sensitivity"] = sensitivity
        raw["models"][0]["deployment_mode"] = "hosted_api"
        assert ("ARCH-SOV-001", Severity.HIGH, "opt-main") in _findings_tuples(raw)


def test_arch_sov_001_permits_hosted_api_on_public_and_internal_with_zdr() -> None:
    for sensitivity in ("public", "internal"):
        raw = sample_blueprint_dict()
        raw["workload"]["data_sensitivity"] = sensitivity
        raw["workload"]["residency"] = "any"
        raw["models"][0]["deployment_mode"] = "hosted_api"
        raw["models"][0]["zero_data_retention"] = True
        tuples = _findings_tuples(raw)
        assert not any(rule == "ARCH-SOV-001" for rule, _, _ in tuples)


def test_arch_sov_001_blocks_hosted_api_on_air_gapped() -> None:
    raw = sample_blueprint_dict()
    raw["workload"]["data_sensitivity"] = "internal"
    raw["workload"]["residency"] = "air_gapped"
    raw["models"][0]["deployment_mode"] = "hosted_api"
    raw["models"][0]["residency_supported"] = ["air_gapped"]
    tuples = _findings_tuples(raw)
    assert ("ARCH-SOV-001", Severity.HIGH, "opt-main") in tuples
    assert ("ARCH-SOV-002", Severity.HIGH, "opt-main") in tuples


def test_arch_sov_002_requires_self_hosted_for_air_gapped() -> None:
    raw = sample_blueprint_dict()
    raw["workload"]["residency"] = "air_gapped"
    raw["models"][0]["residency_supported"].append("air_gapped")
    assert ("ARCH-SOV-002", Severity.HIGH, "opt-main") in _findings_tuples(raw)


def test_arch_res_001_flags_unsupported_residency_even_on_fallback() -> None:
    raw = sample_blueprint_dict()
    raw["workload"]["residency"] = "sovereign_vpc"
    raw["models"][1]["residency_supported"] = ["uk_eu"]
    assert ("ARCH-RES-001", Severity.HIGH, "opt-main") in _findings_tuples(raw)


def test_arch_ret_001_requires_zdr_for_internal_confidential_and_sovereign() -> None:
    for sensitivity in ("internal", "confidential", "restricted_sovereign"):
        raw = sample_blueprint_dict()
        raw["workload"]["data_sensitivity"] = sensitivity
        raw["models"][0]["zero_data_retention"] = False
        assert ("ARCH-RET-001", Severity.HIGH, "opt-main") in _findings_tuples(raw)

    raw_pub = sample_blueprint_dict()
    raw_pub["workload"]["data_sensitivity"] = "public"
    raw_pub["models"][0]["zero_data_retention"] = False
    assert not any(rule == "ARCH-RET-001" for rule, _, _ in _findings_tuples(raw_pub))


def test_arch_cap_001_enforces_tool_calling_for_state_changing_profiles() -> None:
    for profile in ("writes_with_approval", "autonomous"):
        raw = sample_blueprint_dict()
        raw["workload"]["action_profile"] = profile
        raw["models"][1]["supports_tool_calling"] = False
        assert ("ARCH-CAP-001", Severity.HIGH, "opt-main") in _findings_tuples(raw)

    raw_draft = sample_blueprint_dict()
    raw_draft["workload"]["action_profile"] = "draft_only"
    raw_draft["models"][1]["supports_tool_calling"] = False
    assert not any(rule == "ARCH-CAP-001" for rule, _, _ in _findings_tuples(raw_draft))


def test_arch_cap_002_warns_when_routed_tokens_exceed_capacity() -> None:
    raw = sample_blueprint_dict()
    # 20,000 req * 2,500 tokens = 50,000,000 tokens/mo
    raw["models"][0]["max_monthly_tokens"] = 49_999_999
    assert ("ARCH-CAP-002", Severity.WARNING, "opt-main") in _findings_tuples(raw)

    raw["models"][0]["max_monthly_tokens"] = 50_000_000
    assert not any(rule == "ARCH-CAP-002" for rule, _, _ in _findings_tuples(raw))


def test_arch_lat_001_flags_sla_breach() -> None:
    raw = sample_blueprint_dict()
    raw["workload"]["p95_latency_sla_ms"] = 1_000
    assert ("ARCH-LAT-001", Severity.WARNING, "opt-main") in _findings_tuples(raw)


def test_arch_rel_001_boundary_and_sovereign_fallback() -> None:
    raw_below = sample_blueprint_dict()
    raw_below["workload"]["monthly_requests"] = 9_999
    del raw_below["options"][0]["fallback_model"]
    assert not any(rule == "ARCH-REL-001" for rule, _, _ in _findings_tuples(raw_below))

    raw_at = sample_blueprint_dict()
    raw_at["workload"]["monthly_requests"] = 10_000
    del raw_at["options"][0]["fallback_model"]
    assert ("ARCH-REL-001", Severity.WARNING, "opt-main") in _findings_tuples(raw_at)

    raw_sov = sample_blueprint_dict()
    raw_sov["workload"]["monthly_requests"] = 100
    raw_sov["workload"]["data_sensitivity"] = "restricted_sovereign"
    del raw_sov["options"][0]["fallback_model"]
    assert ("ARCH-REL-001", Severity.WARNING, "opt-main") in _findings_tuples(raw_sov)


def test_arch_sec_001_flags_missing_guardrails_or_kill_switch_for_writes_and_autonomous() -> None:
    for profile, control in (
        ("writes_with_approval", "kill_switch_enabled"),
        ("autonomous", "runtime_guardrails"),
    ):
        raw = sample_blueprint_dict()
        raw["workload"]["action_profile"] = profile
        raw["controls"][control] = False
        assert ("ARCH-SEC-001", Severity.HIGH, None) in _findings_tuples(raw)


def test_arch_sec_002_flags_missing_egress_or_audit_for_sensitive_data() -> None:
    for control in ("egress_restricted", "audit_log_enabled"):
        raw = sample_blueprint_dict()
        raw["controls"][control] = False
        assert ("ARCH-SEC-002", Severity.HIGH, None) in _findings_tuples(raw)


def test_arch_sec_003_flags_explicitly_disabled_platform_boundary_and_provenance() -> None:
    raw = sample_blueprint_dict()
    raw["controls"]["cmk_encryption"] = False
    assert ("ARCH-SEC-003", Severity.HIGH, None) in _findings_tuples(raw)

    raw2 = sample_blueprint_dict()
    raw2["controls"]["signed_artifact_provenance"] = False
    assert ("ARCH-SEC-003", Severity.HIGH, "opt-main") in _findings_tuples(raw2)


def test_arch_eval_001_warns_when_eval_gate_disabled() -> None:
    raw = sample_blueprint_dict()
    raw["controls"]["eval_gate_enabled"] = False
    assert ("ARCH-EVAL-001", Severity.WARNING, None) in _findings_tuples(raw)


def test_arch_eco_001_warns_on_negative_net_savings() -> None:
    raw = sample_blueprint_dict()
    raw["workload"]["baseline_cost_per_task_gbp"] = 0.01
    assert ("ARCH-ECO-001", Severity.WARNING, "opt-main") in _findings_tuples(raw)
