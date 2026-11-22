"""Sovereign & regulated LLM architecture validation and TCO economics."""

from __future__ import annotations

from .economics import OptionEconomics, evaluate_blueprint, evaluate_option
from .report import recommend_option, render_json, render_markdown
from .schema import (
    ActionProfile,
    ArchitectureBlueprint,
    DataSensitivity,
    DeploymentMode,
    ModelProfile,
    ResidencyRequirement,
    RoutingOption,
    SecurityControls,
    Severity,
    WorkloadSpec,
    load_blueprint,
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
    "RoutingOption",
    "SecurityControls",
    "Severity",
    "WorkloadSpec",
    "evaluate_blueprint",
    "evaluate_option",
    "load_blueprint",
    "recommend_option",
    "render_json",
    "render_markdown",
    "validate_blueprint",
]
