"""Sovereign & regulated LLM architecture validation and TCO economics."""

from __future__ import annotations

from .economics import OptionEconomics, evaluate_blueprint, evaluate_option, option_routed_tokens
from .report import recommend_option, render_json, render_markdown
from .schema import (
    ActionProfile,
    ArchitectureBlueprint,
    DataSensitivity,
    DeploymentMode,
    ModelProfile,
    ResidencyRequirement,
    RoutingMode,
    RoutingOption,
    SecurityControls,
    Severity,
    WorkloadSpec,
    load_blueprint,
)
from .sensitivity import (
    SensitivityReport,
    VolumePoint,
    analyze_sensitivity,
    render_sensitivity_json,
    render_sensitivity_markdown,
)
from .validator import Finding, validate_blueprint

__all__ = [
    "ActionProfile",
    "ArchitectureBlueprint",
    "DataSensitivity",
    "DeploymentMode",
    "Finding",
    "ModelProfile",
    "OptionEconomics",
    "ResidencyRequirement",
    "RoutingMode",
    "RoutingOption",
    "SecurityControls",
    "SensitivityReport",
    "Severity",
    "VolumePoint",
    "WorkloadSpec",
    "analyze_sensitivity",
    "evaluate_blueprint",
    "evaluate_option",
    "load_blueprint",
    "option_routed_tokens",
    "recommend_option",
    "render_json",
    "render_markdown",
    "render_sensitivity_json",
    "render_sensitivity_markdown",
    "validate_blueprint",
]
