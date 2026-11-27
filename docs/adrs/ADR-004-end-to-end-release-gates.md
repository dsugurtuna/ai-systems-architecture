# ADR-004: Connecting Architecture, Runtime Controls, Evaluation, and Assurance

- **Status:** Accepted
- **Scope:** End-to-end production release governance across architecture, runtime safety, evaluation, and assurance
- **Accountable Owner:** AI Architecture & Assurance Governance Lead
- **Review Cadence:** Quarterly, or on any schema or release-gate update across the suite

## Context

Enterprise AI programmes fail when architecture design, runtime safety controls, quality evaluation, and governance assurance live in disconnected slide decks and PDFs. Each time a prompt, model version, routing threshold, or connector changes, static governance records drift out of sync with production reality—and cost models rely on uncalibrated vendor guesses instead of measured error rates and checking durations.

## Options Considered & Rejected Alternatives

| Option | Pros | Why Rejected |
|---|---|---|
| **1. Static slide-deck sign-off at project kick-off** | Fast initial approval | Unconnected to YAML configs, model swaps, or runtime controls; drifts immediately after release. |
| **2. Monolithic single-tool framework bundling proxy, evals, and governance** | Single repo | Couples runtime hot paths to offline evaluation and assurance reporting; hard to swap or audit independently. |
| **3. Coupled four-layer open-source contract with deterministic CI gates (Chosen)** | Clear separation of concerns (`Architect -> Control -> Verify -> Assure`); testable offline in CI | Requires disciplined parameter hand-off between offline eval outputs and architecture YAML blueprints. |

## Decision

Production readiness is treated as four coupled, machine-checkable layers:

1. **Architecture & Economics (`ai-systems-architecture`):** Validate residency, zero-data-retention, capability parity, capacity bounds, latency SLAs, fallback resilience, TCO, and parameter sensitivity before provisioning infrastructure.
2. **Runtime Execution Controls (`agent-guardrails`):** Enforce allow/draft/approve modes, execution-time re-validation, atomic budgets, idempotency, kill switches, and hash-chained audit logs on every tool call.
3. **Evaluation & Benchmarking (`evidence-synthesis-eval`):** Measure faithfulness, citation integrity, misstatements, blinded human-judge calibration, `escaped_error_rate`, and `review_minutes_per_item` (`ARCH-EVAL-001`) before model promotion.
4. **Proportionate Assurance (`ai-assurance-kit`):** Maintain versioned YAML use-case records, accountable risk owners, 26 automated checks, and diff-triggered re-review gates.

## Failure Modes & Mitigations

- **Stale YAML assumptions after model upgrade:** Blueprint keeps pre-launch `escaped_error_rate` after a silent model update degrades quality -> **Mitigated** by requiring `eval_gate_enabled: true` (`ARCH-EVAL-001`) and checking error tolerances via `aiarch sensitivity`.
- **Documentation drift between CLI behaviour and README/ADRs:** Docs promise gates or commands that do not match code -> **Mitigated** by deterministic CI drift tests (`tests/test_docs.py`) asserting CLI output parity and subcommand/ADR integrity.

## Quantified Decision Thresholds & Reversal Triggers

- **Release gate:** CI blocks release on `aiarch check <blueprint> --fail-on high` (exit code `1`) and flags `ARCH-EVAL-001` warnings whenever `eval_gate_enabled: false`.
- **Re-calibration trigger:** Any model-version change, prompt template revision, or >=10% shift in escalation rate requires re-running offline evaluations and updating `escaped_error_rate` and `review_minutes_per_item` before committing blueprint updates.

## Standards & Reference Alignment

- **UK Government AI Playbook & GOV.UK ATRS:** End-to-end lifecycle transparency, evaluation prior to deployment, and ongoing monitoring.
- **NIST AI Risk Management Framework (AI RMF):** Govern, Map, Measure, and Manage alignment across layers.
- **HM Treasury Aqua Book:** Analytical quality assurance connecting model assumptions to empirical verification.

## Consequences

- Architectural decisions map directly to testable code gates rather than static checklists.
- Leadership, engineering, and assurance teams share one explicit contract connecting unit economics to measured error rates and runtime fail-safes.
