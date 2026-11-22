# ADR-002: Tiered Model Routing and Total Cost of Ownership (TCO)

- **Status:** Accepted
- **Scope:** High-volume production LLM routing and commercial ROI cases

## Context

Evaluating AI architectures purely on `£ / 1M tokens` systematically distorts build-vs-buy and model-selection decisions in two opposite directions:

1. **All-frontier routing** overpays on predictable, low-ambiguity traffic where an open-weights model inside a private VPC meets quality requirements at a fraction of the variable token cost.
2. **Naive small-model routing** underprices **human verification time** and **downstream rework cost**. A model costing £200/month in tokens whose 2% escaped error rate triggers £40,000/month in clinical, financial, or operational rework is a net loss.

## Decision

Every architecture evaluation prices the full operational unit economics:

- **Inference cost:** Blended primary and escalation token spend (incorporating prompt cache hit discounts) plus fixed cluster/provisioned-throughput infrastructure for active models.
- **Human verification cost:** Expected reviewer time per item (`human_review_rate × review_minutes × reviewer_hourly_gbp`).
- **Downstream rework cost:** Blended escaped error rate multiplied by `rework_cost_per_error_gbp`.

Gate `ARCH-ECO-001` automatically flags architectures whose total monthly cost exceeds the operational baseline (`net_monthly_savings_gbp < 0`).

## Consequences

- Commercial business cases expose whether human checking dominates total cost (`human_effort_share_pct`).
- Tiered open-weights + frontier escalation cascades are evaluated fairly on net value rather than raw token price alone.
