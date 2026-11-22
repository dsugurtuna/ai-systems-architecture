# ADR-003: Agentic Trust Boundaries and Execution Fail-Safes

- **Status:** Accepted
- **Scope:** Systems moving from read/draft assistance to external tool execution

## Context

Reading internal documents and drafting summaries carries reversible risk: a person reads the output before acting. Allowing an AI system to send communications, write database records, modify tickets, or trigger downstream APIs introduces irreversible operational and security consequences (`OWASP LLM Top 10` — Excessive Agency).

## Decision

Workloads are explicitly typed by `action_profile`:

- `read_only` < `draft_only` < `writes_with_approval` < `autonomous`

Any workload at `writes_with_approval` or `autonomous` must enforce both **runtime guardrails** (policy allow-lists, argument validation, idempotency, execution-time re-validation) and a **kill switch** (`ARCH-SEC-001`). Confidential and sovereign workloads additionally require **egress restriction** and **tamper-evident audit logging** (`ARCH-SEC-002`).

Reference runtime implementation: [`agent-guardrails`](https://github.com/dsugurtuna/agent-guardrails).

## Consequences

- Permission to connect a model to data does not imply permission to invoke state-changing tools.
- Architectural reviews reject agentic blueprints that omit stop mechanisms or execution audit trails.
