# Reference Architecture Boundaries & Failover Topology

> **Illustrative reference topology.** These diagrams depict the architectural boundaries, security invariants, and routing/failover flows enforced deterministically by `aiarch validate`, `aiarch check`, `aiarch economics`, and `aiarch sensitivity`.

## 1. Deployment & Trust Boundary Topology (Sovereign VPC, Private Link & Air-Gap)

Every routing option in an `ArchitectureBlueprint` is checked across **all participating models** (`primary_model`, `escalation_model`, and `fallback_model`) so that failover under load or outage never silently crosses a weaker residency, retention, or capability perimeter.

```mermaid
flowchart TB
    subgraph ClientPlane["1. Application & Identity Plane"]
        Caller["Enterprise User / Workflow Client"]
        IdP["OIDC / Workload Identity + RBAC"]
        Caller --> IdP
    end

    subgraph ControlProxy["2. Policy, Guardrail & Egress Boundary (ARCH-SEC-001/002/003)"]
        Proxy["PII / DLP Egress Proxy & Policy Router"]
        Guard["agent-guardrails: Allow / Draft / Approve + Kill Switch"]
        Retrieval["Classification-Scoped Retrieval Index (ACL + CMK)"]
        IdP --> Proxy
        Proxy --> Guard
        Guard --> Retrieval
    end

    subgraph RoutingGate["3. Deterministic Boundary Gates (ARCH-SOV / RES / RET / CAP)"]
        Gate["Residency, ZDR, Tool-Calling & Capacity Parity Check"]
        Guard --> Gate
    end

    subgraph ZoneHosted["Zone A: hosted_api (public / internal + ZDR only)"]
        Hosted["Multi-Tenant Vendor API (Blocked for confidential / sovereign / air_gapped)"]
    end

    subgraph ZoneVPC["Zone B: private_cloud_endpoint (uk_eu / sovereign_vpc)"]
        PrivLink["Private Link / NAT-Less Egress (CMK + ZDR)"]
        PrivPrimary["UK Private Frontier Endpoint (Primary / Escalation)"]
        PrivDR["Secondary UK Private Region DR Fallback (standby_monthly_infra_gbp)"]
        PrivLink --> PrivPrimary
        PrivLink --> PrivDR
    end

    subgraph ZoneAirGap["Zone C: self_hosted_open_weights (sovereign_vpc / air_gapped)"]
        Signed["Signed Model Weights & Container Provenance"]
        ClusterHA["Multi-AZ Open-Weights Cluster (max_monthly_tokens bounded)"]
        Standby["Warm Sovereign Standby Node (standby_monthly_infra_gbp)"]
        Signed --> ClusterHA
        Signed --> Standby
    end

    Gate -->|"Permitted only for public / internal"| Hosted
    Gate -->|"uk_eu / sovereign_vpc via Private Link"| PrivLink
    Gate -->|"sovereign_vpc / air_gapped + signed weights"| Signed

    subgraph AssuranceLoop["4. Audit, Evaluation & Assurance Loop"]
        Audit["Tamper-Evident Hash-Chained Audit & SIEM Sink"]
        Eval["evidence-synthesis-eval: Faithfulness, Errors & Review Minutes"]
        Assurance["ai-assurance-kit: Versioned YAML Record & Diff Gate"]
        Proxy --> Audit
        ClusterHA --> Audit
        PrivPrimary --> Audit
        Audit --> Eval
        Eval -->|"Calibrates escaped_error_rate & review_minutes_per_item"| Assurance
    end
```

## 2. Tiered Cascade, Failover & Human-in-the-Loop Execution Flow

`RoutingOption.routing_mode` explicitly distinguishes a **`sequential_cascade`** (where `primary_model` executes `100%` of requests before escalating fraction `r` to `escalation_model`, incurring `1.0 * primary + r * escalation` token spend and smooth tail-mixture latency) from a **`pre_router`** (where an upfront classifier routes `1 - r` to `primary_model` and `r` directly to `escalation_model`).

```mermaid
sequenceDiagram
    autonumber
    participant Client as Caller / App
    participant Guard as Policy & PII/DLP Proxy
    participant Primary as Primary Model (Open Weights / Private)
    participant Esc as Escalation Tier (Private Frontier)
    participant Fallback as Parity-Checked Fallback
    participant Review as Human Reviewer (HITL)
    participant Audit as Audit Sink & Eval Loop

    Client->>Guard: Request + Workload Identity (OIDC/RBAC)
    Guard->>Guard: Enforce egress_restricted, pii_redaction_proxy, kill_switch

    alt routing_mode == sequential_cascade
        Guard->>Primary: Execute 100% of requests (primary_exec_share = 1.0)
        alt Primary healthy & confident (1 - r)
            Primary-->>Guard: Candidate output + confidence score
        else Ambiguous / low confidence (fraction r)
            Primary-->>Guard: Escalation trigger
            Guard->>Esc: Escalate fraction r (adds escalation latency + tokens)
            Esc-->>Guard: High-faithfulness output
        else Primary unavailable / timeout
            Guard->>Fallback: Failover to residency/ZDR/tool-parity fallback
            Fallback-->>Guard: Degraded-mode output
        end
    else routing_mode == pre_router
        Guard->>Guard: Classify complexity upfront
        alt Routine (1 - r)
            Guard->>Primary: Route (1 - r) directly
            Primary-->>Guard: Candidate output
        else Complex (r)
            Guard->>Esc: Route r directly (no primary token spend)
            Esc-->>Guard: High-faithfulness output
        end
    end

    opt action_profile in {writes_with_approval, autonomous}
        Guard->>Guard: Verify supports_tool_calling + runtime_guardrails + approval
    end

    alt Selected for human check (human_review_rate * review_rate_multiplier)
        Guard->>Review: Queue item for verification (human_review_gbp)
        Review-->>Audit: Approval / correction recorded
    else Released automatically
        Guard->>Client: Return verified response
    end

    Guard->>Audit: Append hash-chained audit event (audit_log_enabled)
    Audit->>Audit: Measure escaped_error_rate -> price rework_gbp
```
