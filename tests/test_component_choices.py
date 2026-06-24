"""Tests for component choice parsing and design optimizer integration."""

from __future__ import annotations

from pathlib import Path

import pytest

from gearcity_optimizer.core.cost_mode import parse_cost_mode
from gearcity_optimizer.core.models import VehicleType
from gearcity_optimizer.importers.components_xml import (
    audit_components_schema,
    get_available_component_choices,
    parse_component_choice_catalog,
    parse_components_xml,
)
from gearcity_optimizer.reports.component_choice_recommender import (
    EXPERIMENTAL_DISCLAIMER,
    LOW_CONFIDENCE_PAGE_WARNING,
    NO_RELIABLE_AUTO_PICK_WARNING,
    auto_pick_status_label,
    determine_auto_pick_status,
    has_low_confidence_auto_picks,
    recommend_component_choices,
    score_component_suitability,
)
from gearcity_optimizer.reports.design_objective import evaluate_design_objective
from gearcity_optimizer.reports.design_optimizer import DesignOptimizationInput, optimize_design
from gearcity_optimizer.reports.slider_optimizer import PredictedOutput
from gearcity_optimizer.ui.design_optimizer import design_result_to_csv
from gearcity_optimizer.ui.design_session import SESSION_DEFAULTS


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


def test_parser_identifies_engine_choice_types(sample_catalog):
    """Parser should classify fake engine entries by choice_type."""
    choice_catalog = parse_component_choice_catalog(sample_catalog)
    choice_types = {choice.choice_type for choice in choice_catalog.choices}
    assert "engine_layout" in choice_types
    assert "fuel_type" in choice_types
    assert "valvetrain" in choice_types
    assert "forced_induction" in choice_types
    assert "frame" in choice_types
    assert "gearbox_type" in choice_types


def test_available_choices_respect_year_and_skill(sample_catalog):
    """Available choices should shrink at early years and low skills."""
    low = get_available_component_choices(
        1900,
        0.0,
        0.0,
        0.0,
        0.0,
        catalog=sample_catalog,
    )
    high = get_available_component_choices(
        1925,
        100.0,
        100.0,
        100.0,
        100.0,
        catalog=sample_catalog,
    )
    assert len(high) >= len(low)
    low_types = {choice.choice_type for choice in low}
    high_types = {choice.choice_type for choice in high}
    assert "fuel_type" in low_types
    assert "engine_layout" in high_types


def test_component_recommender_returns_engine_choices(sedan_type, sample_catalog):
    """Recommender should rank engine layout/fuel/valvetrain candidates."""
    available = get_available_component_choices(
        1920,
        0.0,
        100.0,
        100.0,
        0.0,
        catalog=sample_catalog,
    )
    result = recommend_component_choices(
        sedan_type,
        "balanced",
        1920,
        {"chassis": 0.0, "engine": 100.0, "gearbox": 100.0, "vehicle": 0.0},
        available,
        component_choice_mode="manual",
    )
    ranked_types = {
        item.choice_type
        for item in result.choices
        if item.candidates
    }
    assert "engine_layout" in ranked_types
    assert "fuel_type" in ranked_types
    assert "valvetrain" in ranked_types
    engine_layout = next(item for item in result.choices if item.choice_type == "engine_layout")
    assert engine_layout.recommended_choice is None
    assert engine_layout.candidates


def test_auto_mode_returns_component_choices_and_slider_controls(
    sedan_type, sample_catalog, monkeypatch, wiki_model_paths
):
    """Auto mode should return both component choices and slider controls."""
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
            gearbox_skill=100.0,
            component_choice_mode="auto",
        )
    )
    assert result.component_choices is not None
    assert result.component_choices.choices
    assert result.slider_result.control_settings
    assert result.slider_result.predicted_outputs


def test_manual_mode_uses_selected_choices(
    sedan_type, sample_catalog, monkeypatch, wiki_model_paths
):
    """Manual mode should honor selected component choices and still optimize sliders."""
    available = get_available_component_choices(
        1920,
        0.0,
        100.0,
        100.0,
        0.0,
        catalog=sample_catalog,
    )
    manual_layout = next(choice for choice in available if choice.choice_type == "engine_layout")
    monkeypatch.setattr(
        "gearcity_optimizer.reports.design_optimizer.get_available_component_choices",
        lambda *args, **kwargs: available,
    )
    result = optimize_design(
        DesignOptimizationInput(
            vehicle_type=sedan_type,
            year=1920,
            cost_mode="balanced",
            engine_skill=100.0,
            gearbox_skill=100.0,
            component_choice_mode="manual",
            manual_choices={"engine_layout": manual_layout},
        )
    )
    engine_layout = next(
        item
        for item in result.component_choices.choices
        if item.choice_type == "engine_layout"
    )
    assert engine_layout.recommended_choice is not None
    assert engine_layout.recommended_choice.display_name == manual_layout.display_name
    assert result.slider_result.control_settings


def test_outputs_separate_from_controls_and_choices(sedan_type, sample_catalog, monkeypatch):
    """Predicted outputs must stay separate from slider controls and component choices."""
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
            gearbox_skill=100.0,
        )
    )
    control_labels = {item.label.lower() for item in result.slider_result.control_settings}
    forbidden = {"displacement", "horsepower", "cargo", "overall", "driveability"}
    assert not forbidden & control_labels


def test_csv_export_separates_record_types(sedan_type, sample_catalog, monkeypatch, wiki_model_paths):
    """CSV export should include component choices, slider controls, and predicted outputs."""
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
            gearbox_skill=100.0,
        )
    )
    csv_text = design_result_to_csv(result)
    assert "component_choice" in csv_text
    assert "slider_control" in csv_text
    assert "predicted_output" in csv_text


def test_schema_audit_reports_sections(fixture_xml_path: Path):
    """Schema audit should list top-level tags and guessed categories."""
    audit = audit_components_schema(fixture_xml_path)
    assert audit.root_tag == "Components"
    assert audit.sections
    engine_section = next(
        section for section in audit.sections if section.section_tag == "EngineComponents"
    )
    assert "engine_layout" in engine_section.guessed_choice_types
    assert "fuel_type" in engine_section.guessed_choice_types


def test_balanced_sedan_1920_does_not_auto_pick_single_layout(sedan_type, sample_catalog):
    """SingleLayout should not be the recommended high-confidence pick for balanced Sedan in 1920."""
    available = get_available_component_choices(
        1920,
        0.0,
        100.0,
        100.0,
        0.0,
        catalog=sample_catalog,
    )
    result = recommend_component_choices(
        sedan_type,
        "balanced",
        1920,
        {"chassis": 0.0, "engine": 100.0, "gearbox": 100.0, "vehicle": 0.0},
        available,
        component_choice_mode="auto",
    )
    engine_layout = next(item for item in result.choices if item.choice_type == "engine_layout")
    assert engine_layout.top_candidate is not None
    assert engine_layout.auto_pick_enabled
    assert "SingleLayout" not in engine_layout.top_candidate.display_name
    assert engine_layout.auto_pick_status != "recommended" or engine_layout.candidates[0].total_score >= 70
    assert engine_layout.recommended_choice is None or engine_layout.auto_pick_status == "recommended"
    single = next(
        item for item in engine_layout.candidates if "SingleLayout" in item.component_name
    )
    assert single.penalties
    assert single.total_score < engine_layout.candidates[0].total_score


def test_auto_pick_mode_still_recommends_choices(sedan_type, sample_catalog):
    """Auto-pick mode should rank choices and expose top candidates for each choice type."""
    available = get_available_component_choices(
        1920,
        0.0,
        100.0,
        100.0,
        0.0,
        catalog=sample_catalog,
    )
    result = recommend_component_choices(
        sedan_type,
        "balanced",
        1920,
        {"chassis": 0.0, "engine": 100.0, "gearbox": 100.0, "vehicle": 0.0},
        available,
        component_choice_mode="auto",
    )
    ranked = [item for item in result.choices if item.top_candidate is not None]
    assert ranked
    assert all(item.auto_pick_enabled for item in ranked)
    assert any(
        EXPERIMENTAL_DISCLAIMER in warning for warning in result.warnings
    )


def test_auto_pick_is_labeled_experimental():
    """UI and recommender should expose the experimental auto-pick label."""
    from gearcity_optimizer.reports.component_choice_recommender import EXPERIMENTAL_DISCLAIMER
    from gearcity_optimizer.ui.design_session import (
        AUTO_PICK_EXPERIMENTAL_LABEL,
        COMPONENT_CHOICE_MODE_OPTIONS,
        SESSION_DEFAULTS,
    )

    assert "experimental" in AUTO_PICK_EXPERIMENTAL_LABEL.lower()
    assert "validated" in AUTO_PICK_EXPERIMENTAL_LABEL.lower()
    assert SESSION_DEFAULTS["component_choice_mode"] == COMPONENT_CHOICE_MODE_OPTIONS[0]
    assert "experimental" in COMPONENT_CHOICE_MODE_OPTIONS[0].lower()
    assert "experimental" in EXPERIMENTAL_DISCLAIMER.lower()


def test_auto_pick_is_deterministic(sedan_type, sample_catalog):
    """Same inputs should produce the same auto-pick recommendations."""
    available = get_available_component_choices(
        1920,
        0.0,
        100.0,
        100.0,
        0.0,
        catalog=sample_catalog,
    )
    kwargs = {
        "vehicle_type": sedan_type,
        "cost_mode": "balanced",
        "year": 1920,
        "skills": {"chassis": 0.0, "engine": 100.0, "gearbox": 100.0, "vehicle": 0.0},
        "available_choices": available,
        "component_choice_mode": "auto",
    }
    first = recommend_component_choices(**kwargs)
    second = recommend_component_choices(**kwargs)
    first_picks = {
        item.choice_type: item.top_candidate.display_name
        for item in first.choices
        if item.top_candidate is not None
    }
    second_picks = {
        item.choice_type: item.top_candidate.display_name
        for item in second.choices
        if item.top_candidate is not None
    }
    assert first_picks == second_picks


def test_optimizer_has_no_llm_dependency():
    """Core deterministic scorer modules should not depend on LLM/Ollama packages."""
    import gearcity_optimizer.reports.component_choice_recommender as recommender
    import gearcity_optimizer.reports.design_objective as design_objective

    for module in (recommender, design_objective):
        source = module.__file__
        assert source is not None
        text = Path(source).read_text(encoding="utf-8").lower()
        assert "ollama" not in text
        assert "openai" not in text
        assert "langchain" not in text


def test_single_layout_receives_penalty_and_low_suitability(sedan_type, sample_catalog):
    """Primitive SingleLayout should score lower than mainstream layouts for Sedan."""
    available = get_available_component_choices(
        1920,
        0.0,
        100.0,
        100.0,
        0.0,
        catalog=sample_catalog,
    )
    layouts = [choice for choice in available if choice.choice_type == "engine_layout"]
    single = next(choice for choice in layouts if "SingleLayout" in choice.display_name)
    straight = next(choice for choice in layouts if "StraightLayout" in choice.display_name)
    single_score = score_component_suitability(
        single,
        vehicle_type=sedan_type,
        cost_mode=parse_cost_mode("balanced"),
        year=1920,
        candidates=layouts,
    )
    straight_score = score_component_suitability(
        straight,
        vehicle_type=sedan_type,
        cost_mode=parse_cost_mode("balanced"),
        year=1920,
        candidates=layouts,
    )
    assert "primitive/small layout" in single_score.penalties
    assert single_score.total_score < straight_score.total_score
    assert single_score.confidence == "low"


def test_auto_pick_candidates_include_suitability_scores(sedan_type, sample_catalog):
    """Auto mode should expose suitability scores and penalties on candidates."""
    available = get_available_component_choices(
        1920,
        0.0,
        100.0,
        100.0,
        0.0,
        catalog=sample_catalog,
    )
    result = recommend_component_choices(
        sedan_type,
        "balanced",
        1920,
        {"chassis": 0.0, "engine": 100.0, "gearbox": 100.0, "vehicle": 0.0},
        available,
        component_choice_mode="auto",
    )
    engine_layout = next(item for item in result.choices if item.choice_type == "engine_layout")
    assert engine_layout.candidates
    top = engine_layout.candidates[0]
    assert top.total_score >= 0.0
    assert isinstance(top.penalties, list)
    assert isinstance(top.reasons, list)


def test_low_suitability_is_not_labeled_recommended():
    """Scores below 50 should not receive recommended status."""
    assert determine_auto_pick_status(49.0, "medium") == "low_confidence_candidate"
    assert determine_auto_pick_status(21.8, "low") == "not_recommended"
    assert auto_pick_status_label("low_confidence_candidate") == "No reliable recommendation"


def test_csv_exports_auto_pick_status_not_clean_recommendation(
    sedan_type, sample_catalog, monkeypatch, wiki_model_paths
):
    """CSV should include auto_pick_status instead of a bare recommended choice column."""
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
            gearbox_skill=100.0,
            component_choice_mode="auto",
        )
    )
    csv_text = design_result_to_csv(result)
    assert "auto_pick_status" in csv_text
    assert "suggested_choice_or_top_candidate" in csv_text
    assert "Recommended choice" not in csv_text.splitlines()[0]


def test_single_layout_below_50_shows_no_reliable_recommendation(sedan_type, sample_catalog):
    """1920 Balanced Sedan should not treat SingleLayout as a reliable recommendation."""
    available = get_available_component_choices(
        1920,
        0.0,
        100.0,
        100.0,
        0.0,
        catalog=sample_catalog,
    )
    layouts = [choice for choice in available if choice.choice_type == "engine_layout"]
    single = next(choice for choice in layouts if "SingleLayout" in choice.display_name)
    single_score = score_component_suitability(
        single,
        vehicle_type=sedan_type,
        cost_mode=parse_cost_mode("balanced"),
        year=1920,
        candidates=layouts,
    )
    assert single_score.total_score < 50
    status = determine_auto_pick_status(single_score.total_score, "low")
    assert status in {"low_confidence_candidate", "not_recommended"}
    assert auto_pick_status_label(status) == "No reliable recommendation"


def test_page_warning_when_any_auto_pick_is_low_confidence(sedan_type, sample_catalog):
    """Low-confidence auto-picks should trigger the page-level warning."""
    available = get_available_component_choices(
        1920,
        0.0,
        100.0,
        100.0,
        0.0,
        catalog=sample_catalog,
    )
    result = recommend_component_choices(
        sedan_type,
        "balanced",
        1920,
        {"chassis": 0.0, "engine": 100.0, "gearbox": 100.0, "vehicle": 0.0},
        available,
        component_choice_mode="auto",
    )
    layouts = [choice for choice in available if choice.choice_type == "engine_layout"]
    single = next(choice for choice in layouts if "SingleLayout" in choice.display_name)
    single_only = recommend_component_choices(
        sedan_type,
        "balanced",
        1920,
        {"chassis": 0.0, "engine": 100.0, "gearbox": 100.0, "vehicle": 0.0},
        [choice for choice in available if choice.choice_type != "engine_layout"] + [single],
        component_choice_mode="auto",
    )
    assert has_low_confidence_auto_picks(single_only)
    assert LOW_CONFIDENCE_PAGE_WARNING in single_only.warnings
    assert any(
        NO_RELIABLE_AUTO_PICK_WARNING in item.warnings
        for item in single_only.choices
        if item.choice_type == "engine_layout"
    )
    assert not has_low_confidence_auto_picks(result) or LOW_CONFIDENCE_PAGE_WARNING in result.warnings


def test_novalve_penalized_for_mainstream_passenger(sedan_type, sample_catalog):
    """NoValve should score poorly for mainstream passenger vehicles when alternatives exist."""
    available = get_available_component_choices(
        1920,
        0.0,
        100.0,
        100.0,
        0.0,
        catalog=sample_catalog,
    )
    valvetrains = [choice for choice in available if choice.choice_type == "valvetrain"]
    novalve = next(choice for choice in valvetrains if "NoValve" in choice.display_name)
    score = score_component_suitability(
        novalve,
        vehicle_type=sedan_type,
        cost_mode=parse_cost_mode("balanced"),
        year=1920,
        candidates=valvetrains,
    )
    assert "primitive valvetrain" in score.penalties
    assert score.total_score < 50


def test_higher_gear_count_scores_above_lower_for_passenger(sedan_type):
    """Gear count should rank by torque capacity, not era fit alone."""
    from gearcity_optimizer.importers.component_choices import ComponentChoice

    def _gear(name: str, gears: int) -> ComponentChoice:
        return ComponentChoice(
            id=name,
            name=name,
            display_name=f"{gears} Gear",
            section="gearbox",
            choice_type="gear_count",
            start_year=1890,
            end_year=5050,
            required_skill=0.0,
            stats={"gears": float(gears)},
            raw_attributes={"picture": f"{name}.dds"},
            source_path="test",
            confidence="high",
        )

    three = _gear("3Gear", 3)
    six = _gear("6Gear", 6)
    candidates = [three, six]
    three_score = score_component_suitability(
        three,
        vehicle_type=sedan_type,
        cost_mode=parse_cost_mode("balanced"),
        year=1920,
        candidates=candidates,
    )
    six_score = score_component_suitability(
        six,
        vehicle_type=sedan_type,
        cost_mode=parse_cost_mode("balanced"),
        year=1920,
        candidates=candidates,
    )
    assert six_score.total_score > three_score.total_score
    assert "torque capacity" in " ".join(six_score.reasons).lower()


def test_auto_pick_mode_is_default():
    """Auto-pick experimental should be the default session and optimizer mode."""
    from gearcity_optimizer.ui.design_session import COMPONENT_CHOICE_MODE_OPTIONS

    assert SESSION_DEFAULTS["component_choice_mode"] == "Auto-pick components (experimental)"
    assert SESSION_DEFAULTS["component_choice_mode"] == COMPONENT_CHOICE_MODE_OPTIONS[0]
    assert DesignOptimizationInput(
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
        year=1920,
        cost_mode="balanced",
    ).component_choice_mode == "auto"


def test_bad_predicted_fuel_triggers_warning(sedan_type):
    """Low predicted fuel for a high-fuel-priority vehicle should warn."""
    evaluation = evaluate_design_objective(
        sedan_type,
        [
            PredictedOutput(
                output_key="fuel",
                label="Fuel",
                value=15.0,
                target_weight=0.65,
                reason="test",
                is_proxy=False,
            ),
            PredictedOutput(
                output_key="overall",
                label="Overall",
                value=31.0,
                target_weight=0.4,
                reason="test",
                is_proxy=False,
            ),
        ],
    )
    assert evaluation.warnings
    assert any("Fuel" in warning for warning in evaluation.warnings)
    assert "Fuel" in evaluation.poor_priority_stats


def test_objective_score_drops_for_low_priority_stats(sedan_type):
    """Objective score should fall when high-priority predicted stats are low."""
    good = evaluate_design_objective(
        sedan_type,
        [
            PredictedOutput(
                output_key="fuel",
                label="Fuel",
                value=75.0,
                target_weight=0.65,
                reason="test",
                is_proxy=False,
            )
        ],
    )
    poor = evaluate_design_objective(
        sedan_type,
        [
            PredictedOutput(
                output_key="fuel",
                label="Fuel",
                value=10.0,
                target_weight=0.65,
                reason="test",
                is_proxy=False,
            )
        ],
    )
    assert poor.objective_score < good.objective_score


def test_schema_audit_reports_choice_type_counts(fixture_xml_path: Path):
    """Schema audit should include choice_type counts and sample names."""
    audit = audit_components_schema(fixture_xml_path)
    assert audit.choice_type_audit is not None
    assert audit.choice_type_audit.total_entries > 0
    engine_layout = next(
        row
        for row in audit.choice_type_audit.choice_types
        if row.choice_type == "engine_layout"
    )
    assert engine_layout.count >= 3
    assert any("Layout" in name for name in engine_layout.sample_names)


def test_cli_components_schema_audit_registered():
    from gearcity_optimizer.cli import SUBCOMMANDS

    assert "components-schema-audit" in SUBCOMMANDS
    assert "optimize-design" in SUBCOMMANDS
