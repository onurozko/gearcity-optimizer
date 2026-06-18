"""Parse GearCity map TurnEvents.xml timeline files."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from gearcity_optimizer.importers.map_sources import MapSource


class TurnEventsValidationError(ValueError):
    """Raised when TurnEvents XML fails structural validation."""


@dataclass(frozen=True)
class VehiclePopEntry:
    """Vehicle population adjustment for one vehicle type index."""

    selected_index: int
    pop: float | None
    pop_r1: float | None
    pop_r2: float | None
    pop_r3: float | None
    pop_r4: float | None
    pop_r5: float | None
    pop_r6: float | None


@dataclass(frozen=True)
class NewsComment:
    """News headline/body reference from NewsEvts."""

    localization: str
    comment_type: str
    headline: str
    body: str
    image: str


@dataclass(frozen=True)
class CityChange:
    """World city change entry from WorldEvts."""

    city_id: str
    attributes: dict[str, str]


@dataclass(frozen=True)
class TurnEvent:
    """One turn/month of map timeline data."""

    year: int
    turn: int
    buyrate: float | None = None
    stockrate: float | None = None
    interest: float | None = None
    gas: float | None = None
    carprice: float | None = None
    pension_growth: float | None = None
    vehicle_pops: list[VehiclePopEntry] = field(default_factory=list)
    city_changes: list[CityChange] = field(default_factory=list)
    news_comments: list[NewsComment] = field(default_factory=list)
    office_file: str | None = None


@dataclass(frozen=True)
class TurnEventsTimeline:
    """Parsed timeline for one map."""

    map_id: str | None
    map_name: str | None
    source_path: Path
    turns: list[TurnEvent]


def _parse_float(value: str | None) -> float | None:
    if value is None or value == "":
        return None
    return float(value)


def _parse_int(value: str | None) -> int | None:
    if value is None or value == "":
        return None
    return int(value)


def validate_turn_events_xml(xml_content: bytes | str) -> None:
    """Validate TurnEvents XML structure before saving."""
    if isinstance(xml_content, str):
        xml_bytes = xml_content.encode("utf-8")
    else:
        xml_bytes = xml_content

    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as exc:
        raise TurnEventsValidationError(
            "Could not parse XML. Make sure you selected a valid TurnEvents.xml file."
        ) from exc

    if root.tag != "Evts":
        raise TurnEventsValidationError(
            "Invalid TurnEvents file: root element must be <Evts>."
        )

    year_nodes = root.findall("year")
    if not year_nodes:
        raise TurnEventsValidationError(
            "Invalid TurnEvents file: expected at least one <year> node."
        )

    for year_node in year_nodes:
        turn_nodes = year_node.findall("turn")
        if not turn_nodes:
            raise TurnEventsValidationError(
                "Invalid TurnEvents file: each <year> must contain <turn> nodes."
            )


def _parse_vehicle_pop(node: ET.Element) -> VehiclePopEntry:
    return VehiclePopEntry(
        selected_index=int(node.attrib.get("selectedIndex", "0")),
        pop=_parse_float(node.attrib.get("pop")),
        pop_r1=_parse_float(node.attrib.get("popR1")),
        pop_r2=_parse_float(node.attrib.get("popR2")),
        pop_r3=_parse_float(node.attrib.get("popR3")),
        pop_r4=_parse_float(node.attrib.get("popR4")),
        pop_r5=_parse_float(node.attrib.get("popR5")),
        pop_r6=_parse_float(node.attrib.get("popR6")),
    )


def _parse_news_comment(node: ET.Element) -> NewsComment:
    return NewsComment(
        localization=node.attrib.get("localization", ""),
        comment_type=node.attrib.get("type", ""),
        headline=node.attrib.get("headline", ""),
        body=node.attrib.get("body", ""),
        image=node.attrib.get("image", ""),
    )


def _parse_city_change(node: ET.Element) -> CityChange:
    city_id = node.attrib.get("id", "")
    attributes = {key: value for key, value in node.attrib.items() if key != "id"}
    return CityChange(city_id=city_id, attributes=attributes)


def _attr_float(node: ET.Element | None, attr: str) -> float | None:
    if node is None:
        return None
    return _parse_float(node.attrib.get(attr))


def _parse_game_evts(game_evts: ET.Element | None) -> dict[str, object]:
    if game_evts is None:
        return {
            "buyrate": None,
            "stockrate": None,
            "interest": None,
            "gas": None,
            "carprice": None,
            "pension_growth": None,
            "vehicle_pops": [],
            "office_file": None,
        }

    office = game_evts.find("office")
    return {
        "buyrate": _attr_float(game_evts.find("buyrate"), "rate"),
        "stockrate": _attr_float(game_evts.find("stockrate"), "rate"),
        "interest": _attr_float(game_evts.find("interest"), "global"),
        "gas": _attr_float(game_evts.find("gas"), "rate"),
        "carprice": _attr_float(game_evts.find("carprice"), "rate"),
        "pension_growth": _attr_float(game_evts.find("pensionGrowth"), "rate"),
        "vehicle_pops": [
            _parse_vehicle_pop(node) for node in game_evts.findall("vehiclepop")
        ],
        "office_file": office.attrib.get("file") if office is not None else None,
    }


def _parse_turn_node(year: int, turn_node: ET.Element) -> TurnEvent:
    turn = _parse_int(turn_node.attrib.get("t"))
    if turn is None:
        raise TurnEventsValidationError("Each <turn> node must have a turn attribute.")

    game_data = _parse_game_evts(turn_node.find("GameEvts"))
    world_evts = turn_node.find("WorldEvts")
    news_evts = turn_node.find("NewsEvts")

    city_changes: list[CityChange] = []
    if world_evts is not None:
        city_changes = [
            _parse_city_change(node) for node in world_evts.findall("cityChange")
        ]

    news_comments: list[NewsComment] = []
    if news_evts is not None:
        news_comments = [
            _parse_news_comment(node) for node in news_evts.findall("comment")
        ]

    return TurnEvent(
        year=year,
        turn=turn,
        buyrate=game_data["buyrate"],  # type: ignore[arg-type]
        stockrate=game_data["stockrate"],  # type: ignore[arg-type]
        interest=game_data["interest"],  # type: ignore[arg-type]
        gas=game_data["gas"],  # type: ignore[arg-type]
        carprice=game_data["carprice"],  # type: ignore[arg-type]
        pension_growth=game_data["pension_growth"],  # type: ignore[arg-type]
        vehicle_pops=game_data["vehicle_pops"],  # type: ignore[arg-type]
        city_changes=city_changes,
        news_comments=news_comments,
        office_file=game_data["office_file"],  # type: ignore[arg-type]
    )


def parse_turn_events_xml(
    path: Path,
    *,
    map_id: str | None = None,
    map_name: str | None = None,
) -> TurnEventsTimeline:
    """Parse a TurnEvents.xml file into a timeline model."""
    xml_bytes = path.read_bytes()
    validate_turn_events_xml(xml_bytes)
    root = ET.fromstring(xml_bytes)

    turns: list[TurnEvent] = []
    for year_node in root.findall("year"):
        year = _parse_int(year_node.attrib.get("y"))
        if year is None:
            continue
        for turn_node in year_node.findall("turn"):
            turns.append(_parse_turn_node(year, turn_node))

    return TurnEventsTimeline(
        map_id=map_id,
        map_name=map_name,
        source_path=path,
        turns=turns,
    )


def load_turn_events_for_map(map_source: MapSource) -> TurnEventsTimeline:
    """Load the timeline for one discovered map source."""
    return parse_turn_events_xml(
        map_source.turn_events_file,
        map_id=map_source.id,
        map_name=map_source.name,
    )
