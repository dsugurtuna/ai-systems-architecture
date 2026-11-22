# ADR-001: Sovereign, Private VPC, and Hosted API Deployment Boundaries

- **Status:** Accepted
- **Scope:** Enterprise, regulated, and sovereign LLM workloads

## Context

Organisations deploying foundation models routinely confuse vendor contractual assurances with architectural isolation. For `confidential` and `restricted_sovereign` workloads, sending payloads to multi-tenant public endpoints creates data-residency, telemetry-retention, and supply-chain exposure risks that cannot be mitigated solely through prompts or terms of service.

## Decision

Model deployments are classified into three non-interchangeable modes:

1. **`hosted_api`:** Multi-tenant vendor API. Permitted only for `public` or `internal` workloads (with zero data retention when handling non-public data).
2. **`private_cloud_endpoint`:** Tenant-isolated endpoint inside a region-pinned cloud boundary (`uk_eu` or `sovereign_vpc`) with explicit zero data retention (`zero_data_retention: true`) and egress controls.
3. **`self_hosted_open_weights`:** Customer-controlled weights running in dedicated VPC or `air_gapped` infrastructure. Required whenever workloads mandate air-gapped execution or full weight/runtime sovereignty.

These boundaries are enforced deterministically via `ARCH-SOV-001`, `ARCH-SOV-002`, `ARCH-RES-001`, and `ARCH-RET-001` across **every** participating model in a routing option — including fallback paths, so failover never silently downgrades sovereignty guarantees.

## Consequences

- Teams cannot pass an architectural gate review by declaring a sovereign workload on a public API.
- Multi-tier cascades must verify residency and retention parity across primary, escalation, and fallback tiers.
