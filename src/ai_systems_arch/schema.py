"""Strict schema definitions for AI workload, model, routing, and control blueprints."""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator


class DataSensitivity(StrEnum):
    PUBLIC = "public"
    INTERNAL = "internal"
    CONFIDENTIAL = "confidential"
    RESTRICTED_SOVEREIGN = "restricted_sovereign"


class ResidencyRequirement(StrEnum):
    ANY = "any"
    UK_EU = "uk_eu"
    SOVEREIGN_VPC = "sovereign_vpc"
    AIR_GAPPED = "air_gapped"


class DeploymentMode(StrEnum):
    HOSTED_API = "hosted_api"
    PRIVATE_CLOUD_ENDPOINT = "private_cloud_endpoint"
    SELF_HOSTED_OPEN_WEIGHTS = "self_hosted_open_weights"


class ActionProfile(StrEnum):
    READ_ONLY = "read_only"
    DRAFT_ONLY = "draft_only"
    WRITES_WITH_APPROVAL = "writes_with_approval"
    AUTONOMOUS = "autonomous"


class Severity(StrEnum):
    HIGH = "high"
    WARNING = "warning"
    INFO = "info"


class WorkloadSpec(BaseModel):
    """Operational volume, SLA, sensitivity, and human-cost parameters for one AI workload."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    domain: str = Field(min_length=1)
    monthly_requests: int = Field(gt=0)
    avg_input_tokens: int = Field(gt=0)
    avg_output_tokens: int = Field(gt=0)
    data_sensitivity: DataSensitivity
    residency: ResidencyRequirement
    action_profile: ActionProfile
    p95_latency_sla_ms: int = Field(gt=0)
    human_review_rate: float = Field(ge=0.0, le=1.0)
    review_minutes_per_item: float = Field(ge=0.0)
    reviewer_hourly_gbp: float = Field(ge=0.0)
    rework_cost_per_error_gbp: float = Field(ge=0.0)
    baseline_cost_per_task_gbp: float = Field(ge=0.0)


class ModelProfile(BaseModel):
    """Hosting, compliance, pricing, latency, and error profile for a candidate model."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    label: str = Field(min_length=1)
    deployment_mode: DeploymentMode
    residency_supported: list[ResidencyRequirement] = Field(min_length=1)
    zero_data_retention: bool
    input_gbp_per_1m_tokens: float = Field(ge=0.0)
    output_gbp_per_1m_tokens: float = Field(ge=0.0)
    cache_hit_discount: float = Field(default=0.0, ge=0.0, le=1.0)
    fixed_monthly_infra_gbp: float = Field(default=0.0, ge=0.0)
    p95_latency_ms: int = Field(gt=0)
    escaped_error_rate: float = Field(ge=0.0, le=1.0)
    supports_tool_calling: bool = True


class RoutingOption(BaseModel):
    """Candidate architecture combining primary, escalation, caching, and fallback paths."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    primary_model: str = Field(min_length=1)
    escalation_model: str | None = None
    escalation_rate: float = Field(default=0.0, ge=0.0, le=1.0)
    cache_hit_rate: float = Field(default=0.0, ge=0.0, le=1.0)
    fallback_model: str | None = None
    notes: str = ""

    @model_validator(mode="after")
    def _validate_escalation_consistency(self) -> RoutingOption:
        if self.escalation_model is None and self.escalation_rate != 0.0:
            raise ValueError("escalation_rate must be 0.0 when escalation_model is omitted")
        if self.escalation_model is not None and self.escalation_rate == 0.0:
            raise ValueError("escalation_rate must be > 0.0 when escalation_model is set")
        return self


class SecurityControls(BaseModel):
    """Governance and runtime security controls declared for the architecture."""

    model_config = ConfigDict(extra="forbid")

    egress_restricted: bool
    audit_log_enabled: bool
    runtime_guardrails: bool
    eval_gate_enabled: bool
    kill_switch_enabled: bool


class ArchitectureBlueprint(BaseModel):
    """Complete architectural blueprint pairing a workload with candidate routing options."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0"] = "1.0"
    workload: WorkloadSpec
    models: list[ModelProfile] = Field(min_length=1)
    options: list[RoutingOption] = Field(min_length=1)
    controls: SecurityControls

    @model_validator(mode="after")
    def _validate_references_and_uniqueness(self) -> ArchitectureBlueprint:
        model_ids = [m.id for m in self.models]
        if len(set(model_ids)) != len(model_ids):
            raise ValueError("duplicate model id in models")

        option_ids = [o.id for o in self.options]
        if len(set(option_ids)) != len(option_ids):
            raise ValueError("duplicate option id in options")

        known = set(model_ids)
        for option in self.options:
            for field_name in ("primary_model", "escalation_model", "fallback_model"):
                ref = getattr(option, field_name)
                if ref is not None and ref not in known:
                    raise ValueError(
                        f"option '{option.id}' references unknown model '{ref}' in {field_name}"
                    )
        return self

    def model_map(self) -> dict[str, ModelProfile]:
        """Return declared models keyed by id."""
        return {m.id: m for m in self.models}


def load_blueprint(path: Path) -> ArchitectureBlueprint:
    """Load and validate an ArchitectureBlueprint YAML file."""
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path}: expected a YAML mapping at top level")
    return ArchitectureBlueprint.model_validate(data)
