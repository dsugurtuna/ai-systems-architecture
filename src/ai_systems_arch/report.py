"""Markdown and JSON rendering for architecture economics and gate reports."""

from __future__ import annotations

import json
from dataclasses import asdict

from .economics import OptionEconomics
from .schema import ArchitectureBlueprint, Severity
from .validator import Finding


def recommend_option(
    economics: list[OptionEconomics],
    findings: list[Finding],
) -> OptionEconomics | None:
    """Return the lowest-total-cost option with zero high-severity findings."""
    global_high = any(f.option_id is None and f.severity == Severity.HIGH for f in findings)
    if global_high:
        return None
    blocked_options = {
        f.option_id for f in findings if f.option_id is not None and f.severity == Severity.HIGH
    }
    eligible = [e for e in economics if e.option_id not in blocked_options]
    if not eligible:
        return None
    return min(eligible, key=lambda e: e.total_monthly_gbp)


def _format_gate_label(
    high_n: int,
    warn_n: int,
    global_high_n: int,
    global_warn_n: int,
) -> str:
    if high_n > 0 and global_high_n > 0:
        return f"BLOCKED ({high_n} high, {global_high_n} blueprint, {warn_n} warn)"
    if high_n > 0:
        return f"BLOCKED ({high_n} high, {warn_n} warn)"
    if global_high_n > 0:
        if warn_n > 0:
            return f"BLOCKED (blueprint gate, {warn_n} warn)"
        return "BLOCKED (blueprint gate)"
    if warn_n > 0 and global_warn_n > 0:
        return f"PASS ({warn_n} warn, {global_warn_n} blueprint)"
    if warn_n > 0:
        return f"PASS ({warn_n} warn)"
    if global_warn_n > 0:
        return f"PASS ({global_warn_n} blueprint warn)"
    return "PASS"


def render_markdown(
    blueprint: ArchitectureBlueprint,
    economics: list[OptionEconomics],
    findings: list[Finding],
) -> str:
    """Render an executive trade-off and architecture gate brief in Markdown."""
    w = blueprint.workload
    global_high_n = sum(1 for f in findings if f.option_id is None and f.severity == Severity.HIGH)
    global_warn_n = sum(
        1 for f in findings if f.option_id is None and f.severity == Severity.WARNING
    )

    lines: list[str] = [
        f"# Architecture Brief: {w.title}",
        "",
        (
            f"**Workload:** `{w.id}` | **Domain:** {w.domain} | "
            f"**Volume:** {w.monthly_requests:,} req/mo "
            f"({w.avg_input_tokens:,} in / {w.avg_output_tokens:,} out tokens)"
        ),
        (
            f"**Posture:** sensitivity=`{w.data_sensitivity.value}`, "
            f"residency=`{w.residency.value}`, action=`{w.action_profile.value}`, "
            f"SLA p95={w.p95_latency_sla_ms} ms"
        ),
        "",
        "| Option | Deployment | Inference/mo | Review + Rework/mo | Total/mo | Net Savings/mo | p95 (ms) | Gates |",  # noqa: E501
        "|---|---|---:|---:|---:|---:|---:|---|",
    ]

    for e in economics:
        opt_findings = [f for f in findings if f.option_id == e.option_id]
        high_n = sum(1 for f in opt_findings if f.severity == Severity.HIGH)
        warn_n = sum(1 for f in opt_findings if f.severity == Severity.WARNING)
        gate_label = _format_gate_label(high_n, warn_n, global_high_n, global_warn_n)
        review_rework = e.human_review_gbp + e.rework_gbp
        lines.append(
            f"| {e.option_name} | `{e.deployment_summary}` | "
            f"£{e.inference_gbp:,.2f} | £{review_rework:,.2f} | £{e.total_monthly_gbp:,.2f} | "
            f"£{e.net_monthly_savings_gbp:,.2f} | {e.p95_latency_ms} | {gate_label} |"
        )

    best = recommend_option(economics, findings)
    lines.append("")
    if best is not None:
        lines.append(
            f"**Recommendation:** `{best.option_id}` ({best.option_name}) — "
            f"£{best.total_monthly_gbp:,.2f}/mo total (£{best.cost_per_task_gbp:.4f}/task, "
            f"net savings £{best.net_monthly_savings_gbp:,.2f}/mo, "
            f"inference {best.inference_share_pct:.1f}% vs "
            f"human effort {best.human_effort_share_pct:.1f}%)."
        )
    elif global_high_n > 0:
        lines.append(
            "**Recommendation:** Blocked — blueprint-level security and governance controls "
            "fail high-severity gates."
        )
    else:
        lines.append(
            "**Recommendation:** Blocked — no candidate option clears all high-severity "
            "sovereignty, retention, and capability gates."
        )

    if findings:
        lines.extend(["", "## Gate Findings", ""])
        for f in findings:
            scope = f"[{f.option_id}]" if f.option_id else "[blueprint]"
            lines.append(
                f"- **{f.severity.value.upper()}** `{f.rule_id}` {scope} **{f.title}** — {f.detail}"
            )

    return "\n".join(lines) + "\n"


def render_json(
    blueprint: ArchitectureBlueprint,
    economics: list[OptionEconomics],
    findings: list[Finding],
) -> str:
    """Render blueprint economics, recommendation, and findings as JSON."""
    best = recommend_option(economics, findings)
    payload = {
        "workload_id": blueprint.workload.id,
        "recommended_option_id": best.option_id if best is not None else None,
        "economics": [asdict(e) for e in economics],
        "findings": [
            {
                "rule_id": f.rule_id,
                "severity": f.severity.value,
                "option_id": f.option_id,
                "title": f.title,
                "detail": f.detail,
            }
            for f in findings
        ],
    }
    return json.dumps(payload, indent=2) + "\n"
