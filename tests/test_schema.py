"""Schema validation tests."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from ai_systems_arch.schema import ArchitectureBlueprint, load_blueprint
from tests.conftest import EXAMPLES, sample_blueprint_dict


def test_all_example_blueprints_load_and_validate() -> None:
    files = sorted(EXAMPLES.glob("*.yaml"))
    assert len(files) == 3
    for path in files:
        bp = load_blueprint(path)
        assert bp.workload.monthly_requests > 0


def test_rejects_unknown_fields() -> None:
    raw = sample_blueprint_dict()
    raw["workload"]["unexpected_field"] = 123
    with pytest.raises(ValidationError):
        ArchitectureBlueprint.model_validate(raw)


def test_rejects_unknown_model_reference() -> None:
    raw = sample_blueprint_dict()
    raw["options"][0]["fallback_model"] = "does-not-exist"
    with pytest.raises(ValidationError, match="unknown model"):
        ArchitectureBlueprint.model_validate(raw)


def test_rejects_duplicate_model_ids() -> None:
    raw = sample_blueprint_dict()
    raw["models"].append(dict(raw["models"][0]))
    with pytest.raises(ValidationError, match="duplicate model id"):
        ArchitectureBlueprint.model_validate(raw)


def test_rejects_escalation_rate_mismatch() -> None:
    raw = sample_blueprint_dict()
    raw["options"][0]["escalation_rate"] = 0.2
    with pytest.raises(ValidationError, match=r"escalation_rate must be 0\.0"):
        ArchitectureBlueprint.model_validate(raw)

    raw2 = sample_blueprint_dict()
    raw2["options"][0]["escalation_model"] = "m-fallback"
    raw2["options"][0]["escalation_rate"] = 0.0
    with pytest.raises(ValidationError, match=r"escalation_rate must be > 0\.0"):
        ArchitectureBlueprint.model_validate(raw2)
