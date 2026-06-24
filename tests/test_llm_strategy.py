"""Tests for optional LLM-assisted design strategy layer."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import requests

from gearcity_optimizer.core.models import VehicleType
from gearcity_optimizer.importers.components_xml import (
    get_available_component_choices,
    parse_components_xml,
)
from gearcity_optimizer.llm.config import (
    LLMConfig,
    LLM_NOT_CONFIGURED_MESSAGE,
    is_llm_configured,
    normalize_llm_base_url,
    resolve_llm_config,
)
from gearcity_optimizer.llm.strategy_client import (
    LLMStrategyParseError,
    build_design_strategy_prompt,
    call_ollama_strategy,
    list_ollama_models,
    parse_llm_strategy_response,
    request_llm_strategy,
)
from gearcity_optimizer.llm.strategy_context import build_design_strategy_context
from gearcity_optimizer.llm.strategy_validator import (
    run_llm_assisted_strategy,
    validate_llm_slider_guidance,
    validate_llm_strategy,
)
from gearcity_optimizer.reports.design_optimizer import DesignOptimizationInput, optimize_design
from gearcity_optimizer.reports.slider_optimizer import list_sliders
from gearcity_optimizer.ui.design_session import RECOMMENDATION_MODE_OPTIONS, SESSION_DEFAULTS


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
        "slider_guidance": [
            {
                "section": "engine",
                "slider_label": "Fuel Economy",
                "direction": "higher",
                "suggested_range": [60, 85],
                "reason": "fuel is a high priority for Sedan",
            }
        ],
        "expected_tradeoffs": ["more fuel focus may reduce peak performance"],
        "risks": ["primitive layouts should be avoided"],
        "explanation": "Prefer mainstream practical components for a balanced sedan.",
    }
)


def test_normalize_llm_base_url_fixes_windows_style_urls():
    assert (
        normalize_llm_base_url(r"http:\localhost:11434/", backend="ollama")
        == "http://localhost:11434"
    )
    assert normalize_llm_base_url("", backend="ollama") == "http://localhost:11434"


def test_resolve_llm_config_uses_safe_ollama_defaults():
    config = resolve_llm_config(
        enabled=True,
        backend="ollama",
        model="",
        base_url=r"http:\localhost:11434/",
    )
    assert config.base_url == "http://localhost:11434"
    assert config.model == "llama3:latest"


def test_llm_mode_optional_without_ollama(sedan_type, sample_catalog, monkeypatch, wiki_model_paths):
    """App should work in deterministic mode without any LLM backend."""
    monkeypatch.setattr(
        "gearcity_optimizer.reports.design_optimizer.get_available_component_choices",
        lambda *args, **kwargs: get_available_component_choices(
            1920, 0.0, 100.0, 100.0, 0.0, catalog=sample_catalog
        ),
    )
    result = optimize_design(
        DesignOptimizationInput(
            vehicle_type=sedan_type,
            year=1920,
            cost_mode="balanced",
            engine_skill=100.0,
            recommendation_mode="deterministic",
            llm_config=LLMConfig(enabled=False, backend="none"),
        )
    )
    assert result.recommendation_mode == "deterministic"
    assert result.llm_validation is None
    assert result.slider_result.control_settings


def test_deterministic_only_default_recommendation_mode():
    """Deterministic-only should remain the default recommendation mode."""
    assert SESSION_DEFAULTS["recommendation_mode"] == "Deterministic only"
    assert RECOMMENDATION_MODE_OPTIONS[0] == "Deterministic only"


def test_parse_llm_strategy_accepts_valid_json():
    """Parser should accept valid LLM strategy JSON."""
    strategy = parse_llm_strategy_response(VALID_STRATEGY_JSON)
    assert strategy.component_choices
    assert strategy.component_choices[0].recommended_choice == "StraightLayout"
    assert strategy.slider_guidance
    assert strategy.explanation


def test_parse_llm_strategy_rejects_invalid_json():
    """Parser should reject invalid JSON with a helpful error."""
    with pytest.raises(LLMStrategyParseError, match="valid JSON"):
        parse_llm_strategy_response("not json at all")


def test_validator_rejects_unavailable_component_choice(sample_catalog):
    """Validator should reject component choices not in the available catalog."""
    available = get_available_component_choices(
        1920, 0.0, 100.0, 100.0, 0.0, catalog=sample_catalog
    )
    strategy = parse_llm_strategy_response(
        json.dumps(
            {
                "component_choices": [
                    {
                        "section": "engine",
                        "choice_type": "engine_layout",
                        "recommended_choice": "ImaginaryLayout",
                        "alternatives": [],
                        "reason": "bad",
                        "confidence": "high",
                    }
                ],
                "slider_guidance": [],
                "expected_tradeoffs": [],
                "risks": [],
                "explanation": "",
            }
        )
    )
    validations, accepted, warnings = validate_llm_strategy(
        strategy,
        available_choices=available,
    )
    assert not accepted
    assert validations[0].validation_status == "rejected"
    assert warnings


def test_validator_rejects_unknown_slider_label():
    """Validator should reject slider labels not in the wiki registry."""
    strategy = parse_llm_strategy_response(
        json.dumps(
            {
                "component_choices": [],
                "slider_guidance": [
                    {
                        "section": "engine",
                        "slider_label": "Totally Fake Slider",
                        "direction": "higher",
                        "reason": "bad",
                    }
                ],
                "expected_tradeoffs": [],
                "risks": [],
                "explanation": "",
            }
        )
    )
    validations, accepted, warnings = validate_llm_slider_guidance(strategy)
    assert not accepted
    assert validations[0].validation_status == "rejected"
    assert warnings


def test_validator_accepts_available_choice_and_real_slider(
    sample_catalog, wiki_model_paths
):
    """Validator should accept available component choices and real slider labels."""
    available = get_available_component_choices(
        1920, 0.0, 100.0, 100.0, 0.0, catalog=sample_catalog
    )
    engine_slider = next(slider for slider in list_sliders(section="engine"))
    strategy = parse_llm_strategy_response(
        json.dumps(
            {
                "component_choices": [
                    {
                        "section": "engine",
                        "choice_type": "engine_layout",
                        "recommended_choice": "StraightLayout",
                        "alternatives": [],
                        "reason": "good",
                        "confidence": "medium",
                    }
                ],
                "slider_guidance": [
                    {
                        "section": "engine",
                        "slider_label": engine_slider.label,
                        "direction": "higher",
                        "reason": "good",
                    }
                ],
                "expected_tradeoffs": [],
                "risks": [],
                "explanation": "",
            }
        )
    )
    component_validations, accepted_choices, _ = validate_llm_strategy(
        strategy,
        available_choices=available,
    )
    slider_validations, accepted_guidance, _ = validate_llm_slider_guidance(strategy)
    assert accepted_choices["engine_layout"].display_name == "StraightLayout"
    assert component_validations[0].validation_status == "accepted"
    assert accepted_guidance
    assert slider_validations[0].validation_status in {"accepted", "modified"}


def test_ollama_unavailable_returns_warning_not_crash(sedan_type, sample_catalog):
    """Unavailable Ollama should return a friendly warning instead of crashing."""
    available = get_available_component_choices(
        1920, 0.0, 100.0, 100.0, 0.0, catalog=sample_catalog
    )
    config = LLMConfig(enabled=True, backend="ollama", model="llama3.2")
    with patch(
        "gearcity_optimizer.llm.strategy_validator.request_llm_strategy",
        side_effect=requests.ConnectionError("connection refused"),
    ):
        result = run_llm_assisted_strategy(
            vehicle_type=sedan_type,
            cost_mode="balanced",
            year=1920,
            skills={"chassis": 0.0, "engine": 100.0, "gearbox": 100.0, "vehicle": 0.0},
            available_choices=available,
            deterministic_result=None,
            deterministic_warnings=[],
            config=config,
        )
    assert not result.llm_available
    assert result.llm_error
    assert "failed" in result.llm_error.lower() or "connection" in result.llm_error.lower()


def test_llm_not_configured_message_when_disabled():
    """Disabled LLM config should report not configured."""
    assert not is_llm_configured(LLMConfig(enabled=False, backend="none"))
    result = run_llm_assisted_strategy(
        vehicle_type=VehicleType(
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
        ),
        cost_mode="balanced",
        year=1920,
        skills={"chassis": 0.0, "engine": 0.0, "gearbox": 0.0, "vehicle": 0.0},
        available_choices=[],
        deterministic_result=None,
        deterministic_warnings=[],
        config=LLMConfig(enabled=False, backend="none"),
    )
    assert LLM_NOT_CONFIGURED_MESSAGE in result.warnings[0]


def test_deterministic_validator_runs_after_llm_strategy(
    sedan_type, sample_catalog, monkeypatch, wiki_model_paths
):
    """LLM-assisted optimize_design should still compute deterministic slider outputs."""
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
    ):
        result = optimize_design(
            DesignOptimizationInput(
                vehicle_type=sedan_type,
                year=1920,
                cost_mode="balanced",
                engine_skill=100.0,
                recommendation_mode="llm",
                llm_config=config,
            )
        )
    assert result.llm_validation is not None
    assert result.llm_validation.accepted_choices
    assert result.slider_result.predicted_outputs
    assert result.objective is not None


def test_build_design_strategy_prompt_includes_compact_context(sedan_type, sample_catalog):
    """Prompt builder should include compact structured context, not raw XML."""
    available = get_available_component_choices(
        1920, 0.0, 100.0, 100.0, 0.0, catalog=sample_catalog
    )
    context = build_design_strategy_context(
        vehicle_type=sedan_type,
        cost_mode="balanced",
        year=1920,
        skills={"chassis": 80.0, "engine": 80.0, "gearbox": 80.0, "vehicle": 80.0},
        available_choices=available,
    )
    prompt = build_design_strategy_prompt(context)
    assert "Sedan" in prompt
    assert "available_choices" in prompt
    assert "<Components>" not in prompt
    assert "StraightLayout" in prompt or "SingleLayout" in prompt


def test_request_llm_strategy_uses_ollama_mock(sedan_type, sample_catalog):
    """Ollama calls should be mockable for tests."""
    available = get_available_component_choices(
        1920, 0.0, 100.0, 100.0, 0.0, catalog=sample_catalog
    )
    context = build_design_strategy_context(
        vehicle_type=sedan_type,
        cost_mode="balanced",
        year=1920,
        skills={"chassis": 0.0, "engine": 100.0, "gearbox": 100.0, "vehicle": 0.0},
        available_choices=available,
    )
    config = LLMConfig(enabled=True, backend="ollama", model="llama3.2")
    mock_response = MagicMock()
    mock_response.json.return_value = {"response": VALID_STRATEGY_JSON}
    mock_response.raise_for_status = MagicMock()
    with patch("gearcity_optimizer.llm.strategy_client.requests.post", return_value=mock_response):
        strategy = request_llm_strategy(context, config)
    assert strategy.component_choices[0].recommended_choice == "StraightLayout"


def test_ollama_model_not_found_returns_helpful_error():
    """Ollama 404 for missing model should explain available models."""
    config = LLMConfig(enabled=True, backend="ollama", model="llama3.2")
    mock_tags = MagicMock()
    mock_tags.json.return_value = {"models": [{"name": "llama3:latest"}]}
    mock_tags.raise_for_status = MagicMock()
    mock_generate = MagicMock()
    mock_generate.ok = False
    mock_generate.status_code = 404
    mock_generate.json.return_value = {"error": "model 'llama3.2' not found"}
    mock_generate.text = '{"error":"model \'llama3.2\' not found"}'

    with patch(
        "gearcity_optimizer.llm.strategy_client.requests.get",
        return_value=mock_tags,
    ), patch(
        "gearcity_optimizer.llm.strategy_client.requests.post",
        return_value=mock_generate,
    ), pytest.raises(RuntimeError, match="not installed") as exc:
        call_ollama_strategy({"vehicle_type": "Sedan"}, config)
    assert "llama3:latest" in str(exc.value)


def test_list_ollama_models_parses_tags_response():
    """Tags endpoint should return installed model names."""
    config = LLMConfig(backend="ollama", model="llama3:latest")
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "models": [{"name": "llama3:latest"}, {"name": "mistral:latest"}]
    }
    mock_response.raise_for_status = MagicMock()
    with patch(
        "gearcity_optimizer.llm.strategy_client.requests.get",
        return_value=mock_response,
    ):
        assert list_ollama_models(config) == ["llama3:latest", "mistral:latest"]


def test_core_scorer_modules_have_no_llm_backend_dependency():
    """Core deterministic scorer modules should not call Ollama/OpenAI directly."""
    import gearcity_optimizer.reports.component_choice_recommender as recommender
    import gearcity_optimizer.reports.design_objective as design_objective

    for module in (recommender, design_objective):
        source = Path(module.__file__).read_text(encoding="utf-8").lower()
        assert "ollama" not in source
        assert "openai" not in source
        assert "langchain" not in source
