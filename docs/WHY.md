# Why it's built this way

## The problem in two sentences

Teams routinely choose AI architectures by comparing token prices in a spreadsheet while treating sovereignty, latency, fallback resilience, and human verification cost as afterthoughts. By the time hidden rework or compliance failures show up, the system is already built around the wrong boundary.

## Design choices

**Why model total cost including human review and rework instead of token spend alone?**
Because in high-consequence domains, inference is often less than 15% of operational cost. A cheap model that hallucinates twice as often looks attractive on an API rate card while destroying net ROI through human verification minutes and downstream rework.

**Why enforce sovereignty and retention as deterministic code gates?**
Because security and compliance boundaries are binary invariants, not fuzzy scores. Checking `ARCH-SOV-001` through `ARCH-RET-001` in CI makes it obvious immediately when a fallback or escalation path quietly leaks data onto a multi-tenant public endpoint.

**Why check fallback models for residency and retention parity?**
Because failover paths are where architectures break under pressure. If primary traffic stays inside a sovereign VPC while the fallback model points to an unconstrained hosted API, an outage turns into a data-residency breach.

**Why store pricing, latency, and error rates in editable YAML blueprints instead of hardcoding vendor tables?**
Because vendor rate cards, self-hosted GPU cluster costs, and task-specific error rates change continuously. Putting assumptions explicitly in version-controlled YAML lets engineering, finance, and risk teams challenge and sensitivity-test every parameter together.

**Why no LLM calls inside the validator?**
Architecture gate checks must be deterministic, fast, and reproducible offline. Same blueprint in, same gate findings and unit economics out.

## How this fits with the rest of the suite

- [`agent-guardrails`](https://github.com/dsugurtuna/agent-guardrails) enforces runtime controls on state-changing tool calls.
- [`evidence-synthesis-eval`](https://github.com/dsugurtuna/evidence-synthesis-eval) measures the actual error rates and human checking minutes that feed into these economics blueprints.
- [`ai-assurance-kit`](https://github.com/dsugurtuna/ai-assurance-kit) tracks accountable owners, risks, and proportionate governance sign-offs across the portfolio.
