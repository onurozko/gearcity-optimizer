"""Tests for LLM fast-path optimization."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from gearcity_optimizer.core.models import VehicleType
from gearcity_optimizer.importers.components_xml import get_available_component_choices, parse_components_xml
from gearcity_optimizer.llm.config import LLMConfig
from gearcity_optimizer.llm.strategy_client import parse_llm_strategy_response
from gearcity_optimizer.reports.design_optimizer import DesignOptimizationInput, optimize_design
from gearcity_optimizer.reports.slider_optimizer import _depth_search_params, _hill_climb_slider_limit

VALID_STRATEGY_JSON = json.dumps(
    {
        "component_choices": [
            {
                "section": "engine",
                "choice_type": "engine_layout",
                "recommended_choice": "StraightLayout",
                "alternatives": ["FlatLayout"],
                "reason": "mainstream balanced sedan layout",
                "confidence": "medium",
            }
        ],
        "slider_guidance": [],
        "expected_tradeoffs": [],
        "risks": [],
        "explanation": "Prefer mainstream practical components for a balanced sedan.",
    }
)


@pytest.fixture
def fixture_xml_path() -> Path:
    return (
        Path(__file__).resolve().parent
        / "fixtures"
        / "components"
        / "sample_components.xml"
    )


@pytest.fixture
def sample_catalog(fixture_xml_path: Path):
    return parse_components_xml(fixture_xml_path)


@pytest.fixture
def sedan_type() -> VehicleType:
    return VehicleType(
        name="Sedan",
        performance=0.4,
        drivability=0.4,
        luxury=0.45,
        safety=0.65,
        fuel=0.65,
        power=0.45,
        cargo=0.5,
        dependability=0.45,
        wealth_demo=4,
        military_fleet=False,
        civilian_fleet=True,
    )


def test_llm_depth_uses_minimal_search_params():
    assert _depth_search_params("llm") == (2, 1, 3, 1)
    assert _hill_climb_slider_limit("llm") == 12
    assert _hill_climb_slider_limit("quick") == 18
    assert _hill_climb_slider_limit("balanced") is None


def test_llm_mode_uses_fast_path_when_choices_accepted(
    sedan_type, sample_catalog, monkeypatch, wiki_model_paths
):
    available = get_available_component_choices(
        1920, 0.0, 100.0, 100.0, 0.0, catalog=sample_catalog
    )
    monkeypatch.setattr(
        "gearcity_optimizer.reports.design_optimizer.get_available_component_choices",
        lambda *args, **kwargs: available,
    )
    strategy = parse_llm_strategy_response(VALID_STRATEGY_JSON)
    config = LLMConfig(enabled=True, backend="ollama", model="llama3.2")

    with patch(
        "gearcity_optimizer.llm.strategy_validator.request_llm_strategy",
        return_value=strategy,
    ), patch(
        "gearcity_optimizer.reports.design_optimizer.search_best_complete_design",
    ) as mock_search:
        mock_search.return_value.best = None
        mock_search.return_value.alternatives = []
        mock_search.return_value.searched_component_sets = 1
        mock_search.return_value.warnings = []

        optimize_design(
            DesignOptimizationInput(
                vehicle_type=sedan_type,
                year=1920,
                cost_mode="balanced",
                engine_skill=100.0,
                depth="thorough",
                recommendation_mode="llm",
                llm_config=config,
            )
        )

        assert mock_search.call_count == 1
        call_kwargs = mock_search.call_args.kwargs
        assert call_kwargs["depth"] == "llm"
        assert call_kwargs["max_alternatives"] == 0
        assert "engine_layout" in call_kwargs["manual_choices"]
