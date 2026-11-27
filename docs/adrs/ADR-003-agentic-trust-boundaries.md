# ADR-003: Agentic Trust Boundaries and Execution Fail-Safes

- **Status:** Accepted
- **Scope:** Systems moving from read/draft assistance to external tool execution and state-changing actions
- **Accountable Owner:** Security Architecture & Runtime Controls Lead
- **Review Cadence:** Quarterly, or before adding any write/mutating tool connector

## Context

Reading internal documents and drafting summaries carries bounded, reversible risk: a human inspects the output before acting. Allowing an AI system to send communications, write database records, modify tickets, or trigger downstream APIs introduces irreversible operational and security consequences (`OWASP Top 10 for LLM Applications` — Excessive Agency and Prompt Injection). Connecting a model without explicit capability checks across primary, escalation, and fallback tiers also creates silent runtime failures when a degraded fallback model lacks structured tool-calling support.

## Options Considered & Rejected Alternatives

| Option | Pros | Why Rejected |
|---|---|---|
| **1. System-prompt instructions ("do not execute unsafe actions")** | Zero engineering effort | Bypassed by indirect prompt injection; provides no deterministic stop or audit boundary. |
| **2. Primary-only tool-calling validation without kill switch** | Works during normal steady state | Breaks on failover to non-tool-capable standby models and leaves no emergency circuit breaker. |
| **3. Explicit `action_profile` tiers + mandatory runtime guardrails, kill switch & full-path capability parity (Chosen)** | Enforces complete mediation and fail-safe stop before state changes across all routing paths | Requires runtime guardrail integration (`agent-guardrails`) and explicit capability metadata on fallback models. |

## Decision

Workloads are explicitly typed by `action_profile`:

- `read_only` < `draft_only` < `writes_with_approval` < `autonomous`

For any workload at `writes_with_approval` or `autonomous`:

1. **`ARCH-SEC-001` (HIGH):** Both `runtime_guardrails: true` (policy allow-lists, argument schema validation, idempotency, execution-time re-validation) and `kill_switch_enabled: true` are mandatory.
2. **`ARCH-CAP-001` (HIGH):** Every participating model in a routing option (`primary_model`, `escalation_model`, and `fallback_model`) must declare `supports_tool_calling: true` so failover never silently strips structured execution contracts.
3. **`ARCH-SEC-002` & `ARCH-SEC-003` (HIGH):** `confidential` and `restricted_sovereign` workloads additionally mandate `egress_restricted: true`, `audit_log_enabled: true`, and must not disable declared `cmk_encryption`, `workload_identity_rbac`, `pii_redaction_proxy`, or `signed_artifact_provenance` controls.

Reference runtime implementation: [`agent-guardrails`](https://github.com/dsugurtuna/agent-guardrails).

## Failure Modes & Mitigations

- **Tool execution during fallback outage:** Primary supports tool calling, fallback emits unvalidated free text -> **Mitigated** by `ARCH-CAP-001` checking `_option_models` across all paths.
- **Unbounded blast radius on runaway agent loop:** Missing stop control -> **Mitigated** by mandatory `kill_switch_enabled: true` (`ARCH-SEC-001`) paired with atomic budget/rate reservation at runtime.
- **Data exfiltration via external tool arguments:** Sensitive payload routed out of boundary -> **Mitigated** by `egress_restricted: true` (`ARCH-SEC-002`) and `pii_redaction_proxy`.

## Quantified Decision Thresholds & Reversal Triggers

- **Zero tolerance (`0` high-severity findings):** Any missing `runtime_guardrails`, `kill_switch_enabled`, `egress_restricted`, `audit_log_enabled`, or `supports_tool_calling` invariant triggers a `HIGH` gate block.
- **Promotion trigger:** Upgrading a workflow from `draft_only` to `writes_with_approval` or `autonomous` requires re-running `aiarch check --fail-on high` and attaching runtime policy tests from `agent-guardrails`.

## Standards & Reference Alignment

- **OWASP Top 10 for LLM Applications:** Excessive Agency, Indirect Prompt Injection, Sensitive Information Disclosure.
- **NCSC Guidelines for Secure AI System Development:** Secure deployment, least-privilege tool execution, logging and emergency response.
- **UK Government AI Playbook:** Keeping meaningful human accountability over consequential actions.

## Consequences

- Permission to connect a model to data (`read_only`) never implies permission to invoke state-changing tools (`writes_with_approval`).
- Architectural reviews reject agentic blueprints that omit stop mechanisms, execution audit trails, or fallback tool-calling parity.
