# ADR-001: Sovereign, Private VPC, and Hosted API Deployment Boundaries

- **Status:** Accepted
- **Scope:** Enterprise, regulated, and sovereign LLM workloads
- **Accountable Owner:** Architecture & AI Governance Review
- **Review Cadence:** Quarterly, or on any residency, sensitivity, or model hosting change

## Context

Organisations deploying foundation models routinely confuse vendor contractual assurances with architectural isolation. For `confidential` and `restricted_sovereign` workloads, sending payloads to multi-tenant public endpoints creates data-residency, telemetry-retention, identity-isolation, and supply-chain exposure risks that cannot be mitigated solely through prompts or terms of service.

## Options Considered & Rejected Alternatives

| Option | Pros | Why Rejected / Constrained |
|---|---|---|
| **1. Public multi-tenant API with contractual ZDR only** | Zero fixed infrastructure; lowest entry barrier | Fails tenant network isolation (`Private Link`), CMK key custody, and sovereign residency invariants (`ARCH-SOV-001`). Restricted strictly to `public` or `internal` workloads. |
| **2. Validate residency on `primary_model` only** | Allows cheap public failover | Silently breaches residency and ZDR guarantees the moment the primary tier experiences an outage or routes escalation traffic (`ADR-001` failover parity failure). |
| **3. Uniform three-mode policy across primary, escalation, and fallback (Chosen)** | Deterministic CI enforcement across every participating model; explicit air-gap isolation | Requires explicit provisioning of parity-matched DR endpoints or warm sovereign standby nodes. |

## Decision

Model deployments are classified into three non-interchangeable modes:

1. **`hosted_api`:** Multi-tenant vendor API. Permitted **only** for `public` or `internal` workloads (with `zero_data_retention: true` required whenever handling non-public data, including `internal`). Explicitly **blocked** for `confidential`, `restricted_sovereign`, and `air_gapped` workloads.
2. **`private_cloud_endpoint`:** Tenant-isolated endpoint inside a region-pinned cloud boundary (`uk_eu` or `sovereign_vpc`) with explicit zero data retention (`zero_data_retention: true`), Private Link / egress restriction (`egress_restricted: true`), and optional CMK/OIDC/PII-proxy controls.
3. **`self_hosted_open_weights`:** Customer-controlled weights running in dedicated VPC or `air_gapped` infrastructure with signed artifact provenance (`signed_artifact_provenance`). Required whenever workloads mandate `air_gapped` execution (`ARCH-SOV-002`).

These boundaries are enforced deterministically via `ARCH-SOV-001`, `ARCH-SOV-002`, `ARCH-RES-001`, `ARCH-RET-001`, and `ARCH-SEC-003` across **every** participating model in a routing option (`primary_model`, `escalation_model`, and `fallback_model`), and `RoutingOption` forbids trivial `fallback_model == primary_model` or `escalation_model == primary_model` self-loops.

## Failure Modes & Mitigations

- **Failover boundary downgrade:** Primary stays in `sovereign_vpc` while `fallback_model` routes to `hosted_api` or `any` residency -> **Mitigated** by evaluating `_option_models` across all three tiers in `ARCH-SOV-001/002`, `ARCH-RES-001`, and `ARCH-RET-001`.
- **Internal data retained for model training:** `internal` workload uses a multi-tenant endpoint with `zero_data_retention: false` -> **Mitigated** by enforcing `ARCH-RET-001` on all `data_sensitivity != public` workloads.
- **Unverified open-weight containers:** Self-hosted weights loaded without digest/signature checks -> **Mitigated** by `ARCH-SEC-003` flagging `signed_artifact_provenance: false`.

## Quantified Decision Thresholds & Reversal Triggers

- **Zero tolerance (`0` high-severity findings):** Any `ARCH-SOV-001`, `ARCH-SOV-002`, `ARCH-RES-001`, or `ARCH-RET-001` finding blocks recommendation (`recommend_option` returns `None` for that option; `aiarch check --fail-on high` exits `1`).
- **Reversal trigger:** A workload may only adopt `hosted_api` if formal DPIA / data-classification review reclassifies payload sensitivity to `public` or `internal` (with verified ZDR).

## Standards & Reference Alignment

- **NCSC Cloud Security Principles:** Data in transit/rest protection, separation between customers, identity and authentication.
- **UK Government AI Playbook & GOV.UK ATRS:** Proportionate data governance, clear deployment boundary transparency.
- **ICO UK GDPR / DPIA Guidance:** Data minimisation, retention limitation, and cross-border transfer boundaries.

## Consequences

- Teams cannot pass an architectural gate review by declaring a `confidential` or `sovereign` workload on a public API.
- Multi-tier cascades must provision parity-checked DR private endpoints or warm sovereign standby nodes.
