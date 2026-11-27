# ADR-002: Tiered Model Routing and Total Cost of Ownership (TCO)

- **Status:** Accepted
- **Scope:** High-volume production LLM routing, capacity planning, and commercial ROI cases
- **Accountable Owner:** Architecture & FinOps / Tokenomics Review
- **Review Cadence:** Quarterly, or upon >=15% vendor rate-card change or model evaluation refresh

## Context

Evaluating AI architectures purely on `£ / 1M tokens` systematically distorts build-vs-buy and model-selection decisions in two opposite directions:

1. **All-frontier routing** overpays on high-volume, structured workloads where a dedicated open-weights cluster or tiered cascade meets evaluated quality parity at lower marginal compute cost.
2. **Naive small-model routing** underprices **human verification labour** and **downstream rework cost**. A model costing £30/month in tokens whose 2.0% escaped error rate triggers £65,000/month in checking and rework is a commercial loss (`ARCH-ECO-001`).

Furthermore, naive simulators introduce three classic modelling errors: charging full active GPU cluster fees for an idle `fallback_model`, billing `1 - r` primary tokens in a sequential cascade that actually calls the primary model on `100%` of requests, and treating `human_review_gbp` as constant across models of wildly different faithfulness.

## Options Considered & Rejected Alternatives

| Option | Pros | Why Rejected |
|---|---|---|
| **1. Token-price-only comparison (`£ / 1M tokens`)** | Simple rate-card arithmetic | Ignores 85%–98% of true operational cost (human review, rework, MLOps, standby infra). |
| **2. Fixed-infra double-counting + `0.05` step latency** | Penalises unconfigured clusters | Falsely charges idle GPU fallback clusters (`£3,200/mo` distortion) and produces discontinuous `1,750 ms` latency jumps at `r = 0.05`. |
| **3. Full-TCO mode-aware model with standby separation, smooth tail latency & sensitivity sweeps (Chosen)** | Separates `fixed_monthly_infra_gbp` + `ops_monthly_gbp` from `standby_monthly_infra_gbp`; models `sequential_cascade` vs `pre_router`; prices per-model review burden | Requires explicit assumption discipline via YAML parameters and periodic empirical calibration. |

## Decision

Every architecture evaluation prices four explicit operational components:

1. **Variable token cost (`token_cost_gbp`):**
   - In **`sequential_cascade`** (default when `escalation_model` is set): `primary_model` executes on `1.0` of requests, and fraction `r = escalation_rate` escalates to `escalation_model` (incorporating `cache_hit_rate * cache_hit_discount` on input tokens).
   - In **`pre_router`**: an upfront router sends `1.0 - r` directly to `primary_model` and `r` directly to `escalation_model`.
2. **Infrastructure, ops & standby cost (`fixed_and_ops_gbp + standby_infra_gbp`):**
   - Active models (`primary_model`, `escalation_model`) incur `fixed_monthly_infra_gbp + ops_monthly_gbp` (once per unique active model).
   - A distinct `fallback_model` incurs only `standby_monthly_infra_gbp` (`0.0` for elastic pay-per-token DR endpoints; positive for warm dedicated sovereign standby clusters).
3. **Model-aware human verification cost (`human_review_gbp`):**
   - Each model's effective review burden scales `workload.human_review_rate` via `review_rate_multiplier` and optional `review_minutes_per_item` overrides (or `RoutingOption` overrides), blended across `(1 - r)` primary and `r` escalation final outputs.
4. **Downstream rework cost (`rework_gbp`) & smooth tail latency (`p95_latency_ms`):**
   - `blended_error_rate = (1 - r) * primary.escaped_error_rate + r * escalation.escaped_error_rate`.
   - `p95_latency_ms` solves the exact Weibull(`k=3`) mixture quantile `(1 - r) * P(X1 > t) + r * P(X2 > t) = 0.05`, eliminating arbitrary `0.05` step cliffs while capturing sequential (`primary + escalation`) vs pre-routed (`escalation`) slow paths.

## Failure Modes & Mitigations

- **Paper-thin crossover margin:** Self-hosted cluster wins at high volume only if `escaped_error_rate` holds within `<0.02` percentage points of frontier -> **Mitigated** by `aiarch sensitivity` exposing exact `breakeven_monthly_requests` and `max_blended_error_delta`, paired with `ARCH-EVAL-001`.
- **Unbounded cluster throughput:** Scaling `monthly_requests` 10x without adding GPUs -> **Mitigated** by `ModelProfile.max_monthly_tokens` and warning gate `ARCH-CAP-002`.

## Quantified Decision Thresholds & Reversal Triggers

- **`ARCH-ECO-001` warning:** Triggered whenever `net_monthly_savings_gbp < 0.0`.
- **`ARCH-CAP-002` warning:** Triggered whenever routed tokens exceed `max_monthly_tokens` on any active model.
- **`ARCH-LAT-001` warning:** Triggered whenever blended `p95_latency_ms > workload.p95_latency_sla_ms`.
- **Reversal trigger:** Re-run `aiarch sensitivity` whenever measured `escaped_error_rate` from `evidence-synthesis-eval` drifts within `50%` of `max_blended_error_delta`, or monthly volume crosses `breakeven_monthly_requests`.

## Standards & Reference Alignment

- **HM Treasury Aqua Book & Orange Book:** Explicit sensitivity analysis, transparent analytical assumptions, and proportionate risk-cost appraisal.
- **UK Government AI Playbook:** Full lifecycle value measurement beyond software/token licence fees.

## Consequences

- Commercial business cases expose whether human checking and rework dominate total cost (`human_effort_share_pct`).
- High-volume self-hosted migrations require empirical quality-parity evidence rather than optimistic error-rate assumptions.
