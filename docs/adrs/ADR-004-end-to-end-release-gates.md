# ADR-004: Connecting Architecture, Runtime Controls, Evaluation, and Assurance

- **Status:** Accepted
- **Scope:** End-to-end production release governance

## Context

Enterprise AI programmes fail when architecture design, runtime safety controls, quality evaluation, and governance assurance live in disconnected slide decks and PDFs. Each time a prompt, model version, or connector changes, governance records drift out of sync with production reality.

## Decision

Production readiness is treated as four coupled, machine-checkable layers:

1. **Architecture & Economics (`ai-systems-architecture`):** Validate residency, zero-data-retention, latency SLAs, fallback resilience, and total cost of ownership before provisioning infrastructure.
2. **Runtime Execution Controls (`agent-guardrails`):** Enforce allow/draft/approve modes, execution-time re-validation, idempotency, and hash-chained audit logs on every tool call.
3. **Evaluation & Benchmarking (`evidence-synthesis-eval`):** Measure faithfulness, coverage, misstatements, judge calibration, and human checking time (`ARCH-EVAL-001`) before model promotion.
4. **Proportionate Assurance (`ai-assurance-kit`):** Maintain versioned YAML use-case records, risk ownership, and diff-triggered re-review gates.

## Consequences

- Architectural decisions map directly to testable code gates rather than static checklists.
- Leadership teams can compare options, enforce risk appetite, and audit changes uniformly across deployments.
