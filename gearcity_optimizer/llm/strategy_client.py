"""LLM strategy client: prompt building, Ollama calls, and JSON parsing."""

from __future__ import annotations

import json
import re
from typing import Any

import requests

from gearcity_optimizer.llm.config import (
    DEFAULT_OLLAMA_BASE_URL,
    LLMConfig,
    is_llm_configured,
)
from gearcity_optimizer.llm.strategy_models import (
    LLMComponentChoice,
    LLMDesignStrategy,
    LLMSliderGuidance,
)

STRATEGY_JSON_SCHEMA_HINT = """
Return a single JSON object with this shape:
{
  "component_choices": [
    {
      "section": "engine",
      "choice_type": "engine_layout",
      "recommended_choice": "StraightLayout",
      "alternatives": ["FlatLayout"],
      "reason": "short reason",
      "confidence": "medium"
    }
  ],
  "slider_guidance": [
    {
      "section": "engine",
      "slider_label": "Fuel Economy",
      "direction": "higher",
      "suggested_range": [60, 85],
      "reason": "short reason"
    }
  ],
  "expected_tradeoffs": ["tradeoff text"],
  "risks": ["risk text"],
  "explanation": "short overall strategy summary"
}
""".strip()


class LLMStrategyParseError(ValueError):
    """Raised when LLM strategy JSON cannot be parsed."""


def build_design_strategy_prompt(context: dict[str, Any]) -> str:
    """Build the strategy prompt from compact structured context."""
    return _build_strategy_prompt(context, repair_mode=False)


def build_design_repair_prompt(context: dict[str, Any]) -> str:
    """Build a repair prompt when the previous design failed constraints."""
    return _build_strategy_prompt(context, repair_mode=True)


def _build_strategy_prompt(context: dict[str, Any], *, repair_mode: bool) -> str:
    """Build strategy or repair prompt from compact structured context."""
    context_json = json.dumps(context, indent=2, sort_keys=True)
    if repair_mode:
        lead = (
            "You are REPAIRING a failed GearCity vehicle design.\n"
            "The previous design violated physical constraints. Propose a new strategy "
            "that fixes every failure listed in physical_fit_failures.\n"
        )
    else:
        lead = (
            "You are assisting a GearCity vehicle design optimizer.\n"
            "Designs must be physically feasible: engine torque must not exceed gearbox "
            "max torque support, and engine size must fit the chassis bay.\n"
        )
    return (
        f"{lead}"
        "Use only the facts in the context below. Do not invent component names or slider labels.\n"
        "Choose component names exactly from available_choices.\n"
        "Choose slider_label values exactly from real_sliders.\n"
        "Use direction: lower, neutral, or higher.\n"
        "Confidence must be low, medium, or high.\n"
        "This is experimental assistance. Be conservative and explain tradeoffs.\n\n"
        f"{STRATEGY_JSON_SCHEMA_HINT}\n\n"
        "Context:\n"
        f"{context_json}\n"
    )


def _extract_json_object(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        payload = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        match = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
        if match is None:
            raise LLMStrategyParseError(
                f"LLM response did not contain valid JSON: {exc}"
            ) from exc
        try:
            payload = json.loads(match.group(0))
        except json.JSONDecodeError as inner_exc:
            raise LLMStrategyParseError(
                f"LLM response JSON could not be parsed: {inner_exc}"
            ) from inner_exc
    if not isinstance(payload, dict):
        raise LLMStrategyParseError("LLM strategy root must be a JSON object.")
    return payload


def parse_llm_strategy_response(text: str) -> LLMDesignStrategy:
    """Parse LLM JSON text into a structured strategy."""
    payload = _extract_json_object(text)
    component_choices: list[LLMComponentChoice] = []
    for item in payload.get("component_choices", []):
        if not isinstance(item, dict):
            continue
        alternatives = item.get("alternatives", [])
        if not isinstance(alternatives, list):
            alternatives = []
        component_choices.append(
            LLMComponentChoice(
                section=str(item.get("section", "unknown")),
                choice_type=str(item.get("choice_type", "unknown")),
                recommended_choice=str(item.get("recommended_choice", "")).strip(),
                alternatives=tuple(str(value) for value in alternatives),
                reason=str(item.get("reason", "")),
                confidence=str(item.get("confidence", "low")),
            )
        )

    slider_guidance: list[LLMSliderGuidance] = []
    for item in payload.get("slider_guidance", []):
        if not isinstance(item, dict):
            continue
        suggested = item.get("suggested_range")
        suggested_range: tuple[float, float] | None = None
        if isinstance(suggested, list) and len(suggested) == 2:
            try:
                suggested_range = (float(suggested[0]), float(suggested[1]))
            except (TypeError, ValueError):
                suggested_range = None
        slider_guidance.append(
            LLMSliderGuidance(
                section=str(item.get("section", "unknown")),
                slider_label=str(item.get("slider_label", "")).strip(),
                direction=str(item.get("direction", "neutral")).strip().lower(),
                suggested_range=suggested_range,
                reason=str(item.get("reason", "")),
            )
        )

    tradeoffs = payload.get("expected_tradeoffs", [])
    risks = payload.get("risks", [])
    if not isinstance(tradeoffs, list):
        tradeoffs = []
    if not isinstance(risks, list):
        risks = []

    return LLMDesignStrategy(
        component_choices=tuple(component_choices),
        slider_guidance=tuple(slider_guidance),
        expected_tradeoffs=tuple(str(value) for value in tradeoffs),
        risks=tuple(str(value) for value in risks),
        explanation=str(payload.get("explanation", "")),
    )


def list_ollama_models(config: LLMConfig) -> list[str]:
    """Return model names reported by a local Ollama instance."""
    base_url = config.base_url.rstrip("/") or DEFAULT_OLLAMA_BASE_URL
    try:
        response = requests.get(f"{base_url}/api/tags", timeout=min(config.timeout, 10.0))
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, dict):
            return []
        models = data.get("models", [])
        if not isinstance(models, list):
            return []
        return [str(item.get("name", "")).strip() for item in models if item.get("name")]
    except requests.RequestException:
        return []


def ollama_is_reachable(config: LLMConfig) -> bool:
    """Return True when Ollama responds on its tags endpoint."""
    base_url = config.base_url.rstrip("/") or DEFAULT_OLLAMA_BASE_URL
    try:
        response = requests.get(f"{base_url}/api/tags", timeout=5.0)
        return response.status_code == 200
    except requests.RequestException:
        return False


def _parse_ollama_error(response: requests.Response) -> str:
    try:
        data = response.json()
        if isinstance(data, dict) and data.get("error"):
            return str(data["error"])
    except (ValueError, requests.JSONDecodeError):
        pass
    return response.text[:300] or f"HTTP {response.status_code}"


def _raise_ollama_http_error(response: requests.Response, config: LLMConfig) -> None:
    message = _parse_ollama_error(response)
    available = list_ollama_models(config)
    available_text = ", ".join(available) if available else "(none reported)"
    if response.status_code == 404 and "not found" in message.lower():
        raise RuntimeError(
            f"Ollama model {config.model!r} is not installed ({message}). "
            f"Available models: {available_text}. "
            f"Run `ollama pull {config.model}` or pick an installed model in Design Optimizer."
        )
    raise RuntimeError(
        f"Ollama request failed ({response.status_code}): {message}. "
        f"Available models: {available_text}."
    )


def call_ollama_strategy(
    context: dict[str, Any],
    config: LLMConfig,
    *,
    prompt_builder=build_design_strategy_prompt,
) -> str:
    """Call a local Ollama generate endpoint and return raw response text."""
    base_url = config.base_url.rstrip("/") or DEFAULT_OLLAMA_BASE_URL
    url = f"{base_url}/api/generate"
    payload = {
        "model": config.model,
        "prompt": prompt_builder(context),
        "stream": False,
        "format": "json",
        "options": {"temperature": config.temperature},
    }
    try:
        response = requests.post(url, json=payload, timeout=config.timeout)
    except requests.ConnectionError as exc:
        raise RuntimeError(
            f"Could not connect to Ollama at {base_url}. "
            "Start Ollama or switch to Deterministic only."
        ) from exc
    except requests.Timeout as exc:
        raise RuntimeError(
            f"Ollama request timed out after {config.timeout:.0f}s. "
            "Try a smaller model or increase the timeout."
        ) from exc
    if not response.ok:
        _raise_ollama_http_error(response, config)
    data = response.json()
    if not isinstance(data, dict):
        raise RuntimeError("Ollama response was not a JSON object.")
    text = data.get("response", "")
    if not isinstance(text, str) or not text.strip():
        raise RuntimeError("Ollama returned an empty strategy response.")
    return text


def call_openai_compatible_strategy(
    context: dict[str, Any],
    config: LLMConfig,
    *,
    prompt_builder=build_design_strategy_prompt,
) -> str:
    """Call an OpenAI-compatible chat completions endpoint."""
    base_url = config.base_url.rstrip("/")
    url = f"{base_url}/v1/chat/completions"
    headers = {"Content-Type": "application/json"}
    if config.api_key:
        headers["Authorization"] = f"Bearer {config.api_key}"
    payload = {
        "model": config.model,
        "temperature": config.temperature,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You assist a GearCity design optimizer. Return JSON only using the "
                    "requested schema."
                ),
            },
            {"role": "user", "content": prompt_builder(context)},
        ],
        "response_format": {"type": "json_object"},
    }
    response = requests.post(url, headers=headers, json=payload, timeout=config.timeout)
    response.raise_for_status()
    data = response.json()
    choices = data.get("choices", [])
    if not choices:
        raise RuntimeError("OpenAI-compatible API returned no choices.")
    message = choices[0].get("message", {})
    content = message.get("content", "")
    if not isinstance(content, str) or not content.strip():
        raise RuntimeError("OpenAI-compatible API returned empty content.")
    return content


def request_llm_strategy(
    context: dict[str, Any],
    config: LLMConfig,
    *,
    prompt_builder=build_design_strategy_prompt,
) -> LLMDesignStrategy:
    """Request and parse an LLM strategy using the configured backend."""
    if config.backend == "ollama":
        raw = call_ollama_strategy(context, config, prompt_builder=prompt_builder)
    elif config.backend == "openai_compatible":
        raw = call_openai_compatible_strategy(context, config, prompt_builder=prompt_builder)
    else:
        raise RuntimeError("LLM backend is not configured.")
    return parse_llm_strategy_response(raw)


def request_llm_repair_strategy(
    context: dict[str, Any],
    config: LLMConfig,
) -> LLMDesignStrategy:
    """Request a repair strategy after a failed design."""
    return request_llm_strategy(
        context,
        config,
        prompt_builder=build_design_repair_prompt,
    )


def llm_backend_label(config: LLMConfig) -> str:
    """Return a short backend label for UI display."""
    if config.backend == "ollama":
        return f"Ollama ({config.model})"
    if config.backend == "openai_compatible":
        return f"OpenAI-compatible ({config.model})"
    return "none"
