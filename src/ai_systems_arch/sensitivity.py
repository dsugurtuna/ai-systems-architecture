"""Sensitivity and break-even analysis across volume, error-rate, and rework assumptions."""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import asdict, dataclass

from .economics import (
    RawOptionCosts,
    compute_raw_option_costs,
    evaluate_blueprint,
)
from .report import recommend_option
from .schema import ArchitectureBlueprint, RoutingOption, Severity
from .validator import validate_blueprint


@dataclass(frozen=True)
class VolumePoint:
    """TCO comparison and capacity check at one candidate monthly request volume."""

    monthly_requests: int
    is_current: bool
    is_breakeven: bool
    winner_total_gbp: float
    challenger_total_gbp: float | None
    advantage_gbp: float | None
    recommended_option_id: str | None
    capacity_warning_options: tuple[str, ...]


@dataclass(frozen=True)
class SensitivityReport:
    """Break-even volume, error-rate tipping points, and sweep table between top options."""

    workload_id: str
    workload_title: str
    current_monthly_requests: int
    winner_option_id: str
    winner_option_name: str
    challenger_option_id: str | None
    challenger_option_name: str | None
    winner_blocked: bool
    challenger_blocked: bool
    winner_total_gbp: float
    challenger_total_gbp: float | None
    current_margin_gbp: float | None
    current_margin_pct: float | None
    breakeven_monthly_requests: int | None
    breakeven_direction: str
    max_blended_error_delta: float | None
    tipping_blended_error_rate: float | None
    max_primary_error_delta: float | None
    tipping_primary_error_rate: float | None
    breakeven_rework_cost_gbp: float | None
    volume_sweep: list[VolumePoint]


def _select_comparison_pair(
    blueprint: ArchitectureBlueprint,
    winner_id: str | None,
    challenger_id: str | None,
) -> tuple[RoutingOption, RoutingOption | None, bool, bool]:
    economics = evaluate_blueprint(blueprint)
    findings = validate_blueprint(blueprint)
    opt_by_id = {o.id: o for o in blueprint.options}

    global_high = any(f.option_id is None and f.severity == Severity.HIGH for f in findings)
    if global_high:
        blocked_ids = set(opt_by_id)
    else:
        blocked_ids = {
            f.option_id for f in findings if f.option_id is not None and f.severity == Severity.HIGH
        }

    if winner_id is not None and winner_id not in opt_by_id:
        raise ValueError(f"unknown winner option '{winner_id}'")
    if challenger_id is not None and challenger_id not in opt_by_id:
        raise ValueError(f"unknown challenger option '{challenger_id}'")
    if winner_id is not None and challenger_id is not None and winner_id == challenger_id:
        raise ValueError("winner and challenger options must differ")

    eligible = sorted(
        [e for e in economics if e.option_id not in blocked_ids],
        key=lambda e: e.total_monthly_gbp,
    )
    blocked = sorted(
        [e for e in economics if e.option_id in blocked_ids],
        key=lambda e: e.total_monthly_gbp,
    )
    ordered = eligible + blocked

    winner_opt = opt_by_id[ordered[0].option_id] if winner_id is None else opt_by_id[winner_id]

    if challenger_id is None:
        remaining = [e for e in ordered if e.option_id != winner_opt.id]
        challenger_opt = opt_by_id[remaining[0].option_id] if remaining else None
    else:
        challenger_opt = opt_by_id[challenger_id]

    winner_blocked = winner_opt.id in blocked_ids
    challenger_blocked = challenger_opt.id in blocked_ids if challenger_opt is not None else False
    return winner_opt, challenger_opt, winner_blocked, challenger_blocked


def _variable_cost_per_request(raw: RawOptionCosts, monthly_requests: int) -> float:
    return (raw.total_monthly_gbp - raw.fixed_total_gbp) / monthly_requests


def _compute_breakeven_volume(
    raw_w: RawOptionCosts,
    raw_c: RawOptionCosts,
    monthly_requests: int,
) -> tuple[int | None, str]:
    var_w = _variable_cost_per_request(raw_w, monthly_requests)
    var_c = _variable_cost_per_request(raw_c, monthly_requests)
    slope_diff = var_c - var_w

    if abs(slope_diff) <= 1e-12:
        return None, "none_same_slope"

    n_star = (raw_w.fixed_total_gbp - raw_c.fixed_total_gbp) / slope_diff
    if n_star <= 0.0:
        if raw_w.total_monthly_gbp <= raw_c.total_monthly_gbp:
            return None, "winner_dominates_all_volumes"
        return None, "challenger_dominates_all_volumes"

    direction = "winner_cheaper_above" if slope_diff > 0.0 else "winner_cheaper_below"
    return round(n_star), direction


def _build_volume_sweep(
    blueprint: ArchitectureBlueprint,
    winner_id: str,
    challenger_id: str | None,
    multipliers: Sequence[float],
    breakeven_vol: int | None,
) -> list[VolumePoint]:
    w = blueprint.workload
    candidate_vols = {
        w.monthly_requests,
        *(max(1, round(w.monthly_requests * m)) for m in multipliers),
    }
    if breakeven_vol is not None and breakeven_vol > 0:
        candidate_vols.add(breakeven_vol)

    sweep: list[VolumePoint] = []
    for vol in sorted(candidate_vols):
        bp_v = blueprint.model_copy(
            update={"workload": w.model_copy(update={"monthly_requests": vol})}
        )
        econ_v = evaluate_blueprint(bp_v)
        findings_v = validate_blueprint(bp_v)
        best_v = recommend_option(econ_v, findings_v)
        cap_warn = tuple(
            f.option_id
            for f in findings_v
            if f.rule_id == "ARCH-CAP-002" and f.option_id is not None
        )
        w_tot = next(e.total_monthly_gbp for e in econ_v if e.option_id == winner_id)
        c_tot = (
            next(e.total_monthly_gbp for e in econ_v if e.option_id == challenger_id)
            if challenger_id is not None
            else None
        )
        adv = round(c_tot - w_tot, 2) if c_tot is not None else None
        sweep.append(
            VolumePoint(
                monthly_requests=vol,
                is_current=(vol == w.monthly_requests),
                is_breakeven=(breakeven_vol is not None and vol == breakeven_vol),
                winner_total_gbp=w_tot,
                challenger_total_gbp=c_tot,
                advantage_gbp=adv,
                recommended_option_id=best_v.option_id if best_v else None,
                capacity_warning_options=cap_warn,
            )
        )
    return sweep


def analyze_sensitivity(
    blueprint: ArchitectureBlueprint,
    winner_id: str | None = None,
    challenger_id: str | None = None,
    multipliers: Sequence[float] = (0.25, 0.5, 1.0, 2.0, 5.0),
) -> SensitivityReport:
    """Compute break-even volume, error-rate tipping points, and a volume sweep."""
    w = blueprint.workload
    winner_opt, challenger_opt, winner_blocked, challenger_blocked = _select_comparison_pair(
        blueprint, winner_id, challenger_id
    )

    raw_w = compute_raw_option_costs(blueprint, winner_opt)
    if challenger_opt is None:
        sweep = _build_volume_sweep(blueprint, winner_opt.id, None, multipliers, None)
        return SensitivityReport(
            workload_id=w.id,
            workload_title=w.title,
            current_monthly_requests=w.monthly_requests,
            winner_option_id=winner_opt.id,
            winner_option_name=winner_opt.name,
            challenger_option_id=None,
            challenger_option_name=None,
            winner_blocked=winner_blocked,
            challenger_blocked=False,
            winner_total_gbp=round(raw_w.total_monthly_gbp, 2),
            challenger_total_gbp=None,
            current_margin_gbp=None,
            current_margin_pct=None,
            breakeven_monthly_requests=None,
            breakeven_direction="single_option",
            max_blended_error_delta=None,
            tipping_blended_error_rate=None,
            max_primary_error_delta=None,
            tipping_primary_error_rate=None,
            breakeven_rework_cost_gbp=None,
            volume_sweep=sweep,
        )

    raw_c = compute_raw_option_costs(blueprint, challenger_opt)
    margin = raw_c.total_monthly_gbp - raw_w.total_monthly_gbp
    margin_pct = (
        (margin / raw_c.total_monthly_gbp) * 100.0 if raw_c.total_monthly_gbp > 0.0 else None
    )

    breakeven_vol, direction = _compute_breakeven_volume(raw_w, raw_c, w.monthly_requests)

    max_blended_delta: float | None = None
    tipping_blended: float | None = None
    if w.rework_cost_per_error_gbp > 0.0 and w.monthly_requests > 0:
        max_blended_delta = margin / (w.monthly_requests * w.rework_cost_per_error_gbp)
        candidate = raw_w.blended_error_rate + max_blended_delta
        if 0.0 <= candidate <= 1.0:
            tipping_blended = round(candidate, 6)

    # Sensitivity to winner primary model's escaped_error_rate (handles shared models cleanly)
    models = blueprint.model_map()
    primary_model = models[winner_opt.primary_model]
    slope_w = (1.0 - winner_opt.escalation_rate) * w.monthly_requests * w.rework_cost_per_error_gbp
    if challenger_opt.primary_model == winner_opt.primary_model:
        slope_c = (
            (1.0 - challenger_opt.escalation_rate)
            * w.monthly_requests
            * w.rework_cost_per_error_gbp
        )
    elif challenger_opt.escalation_model == winner_opt.primary_model:
        slope_c = challenger_opt.escalation_rate * w.monthly_requests * w.rework_cost_per_error_gbp
    else:
        slope_c = 0.0

    net_primary_slope = slope_w - slope_c
    max_primary_delta: float | None = None
    tipping_primary: float | None = None
    if abs(net_primary_slope) > 1e-9:
        delta_p = margin / net_primary_slope
        if (net_primary_slope > 0.0 and delta_p >= 0.0) or (
            net_primary_slope < 0.0 and delta_p <= 0.0
        ):
            max_primary_delta = round(delta_p, 6)
            cand_p = primary_model.escaped_error_rate + delta_p
            if 0.0 <= cand_p <= 1.0:
                tipping_primary = round(cand_p, 6)

    err_diff = raw_w.blended_error_rate - raw_c.blended_error_rate
    breakeven_rework: float | None = None
    if abs(err_diff) > 1e-12:
        non_rework_margin = (raw_c.total_monthly_gbp - raw_c.rework_gbp) - (
            raw_w.total_monthly_gbp - raw_w.rework_gbp
        )
        rework_star = non_rework_margin / (w.monthly_requests * err_diff)
        if rework_star > 0.0:
            breakeven_rework = round(rework_star, 2)

    sweep = _build_volume_sweep(
        blueprint, winner_opt.id, challenger_opt.id, multipliers, breakeven_vol
    )

    return SensitivityReport(
        workload_id=w.id,
        workload_title=w.title,
        current_monthly_requests=w.monthly_requests,
        winner_option_id=winner_opt.id,
        winner_option_name=winner_opt.name,
        challenger_option_id=challenger_opt.id,
        challenger_option_name=challenger_opt.name,
        winner_blocked=winner_blocked,
        challenger_blocked=challenger_blocked,
        winner_total_gbp=round(raw_w.total_monthly_gbp, 2),
        challenger_total_gbp=round(raw_c.total_monthly_gbp, 2),
        current_margin_gbp=round(margin, 2),
        current_margin_pct=round(margin_pct, 2) if margin_pct is not None else None,
        breakeven_monthly_requests=breakeven_vol,
        breakeven_direction=direction,
        max_blended_error_delta=(
            round(max_blended_delta, 6) if max_blended_delta is not None else None
        ),
        tipping_blended_error_rate=tipping_blended,
        max_primary_error_delta=max_primary_delta,
        tipping_primary_error_rate=tipping_primary,
        breakeven_rework_cost_gbp=breakeven_rework,
        volume_sweep=sweep,
    )


def render_sensitivity_markdown(report: SensitivityReport) -> str:
    """Render sensitivity and break-even report in Markdown."""
    lines: list[str] = [
        f"# Sensitivity Analysis: {report.workload_title}",
        "",
        f"**Workload:** `{report.workload_id}` | **Current Volume:** {report.current_monthly_requests:,} req/mo",  # noqa: E501
    ]

    if report.challenger_option_id is None:
        lines.extend(
            [
                f"**Option:** `{report.winner_option_id}` (£{report.winner_total_gbp:,.2f}/mo) — "
                "only one option declared; add a challenger option for pairwise break-even.",
                "",
            ]
        )
        return "\n".join(lines)

    margin_pct_str = (
        f" ({report.current_margin_pct:.1f}%)" if report.current_margin_pct is not None else ""
    )
    lines.append(
        f"**Comparison:** `{report.winner_option_id}` (£{report.winner_total_gbp:,.2f}/mo) "
        f"vs `{report.challenger_option_id}` (£{report.challenger_total_gbp:,.2f}/mo) — "
        f"margin **£{report.current_margin_gbp:,.2f}/mo**{margin_pct_str}"
    )
    lines.extend(["", "## Key Tipping Points", ""])

    if report.breakeven_monthly_requests is not None:
        rel = (
            "cheaper above"
            if report.breakeven_direction == "winner_cheaper_above"
            else "cheaper below"
        )
        lines.append(
            f"- **Break-even volume:** **{report.breakeven_monthly_requests:,} req/mo** "
            f"(`{report.winner_option_id}` is {rel} this threshold)"
        )
    else:
        lines.append(
            f"- **Break-even volume:** None (`{report.breakeven_direction.replace('_', ' ')}`)"
        )

    if report.max_blended_error_delta is not None:
        pp = report.max_blended_error_delta * 100.0
        tip = (
            f" (tipping blended error rate: {report.tipping_blended_error_rate * 100:.4f}%)"
            if report.tipping_blended_error_rate is not None
            else " (exceeds 100%)"
        )
        lines.append(
            f"- **Blended error-rate tolerance:** `{report.max_blended_error_delta:+.6f}` "
            f"(`{pp:+.4f}` percentage points){tip}"
        )

    if report.max_primary_error_delta is not None:
        pp_p = report.max_primary_error_delta * 100.0
        tip_p = (
            f" (tipping primary error rate: {report.tipping_primary_error_rate * 100:.4f}%)"
            if report.tipping_primary_error_rate is not None
            else ""
        )
        lines.append(
            f"- **Primary model error-rate tolerance:** `{report.max_primary_error_delta:+.6f}` "
            f"(`{pp_p:+.4f}` percentage points){tip_p}"
        )

    if report.breakeven_rework_cost_gbp is not None:
        lines.append(
            f"- **Break-even rework cost per error:** "
            f"**£{report.breakeven_rework_cost_gbp:,.2f}/error**"
        )

    lines.extend(
        [
            "",
            "## Volume Sweep",
            "",
            f"| Volume (req/mo) | `{report.winner_option_id}`/mo | `{report.challenger_option_id}`/mo | Margin/mo | Recommended | Capacity Alerts |",  # noqa: E501
            "|---:|---:|---:|---:|---|---|",
        ]
    )

    for pt in report.volume_sweep:
        tags: list[str] = []
        if pt.is_current:
            tags.append("current")
        if pt.is_breakeven:
            tags.append("break-even")
        vol_label = f"{pt.monthly_requests:,}" + (f" ({', '.join(tags)})" if tags else "")
        c_str = f"£{pt.challenger_total_gbp:,.2f}" if pt.challenger_total_gbp is not None else "-"
        adv_str = f"£{pt.advantage_gbp:,.2f}" if pt.advantage_gbp is not None else "-"
        rec_str = f"`{pt.recommended_option_id}`" if pt.recommended_option_id else "BLOCKED"
        cap_str = ", ".join(pt.capacity_warning_options) if pt.capacity_warning_options else "-"
        lines.append(
            f"| {vol_label} | £{pt.winner_total_gbp:,.2f} | {c_str} | "
            f"{adv_str} | {rec_str} | {cap_str} |"
        )

    return "\n".join(lines) + "\n"


def render_sensitivity_json(report: SensitivityReport) -> str:
    """Render sensitivity report as JSON."""
    payload = asdict(report)
    payload["volume_sweep"] = [
        {
            **asdict(pt),
            "capacity_warning_options": list(pt.capacity_warning_options),
        }
        for pt in report.volume_sweep
    ]
    return json.dumps(payload, indent=2) + "\n"
