"""Deterministic architecture, sovereignty, security, and ROI gates."""

from __future__ import annotations

from dataclasses import dataclass

from .economics import OptionEconomics, evaluate_option
from .schema import (
    ActionProfile,
    ArchitectureBlueprint,
    DataSensitivity,
    DeploymentMode,
    ModelProfile,
    ResidencyRequirement,
    RoutingOption,
    Severity,
)


@dataclass(frozen=True)
class Finding:
    """One architectural or sovereignty gate finding."""

    rule_id: str
    severity: Severity
    title: str
    detail: str
    option_id: str | None = None


def _option_models(blueprint: ArchitectureBlueprint, option: RoutingOption) -> list[ModelProfile]:
    models = blueprint.model_map()
    seen: dict[str, ModelProfile] = {option.primary_model: models[option.primary_model]}
    for ref in (option.escalation_model, option.fallback_model):
        if ref is not None and ref not in seen:
            seen[ref] = models[ref]
    return list(seen.values())


def _validate_blueprint_controls(blueprint: ArchitectureBlueprint) -> list[Finding]:
    findings: list[Finding] = []
    w = blueprint.workload
    c = blueprint.controls

    if w.action_profile in (ActionProfile.WRITES_WITH_APPROVAL, ActionProfile.AUTONOMOUS) and (
        not c.runtime_guardrails or not c.kill_switch_enabled
    ):
        missing = [
            name
            for name, flag in (
                ("runtime_guardrails", c.runtime_guardrails),
                ("kill_switch_enabled", c.kill_switch_enabled),
            )
            if not flag
        ]
        findings.append(
            Finding(
                rule_id="ARCH-SEC-001",
                severity=Severity.HIGH,
                title="State-changing workload lacks runtime guardrails or kill switch",
                detail=(
                    f"Action profile '{w.action_profile.value}' requires both runtime_guardrails "
                    f"and kill_switch_enabled; missing: {', '.join(missing)}."
                ),
            )
        )

    if w.data_sensitivity in (
        DataSensitivity.CONFIDENTIAL,
        DataSensitivity.RESTRICTED_SOVEREIGN,
    ) and (not c.egress_restricted or not c.audit_log_enabled):
        missing = [
            name
            for name, flag in (
                ("egress_restricted", c.egress_restricted),
                ("audit_log_enabled", c.audit_log_enabled),
            )
            if not flag
        ]
        findings.append(
            Finding(
                rule_id="ARCH-SEC-002",
                severity=Severity.HIGH,
                title="Sensitive workload lacks egress controls or tamper-evident audit logging",
                detail=(
                    f"Sensitivity '{w.data_sensitivity.value}' requires egress_restricted and "
                    f"audit_log_enabled; missing: {', '.join(missing)}."
                ),
            )
        )

    if not c.eval_gate_enabled:
        findings.append(
            Finding(
                rule_id="ARCH-EVAL-001",
                severity=Severity.WARNING,
                title="No pre-release evaluation gate configured",
                detail="Enable eval_gate_enabled before promoting model or prompt changes.",
            )
        )

    return findings


def _validate_option(
    blueprint: ArchitectureBlueprint,
    option: RoutingOption,
    econ: OptionEconomics,
) -> list[Finding]:
    findings: list[Finding] = []
    w = blueprint.workload
    participating = _option_models(blueprint, option)

    # ARCH-SOV-001: restricted_sovereign data or air_gapped residency routed to hosted_api
    if w.data_sensitivity == DataSensitivity.RESTRICTED_SOVEREIGN or (
        w.residency == ResidencyRequirement.AIR_GAPPED
    ):
        hosted = [m.id for m in participating if m.deployment_mode == DeploymentMode.HOSTED_API]
        if hosted:
            findings.append(
                Finding(
                    rule_id="ARCH-SOV-001",
                    severity=Severity.HIGH,
                    option_id=option.id,
                    title="Sovereign or air-gapped workload routed via public hosted API",
                    detail=(
                        f"Option '{option.id}' includes hosted_api model(s) {', '.join(hosted)}, "
                        "violating sovereign/air-gapped isolation."
                    ),
                )
            )

    # ARCH-SOV-002: air_gapped workload requires self_hosted_open_weights
    if w.residency == ResidencyRequirement.AIR_GAPPED:
        non_self = [
            m.id
            for m in participating
            if m.deployment_mode != DeploymentMode.SELF_HOSTED_OPEN_WEIGHTS
        ]
        if non_self:
            findings.append(
                Finding(
                    rule_id="ARCH-SOV-002",
                    severity=Severity.HIGH,
                    option_id=option.id,
                    title="Air-gapped workload requires self-hosted open-weights deployment",
                    detail=(
                        f"Option '{option.id}' includes external model(s) {', '.join(non_self)} "
                        "that cannot operate inside an air-gapped perimeter."
                    ),
                )
            )

    # ARCH-RES-001: residency support check
    if w.residency != ResidencyRequirement.ANY:
        unsupported = [m.id for m in participating if w.residency not in m.residency_supported]
        if unsupported:
            findings.append(
                Finding(
                    rule_id="ARCH-RES-001",
                    severity=Severity.HIGH,
                    option_id=option.id,
                    title="Model residency does not satisfy workload residency requirement",
                    detail=(
                        f"Required residency '{w.residency.value}' is not supported by model(s): "
                        f"{', '.join(unsupported)}."
                    ),
                )
            )

    # ARCH-RET-001: zero data retention for confidential / restricted_sovereign
    if w.data_sensitivity in (
        DataSensitivity.CONFIDENTIAL,
        DataSensitivity.RESTRICTED_SOVEREIGN,
    ):
        non_zdr = [m.id for m in participating if not m.zero_data_retention]
        if non_zdr:
            findings.append(
                Finding(
                    rule_id="ARCH-RET-001",
                    severity=Severity.HIGH,
                    option_id=option.id,
                    title="Sensitive workload routed to model without zero data retention",
                    detail=(
                        f"Sensitivity '{w.data_sensitivity.value}' requires "
                        f"zero_data_retention=true; not guaranteed on: {', '.join(non_zdr)}."
                    ),
                )
            )

    # ARCH-LAT-001: p95 latency SLA
    if econ.p95_latency_ms > w.p95_latency_sla_ms:
        findings.append(
            Finding(
                rule_id="ARCH-LAT-001",
                severity=Severity.WARNING,
                option_id=option.id,
                title="Estimated p95 latency exceeds workload SLA",
                detail=(
                    f"Option '{option.id}' p95 latency is {econ.p95_latency_ms} ms, "
                    f"exceeding SLA of {w.p95_latency_sla_ms} ms."
                ),
            )
        )

    # ARCH-REL-001: fallback required on high-volume or sovereign workloads
    if (
        w.monthly_requests >= 10_000 or w.data_sensitivity == DataSensitivity.RESTRICTED_SOVEREIGN
    ) and option.fallback_model is None:
        findings.append(
            Finding(
                rule_id="ARCH-REL-001",
                severity=Severity.WARNING,
                option_id=option.id,
                title="No fallback model configured for high-volume or sovereign workload",
                detail=(
                    f"Option '{option.id}' has no fallback_model; single-provider or "
                    "single-cluster outages will interrupt service."
                ),
            )
        )

    # ARCH-ECO-001: negative net monthly savings
    if econ.net_monthly_savings_gbp < 0.0:
        findings.append(
            Finding(
                rule_id="ARCH-ECO-001",
                severity=Severity.WARNING,
                option_id=option.id,
                title="Negative net ROI once human verification and rework are priced",
                detail=(
                    f"Option '{option.id}' totals GBP {econ.total_monthly_gbp:,.2f}/mo vs baseline "
                    f"GBP {econ.baseline_monthly_gbp:,.2f}/mo "
                    f"(net GBP {econ.net_monthly_savings_gbp:,.2f}/mo)."
                ),
            )
        )

    return findings


def validate_blueprint(blueprint: ArchitectureBlueprint) -> list[Finding]:
    """Run all deterministic architecture, sovereignty, security, and ROI checks."""
    findings = _validate_blueprint_controls(blueprint)
    for option in blueprint.options:
        econ = evaluate_option(blueprint, option)
        findings.extend(_validate_option(blueprint, option, econ))
    return findings
