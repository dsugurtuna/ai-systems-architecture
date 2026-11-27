# Why it's built this way

## The problem in two sentences

Teams routinely choose AI architectures by comparing token prices in a spreadsheet while treating sovereignty, failover parity, capacity ceilings, and human verification cost as afterthoughts. By the time hidden rework, idle failover clusters, or compliance failures show up, the system is already built around the wrong boundary.

## Design choices

**Why model total cost including human review and rework instead of token spend alone?**
Because in high-consequence domains, inference is often less than 15% of operational cost. A cheap model that hallucinates twice as often—or forces reviewers to spend more time checking weak citations—looks attractive on an API rate card while destroying net ROI through human verification minutes (`review_rate_multiplier`, `review_minutes_per_item`) and downstream rework.

**Why separate active `fixed_monthly_infra_gbp` and `ops_monthly_gbp` from `standby_monthly_infra_gbp`?**
Because charging full dedicated GPU cluster rent for an idle `fallback_model` silently penalises pay-per-token cloud options by thousands of pounds per month. Active tiers pay compute and MLOps overhead; standby-only fallbacks pay only their explicit reservation or warm-standby cost (`0.0` for elastic secondary-region endpoints).

**Why separate `sequential_cascade` from `pre_router` and remove the `0.05` latency step?**
Because a sequential cascade runs the primary model on 100% of traffic before escalating ambiguous items (`r`), whereas an upfront pre-router sends `(1 - r)` to primary and `r` directly to escalation. Modelling tail latency with a smooth mixture quantile eliminates artificial discontinuities while preserving realistic slow-path impact.

**Why enforce sovereignty, retention, and tool-calling across all participating models?**
Because failover paths are where architectures break under pressure. If primary traffic stays inside a sovereign VPC while the fallback model points to an unconstrained hosted API, or lacks `supports_tool_calling` on a state-changing workload, an outage turns into a data-residency or execution breach. See [docs/diagrams/architecture-boundaries.md](diagrams/architecture-boundaries.md).

**Why include `aiarch sensitivity` alongside static cost tables?**
Because single-point TCO estimates hide razor-thin margins. `aiarch sensitivity` computes the exact break-even request volume, error-rate tipping point (`max_blended_error_delta`), rework-cost break-even, and volume capacity warnings (`ARCH-CAP-002`) directly from the blueprint parameters.

**Why no LLM calls inside the validator?**
Architecture gate checks must be deterministic, fast, and reproducible offline. Same blueprint in, same gate findings, unit economics, and sensitivity tipping points out.

## How this fits with the rest of the suite

- [`agent-guardrails`](https://github.com/dsugurtuna/agent-guardrails) enforces runtime controls on state-changing tool calls (`ARCH-SEC-001` / `ARCH-CAP-001`).
- [`evidence-synthesis-eval`](https://github.com/dsugurtuna/evidence-synthesis-eval) measures the actual error rates and human checking minutes (`ARCH-EVAL-001`) that calibrate these economics blueprints.
- [`ai-assurance-kit`](https://github.com/dsugurtuna/ai-assurance-kit) tracks accountable owners, risks, and proportionate governance sign-offs across the portfolio.
