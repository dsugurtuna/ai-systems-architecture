"""Total-cost-of-ownership (TCO), latency, capacity, and error economics for routing options.

All numbers are deterministic calculations over the declared blueprint parameters.
Pricing and error rates reflect transparent workload assumptions, not live provider quotes.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from .schema import ArchitectureBlueprint, ModelProfile, RoutingMode, RoutingOption

_LN_20 = math.log(20.0)
_WEIBULL_SHAPE = 3.0


@dataclass(frozen=True)
class RawOptionCosts:
    """Unrounded float64 cost and latency decomposition for exact sensitivity analysis."""

    option_id: str
    option_name: str
    deployment_summary: str
    routing_mode: str
    token_cost_gbp: float
    fixed_infra_gbp: float
    ops_gbp: float
    standby_infra_gbp: float
    fixed_total_gbp: float
    inference_gbp: float
    human_review_gbp: float
    rework_gbp: float
    total_monthly_gbp: float
    baseline_monthly_gbp: float
    net_monthly_savings_gbp: float
    p95_latency_ms: int
    blended_error_rate: float


@dataclass(frozen=True)
class OptionEconomics:
    """Computed monthly economics and quality profile for one routing option."""

    option_id: str
    option_name: str
    deployment_summary: str
    routing_mode: str
    token_cost_gbp: float
    fixed_and_ops_gbp: float
    standby_infra_gbp: float
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


def _blended_p95_latency_ms(
    primary: ModelProfile,
    escalation: ModelProfile | None,
    escalation_rate: float,
    routing_mode: RoutingMode,
) -> int:
    """Compute smooth p95 tail latency across primary and escalation paths without step cliffs.

    Each path's latency distribution is modelled with a right-skewed Weibull(k=3) CDF whose
    95th percentile equals the path's declared p95 latency, solving the exact mixture quantile
    equation ``(1 - r) * P(X1 > t) + r * P(X2 > t) = 0.05`` via bisection.
    """
    if escalation is None or escalation_rate <= 0.0:
        return primary.p95_latency_ms

    path1_p95 = float(primary.p95_latency_ms)
    if routing_mode == RoutingMode.SEQUENTIAL_CASCADE:
        path2_p95 = float(primary.p95_latency_ms + escalation.p95_latency_ms)
    else:
        path2_p95 = float(escalation.p95_latency_ms)

    if escalation_rate >= 1.0:
        return round(path2_p95)
    if abs(path1_p95 - path2_p95) < 1e-9:
        return round(path1_p95)

    lo = min(path1_p95, path2_p95)
    hi = max(path1_p95, path2_p95)
    for _ in range(80):
        mid = (lo + hi) * 0.5
        tail1 = math.exp(-_LN_20 * (mid / path1_p95) ** _WEIBULL_SHAPE)
        tail2 = math.exp(-_LN_20 * (mid / path2_p95) ** _WEIBULL_SHAPE)
        if (1.0 - escalation_rate) * tail1 + escalation_rate * tail2 > 0.05:
            lo = mid
        else:
            hi = mid
    return round((lo + hi) * 0.5)


def _effective_review_minutes_per_request(
    blueprint: ArchitectureBlueprint,
    option: RoutingOption,
    primary: ModelProfile,
    escalation: ModelProfile | None,
) -> float:
    w = blueprint.workload
    r = option.escalation_rate
    primary_final_share = 1.0 - r

    def _model_review_mins(model: ModelProfile) -> float:
        rate = (
            option.review_rate_override
            if option.review_rate_override is not None
            else min(1.0, w.human_review_rate * model.review_rate_multiplier)
        )
        mins = (
            option.review_minutes_per_item
            if option.review_minutes_per_item is not None
            else (
                model.review_minutes_per_item
                if model.review_minutes_per_item is not None
                else w.review_minutes_per_item
            )
        )
        return rate * mins

    expected_mins = primary_final_share * _model_review_mins(primary)
    if escalation is not None:
        expected_mins += r * _model_review_mins(escalation)
    return expected_mins


def option_routed_tokens(
    blueprint: ArchitectureBlueprint,
    option: RoutingOption,
) -> dict[str, int]:
    """Return monthly input+output tokens executed on each active model for capacity checks."""
    w = blueprint.workload
    tokens_per_req = w.avg_input_tokens + w.avg_output_tokens
    r = option.escalation_rate

    if option.escalation_model is None:
        return {option.primary_model: w.monthly_requests * tokens_per_req}

    primary_exec_share = 1.0 if option.routing_mode == RoutingMode.SEQUENTIAL_CASCADE else (1.0 - r)
    routed: dict[str, int] = {
        option.primary_model: round(w.monthly_requests * primary_exec_share * tokens_per_req),
        option.escalation_model: round(w.monthly_requests * r * tokens_per_req),
    }
    return routed


def compute_raw_option_costs(
    blueprint: ArchitectureBlueprint,
    option: RoutingOption,
) -> RawOptionCosts:
    """Compute exact unrounded monthly economics for one routing option."""
    models = blueprint.model_map()
    w = blueprint.workload
    primary = models[option.primary_model]
    escalation = models[option.escalation_model] if option.escalation_model else None

    r = option.escalation_rate
    primary_final_share = 1.0 - r
    if escalation is None:
        primary_exec_share = 1.0
        routing_mode_label = "single"
    elif option.routing_mode == RoutingMode.SEQUENTIAL_CASCADE:
        primary_exec_share = 1.0
        routing_mode_label = option.routing_mode.value
    else:
        primary_exec_share = 1.0 - r
        routing_mode_label = option.routing_mode.value

    token_cost = _tier_token_cost_gbp(
        primary,
        w.monthly_requests,
        w.avg_input_tokens,
        w.avg_output_tokens,
        primary_exec_share,
        option.cache_hit_rate,
    )
    if escalation is not None:
        token_cost += _tier_token_cost_gbp(
            escalation,
            w.monthly_requests,
            w.avg_input_tokens,
            w.avg_output_tokens,
            r,
            option.cache_hit_rate,
        )

    active_models: dict[str, ModelProfile] = {primary.id: primary}
    if escalation is not None:
        active_models[escalation.id] = escalation

    fixed_infra = sum(m.fixed_monthly_infra_gbp for m in active_models.values())
    ops_cost = sum(m.ops_monthly_gbp for m in active_models.values())

    standby_infra = 0.0
    if option.fallback_model is not None and option.fallback_model not in active_models:
        fb = models[option.fallback_model]
        standby_infra = fb.standby_monthly_infra_gbp

    fixed_total = fixed_infra + ops_cost + standby_infra
    inference_gbp = token_cost + fixed_total

    p95_latency_ms = _blended_p95_latency_ms(
        primary,
        escalation,
        r,
        option.routing_mode,
    )

    blended_error_rate = primary_final_share * primary.escaped_error_rate + (
        r * escalation.escaped_error_rate if escalation is not None else 0.0
    )

    expected_review_mins = _effective_review_minutes_per_request(
        blueprint, option, primary, escalation
    )
    human_review_gbp = w.monthly_requests * (expected_review_mins / 60.0) * w.reviewer_hourly_gbp
    rework_gbp = w.monthly_requests * blended_error_rate * w.rework_cost_per_error_gbp
    total_monthly_gbp = inference_gbp + human_review_gbp + rework_gbp

    baseline_monthly_gbp = w.monthly_requests * w.baseline_cost_per_task_gbp
    net_monthly_savings_gbp = baseline_monthly_gbp - total_monthly_gbp

    if escalation is None:
        deployment_summary = primary.deployment_mode.value
    elif primary.deployment_mode == escalation.deployment_mode:
        deployment_summary = f"{primary.deployment_mode.value} (tiered)"
    else:
        deployment_summary = (
            f"{primary.deployment_mode.value} -> {escalation.deployment_mode.value}"
        )

    return RawOptionCosts(
        option_id=option.id,
        option_name=option.name,
        deployment_summary=deployment_summary,
        routing_mode=routing_mode_label,
        token_cost_gbp=token_cost,
        fixed_infra_gbp=fixed_infra,
        ops_gbp=ops_cost,
        standby_infra_gbp=standby_infra,
        fixed_total_gbp=fixed_total,
        inference_gbp=inference_gbp,
        human_review_gbp=human_review_gbp,
        rework_gbp=rework_gbp,
        total_monthly_gbp=total_monthly_gbp,
        baseline_monthly_gbp=baseline_monthly_gbp,
        net_monthly_savings_gbp=net_monthly_savings_gbp,
        p95_latency_ms=p95_latency_ms,
        blended_error_rate=blended_error_rate,
    )


def evaluate_option(blueprint: ArchitectureBlueprint, option: RoutingOption) -> OptionEconomics:
    """Evaluate monthly inference, human checking, rework, latency, and net savings."""
    raw = compute_raw_option_costs(blueprint, option)
    w = blueprint.workload
    cost_per_task_gbp = raw.total_monthly_gbp / w.monthly_requests

    if raw.total_monthly_gbp > 0.0:
        inference_share_pct = (raw.inference_gbp / raw.total_monthly_gbp) * 100.0
        human_effort_share_pct = (
            (raw.human_review_gbp + raw.rework_gbp) / raw.total_monthly_gbp
        ) * 100.0
    else:
        inference_share_pct = 0.0
        human_effort_share_pct = 0.0

    return OptionEconomics(
        option_id=raw.option_id,
        option_name=raw.option_name,
        deployment_summary=raw.deployment_summary,
        routing_mode=raw.routing_mode,
        token_cost_gbp=round(raw.token_cost_gbp, 2),
        fixed_and_ops_gbp=round(raw.fixed_infra_gbp + raw.ops_gbp, 2),
        standby_infra_gbp=round(raw.standby_infra_gbp, 2),
        inference_gbp=round(raw.inference_gbp, 2),
        human_review_gbp=round(raw.human_review_gbp, 2),
        rework_gbp=round(raw.rework_gbp, 2),
        total_monthly_gbp=round(raw.total_monthly_gbp, 2),
        baseline_monthly_gbp=round(raw.baseline_monthly_gbp, 2),
        net_monthly_savings_gbp=round(raw.net_monthly_savings_gbp, 2),
        cost_per_task_gbp=round(cost_per_task_gbp, 4),
        p95_latency_ms=raw.p95_latency_ms,
        blended_error_rate=round(raw.blended_error_rate, 6),
        inference_share_pct=round(inference_share_pct, 1),
        human_effort_share_pct=round(human_effort_share_pct, 1),
    )


def evaluate_blueprint(blueprint: ArchitectureBlueprint) -> list[OptionEconomics]:
    """Compute economics for every routing option declared in a blueprint."""
    return [evaluate_option(blueprint, option) for option in blueprint.options]
