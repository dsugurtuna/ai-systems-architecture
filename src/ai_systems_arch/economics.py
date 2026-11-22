"""Total-cost-of-ownership (TCO), latency, and error economics for routing options.

All numbers are deterministic calculations over the declared blueprint parameters.
Pricing and error rates reflect transparent workload assumptions, not live provider quotes.
"""

from __future__ import annotations

from dataclasses import dataclass

from .schema import ArchitectureBlueprint, ModelProfile, RoutingOption


@dataclass(frozen=True)
class OptionEconomics:
    """Computed monthly economics and quality profile for one routing option."""

    option_id: str
    option_name: str
    deployment_summary: str
    inference_gbp: float
    human_review_gbp: float
    rework_gbp: float
    total_monthly_gbp: float
    baseline_monthly_gbp: float
    net_monthly_savings_gbp: float
    cost_per_task_gbp: float
    p95_latency_ms: int
    blended_error_rate: float
    inference_share_pct: float
    human_effort_share_pct: float


def _tier_token_cost_gbp(
    model: ModelProfile,
    monthly_requests: int,
    avg_input_tokens: int,
    avg_output_tokens: int,
    request_share: float,
    cache_hit_rate: float,
) -> float:
    scaled_requests = monthly_requests * request_share
    effective_input_price = model.input_gbp_per_1m_tokens * (
        1.0 - cache_hit_rate * model.cache_hit_discount
    )
    input_cost = (scaled_requests * avg_input_tokens / 1_000_000.0) * effective_input_price
    output_cost = (
        scaled_requests * avg_output_tokens / 1_000_000.0
    ) * model.output_gbp_per_1m_tokens
    return input_cost + output_cost


def evaluate_option(blueprint: ArchitectureBlueprint, option: RoutingOption) -> OptionEconomics:
    """Evaluate monthly inference, human checking, rework, latency, and net savings."""
    models = blueprint.model_map()
    w = blueprint.workload
    primary = models[option.primary_model]
    escalation = models[option.escalation_model] if option.escalation_model else None

    primary_share = 1.0 - option.escalation_rate
    token_cost = _tier_token_cost_gbp(
        primary,
        w.monthly_requests,
        w.avg_input_tokens,
        w.avg_output_tokens,
        primary_share,
        option.cache_hit_rate,
    )
    if escalation is not None:
        token_cost += _tier_token_cost_gbp(
            escalation,
            w.monthly_requests,
            w.avg_input_tokens,
            w.avg_output_tokens,
            option.escalation_rate,
            option.cache_hit_rate,
        )

    active_models: dict[str, ModelProfile] = {primary.id: primary}
    if escalation is not None:
        active_models[escalation.id] = escalation
    if option.fallback_model is not None:
        fb = models[option.fallback_model]
        active_models[fb.id] = fb

    fixed_infra = sum(m.fixed_monthly_infra_gbp for m in active_models.values())
    inference_gbp = token_cost + fixed_infra

    if escalation is not None and option.escalation_rate >= 0.05:
        p95_latency_ms = primary.p95_latency_ms + escalation.p95_latency_ms
    else:
        p95_latency_ms = primary.p95_latency_ms

    blended_error_rate = primary_share * primary.escaped_error_rate + (
        option.escalation_rate * escalation.escaped_error_rate if escalation is not None else 0.0
    )

    human_review_gbp = (
        w.monthly_requests
        * w.human_review_rate
        * (w.review_minutes_per_item / 60.0)
        * w.reviewer_hourly_gbp
    )
    rework_gbp = w.monthly_requests * blended_error_rate * w.rework_cost_per_error_gbp
    total_monthly_gbp = inference_gbp + human_review_gbp + rework_gbp

    baseline_monthly_gbp = w.monthly_requests * w.baseline_cost_per_task_gbp
    net_monthly_savings_gbp = baseline_monthly_gbp - total_monthly_gbp
    cost_per_task_gbp = total_monthly_gbp / w.monthly_requests

    if total_monthly_gbp > 0.0:
        inference_share_pct = (inference_gbp / total_monthly_gbp) * 100.0
        human_effort_share_pct = ((human_review_gbp + rework_gbp) / total_monthly_gbp) * 100.0
    else:
        inference_share_pct = 0.0
        human_effort_share_pct = 0.0

    if escalation is None:
        deployment_summary = primary.deployment_mode.value
    elif primary.deployment_mode == escalation.deployment_mode:
        deployment_summary = f"{primary.deployment_mode.value} (tiered)"
    else:
        deployment_summary = (
            f"{primary.deployment_mode.value} -> {escalation.deployment_mode.value}"
        )

    return OptionEconomics(
        option_id=option.id,
        option_name=option.name,
        deployment_summary=deployment_summary,
        inference_gbp=round(inference_gbp, 2),
        human_review_gbp=round(human_review_gbp, 2),
        rework_gbp=round(rework_gbp, 2),
        total_monthly_gbp=round(total_monthly_gbp, 2),
        baseline_monthly_gbp=round(baseline_monthly_gbp, 2),
        net_monthly_savings_gbp=round(net_monthly_savings_gbp, 2),
        cost_per_task_gbp=round(cost_per_task_gbp, 4),
        p95_latency_ms=p95_latency_ms,
        blended_error_rate=round(blended_error_rate, 6),
        inference_share_pct=round(inference_share_pct, 1),
        human_effort_share_pct=round(human_effort_share_pct, 1),
    )


def evaluate_blueprint(blueprint: ArchitectureBlueprint) -> list[OptionEconomics]:
    """Compute economics for every routing option declared in a blueprint."""
    return [evaluate_option(blueprint, option) for option in blueprint.options]
