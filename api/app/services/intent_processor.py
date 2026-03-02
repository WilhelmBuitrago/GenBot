from __future__ import annotations

import asyncio
import json
import logging
import re
import unicodedata
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Tuple

from app.core.security import sanitize_text
from app.models.schemas import Availability, Service, ServiceOption
from app.services.conversation_memory import ConversationMemory
from app.services.llm_client import LLMClient


@dataclass
class IntentResult:
    intent: str
    service_name: Optional[str]
    prompt: str
    response: Optional[str] = None
    status: str = "ok"
    message: Optional[str] = None
    options: Optional[List[ServiceOption]] = None


_ALLOWED_INTENTS = {"price", "availability", "general"}
_INTENT_TIMEOUT_SECONDS = 6.0
_NON_ALNUM = re.compile(r"[^a-z0-9\s]")
_MISSION_EXPLICIT_MAP = {
    True: ["con misiones", "exploracion con misiones", "full", "completo", "todo"],
    False: ["sin misiones", "solo exploracion", "sin nada mas", "basico"],
}

logger = logging.getLogger("genbot")


class ServiceSelectionError(RuntimeError):
    def __init__(self, message: str, detail: dict) -> None:
        super().__init__(message)
        self.detail = detail


def _normalize_text(value: str) -> str:
    lowered = value.lower().replace("_", " ").replace("-", " ")
    normalized = unicodedata.normalize("NFD", lowered)
    without_accents = "".join(
        char for char in normalized if unicodedata.category(char) != "Mn"
    )
    cleaned = _NON_ALNUM.sub(" ", without_accents)
    return " ".join(cleaned.split())


def _normalize_field(value: object) -> str:
    if value is None:
        return ""
    text = str(value)
    if not text.strip():
        return ""
    return _normalize_text(text)


def _collect_unique(values: Iterable[str]) -> List[str]:
    seen = set()
    ordered: List[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            ordered.append(value)
    return ordered


def _parse_intent_response(
    text: str,
) -> Tuple[Optional[str], Optional[str], Optional[bool]]:
    cleaned = text.strip()
    if not cleaned:
        return None, None, None
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                data = json.loads(cleaned[start : end + 1])
            except json.JSONDecodeError:
                data = {}
        else:
            data = {}

    if not isinstance(data, dict):
        return None, None, None

    service_name = data.get("service_name", None)
    region = data.get("region", None)
    mission = data.get("mission", None)

    if service_name is not None:
        service_name = str(service_name).strip()
    if region is not None:
        region = str(region).strip()

    if mission is True or mission is False:
        mission_value = mission
    elif mission is None:
        mission_value = None
    elif isinstance(mission, str):
        normalized = mission.strip().lower()
        if normalized == "true":
            mission_value = True
        elif normalized == "false":
            mission_value = False
        elif normalized in ("", "null", "none"):
            mission_value = None
        else:
            mission_value = None
    else:
        mission_value = None

    return service_name or None, region or None, mission_value


def _detect_explicit_mission(normalized_message: str) -> Optional[bool]:
    found_true = False
    found_false = False
    for value, patterns in _MISSION_EXPLICIT_MAP.items():
        for pattern in patterns:
            normalized_pattern = _normalize_text(pattern)
            if normalized_pattern and normalized_pattern in normalized_message:
                if value:
                    found_true = True
                else:
                    found_false = True

    if found_true and found_false:
        return None
    if found_true:
        return True
    if found_false:
        return False
    return None


def _service_key_str(service: Service) -> str:
    mission_value = "" if service.mission is None else str(service.mission).lower()
    return f"{service.name}|{service.region or ''}|{mission_value}"


async def detect_intent_llm(message: str, llm_client: LLMClient) -> str:
    safe_message = sanitize_text(message)
    prompt = (
        "Somos una empresa que presta servicios profesionales para cuentas de Genshin Impact. Clasifica el siguiente mensaje en una sola palabra exactamente igual a una de estas opciones:\n\n"
        "* price\n"
        "* general\n\n"
        "Contexto: \n\n"
        "Responde únicamente con una de las 2 etiquetas. No agregues explicación."
    )

    try:
        response = await asyncio.wait_for(
            llm_client.generate(prompt=prompt, history=[]),
            timeout=_INTENT_TIMEOUT_SECONDS,
        )
    except Exception:
        return "general"

    label = response.strip().lower()
    if label in _ALLOWED_INTENTS:
        return label
    return "general"


async def _extract_fields_llm(
    message: str, services: List[Service], llm_client: LLMClient
) -> Tuple[Optional[str], Optional[str], Optional[bool]]:
    service_names = _collect_unique(
        _normalize_field(service.name) for service in services
    )
    regions = _collect_unique(_normalize_field(service.region) for service in services)

    service_list = [name for name in service_names if name]
    region_list = [region for region in regions if region]

    safe_message = sanitize_text(message)
    prompt = (
        "Extrae service_name, region y mission del mensaje del usuario. "
        "Responde solo con JSON valido y sin texto extra. "
        "Si un campo no se menciona explicitamente, usa null.\n\n"
        f"Service_name permitidos: {', '.join(service_list) if service_list else 'N/A'}\n"
        f"Regiones permitidas: {', '.join(region_list) if region_list else 'N/A'}\n"
        "Mission permitido: true, false o null\n\n"
        f"Mensaje: {safe_message}\n\n"
        'Formato esperado: {"service_name": null, "region": null, "mission": null}'
    )

    try:
        response = await asyncio.wait_for(
            llm_client.generate(prompt=prompt, history=[]),
            timeout=_INTENT_TIMEOUT_SECONDS,
        )
    except Exception:
        return None, None, None

    service_name, region, mission = _parse_intent_response(response)

    normalized_service_name = _normalize_field(service_name) if service_name else ""
    if normalized_service_name and normalized_service_name in service_list:
        service_name_value = normalized_service_name
    else:
        service_name_value = None

    normalized_region = _normalize_field(region) if region else ""
    if normalized_region and normalized_region not in region_list:
        normalized_region = ""

    return service_name_value, normalized_region or None, mission


def _filter_services(
    services: List[Service],
    service_name: Optional[str],
    region: Optional[str],
    mission: Optional[bool],
) -> List[Service]:
    candidates: List[Service] = []
    for service in services:
        name_ok = True
        region_ok = True
        mission_ok = True

        if service_name:
            name_ok = _normalize_field(service.name) == service_name

        if region:
            normalized_region = _normalize_field(service.region)
            region_ok = normalized_region == region

        if mission is not None:
            mission_ok = service.mission == mission

        if name_ok and region_ok and mission_ok:
            candidates.append(service)

    return candidates


def _build_options(candidates: List[Service]) -> List[ServiceOption]:
    options: List[ServiceOption] = []
    for service in candidates:
        options.append(
            ServiceOption(
                service_name=service.name,
                region=service.region or "",
                mission=service.mission,
                price=service.price,
                currency=service.currency,
            )
        )
    return options


def _format_ambiguity_response(options: List[ServiceOption]) -> str:
    if not options:
        return "Necesito un poco mas de informacion para continuar."

    lines = [
        "Hay varias variantes disponibles. Indica cual prefieres:",
    ]
    for option in options:
        mission_label = "con misiones" if option.mission else "solo exploracion"
        region_label = option.region or "sin region"
        lines.append(
            f"- {option.service_name} | {region_label} | {mission_label} | {option.price} {option.currency}"
        )
    lines.append("Puedes responder con la region y si incluye misiones.")
    return "\n".join(lines)


async def select_service(
    message: str,
    services: List[Service],
    llm_client: LLMClient,
    memory: ConversationMemory,
    user_id: str,
) -> Tuple[Optional[Service], Optional[List[ServiceOption]]]:
    if not message or not services:
        raise ServiceSelectionError(
            "Missing input data",
            {"reason": "empty_input"},
        )

    normalized_message = _normalize_text(message)
    if not normalized_message:
        raise ServiceSelectionError(
            "Empty normalized message",
            {"reason": "empty_message"},
        )

    service_name, region, mission = await _extract_fields_llm(
        message, services, llm_client
    )

    explicit_mission = _detect_explicit_mission(normalized_message)
    if explicit_mission is None:
        mission = None
    else:
        mission = explicit_mission

    explicit_fields = {
        "service_name": service_name,
        "region": region,
        "mission": mission,
    }

    context_fields = memory.get_recent_explicit_fields(user_id)
    effective_service_name = service_name or context_fields.get("service_name")
    effective_region = region or context_fields.get("region")
    effective_mission = mission

    memory.add_explicit_fields(user_id, explicit_fields)

    candidates = _filter_services(
        services,
        effective_service_name,
        effective_region,
        effective_mission,
    )

    logger.info(
        "Service selection context",
        extra={
            "intent_message": normalized_message,
            "explicit_fields": explicit_fields,
            "context_fields": context_fields,
            "candidate_count": len(candidates),
            "candidates": [_service_key_str(service) for service in candidates],
        },
    )

    if not candidates:
        raise ServiceSelectionError(
            "No matching services",
            {
                "reason": "no_candidates",
                "service_name": service_name,
                "region": region,
                "mission": mission,
            },
        )

    if len(candidates) == 1:
        selected = candidates[0]
        logger.info(
            "Service selected deterministically",
            extra={"service_name": selected.name},
        )
        return selected, None

    options = _build_options(candidates)
    logger.info(
        "Service selection ambiguous",
        extra={"options": [_service_key_str(service) for service in candidates]},
    )
    return None, options


async def build_prompt(
    message: str,
    services: List[Service],
    availability: Dict[str, Availability],
    llm_client: LLMClient,
    memory: ConversationMemory,
    user_id: str,
) -> IntentResult:
    safe_message = sanitize_text(message)
    intent = await detect_intent_llm(safe_message, llm_client)
    logger.info(
        "Intent detected",
        extra={"intent": intent, "user_message": _normalize_text(safe_message)},
    )

    selected_service, options = await select_service(
        safe_message, services, llm_client, memory, user_id
    )

    if options:
        response_text = _format_ambiguity_response(options)
        return IntentResult(
            intent=intent,
            service_name=None,
            prompt="",
            response=response_text,
            status="ambiguous",
            message="Multiple service variants found",
            options=options,
        )

    service_block = "No service selected."
    availability_block = "No availability found."

    if selected_service:
        service_block = (
            f"Service: {selected_service.name}\n"
            f"Description: {selected_service.description}\n"
            f"Price: {selected_service.price} {selected_service.currency}\n"
        )
        item = availability.get(_normalize_field(selected_service.name))
        if item:
            availability_block = f"Available now: {item.slots} people"

    prompt = (
        "Eres un asesor de servicios de Genshin Impact. "
        "Responde en español con un tono cercano y profesional. "
        "Sé empático, directo y usa frases humanas naturales. "
        "NO repitas saludos ni presentaciones en cada mensaje. "
        "Responde solo sobre los servicios disponibles: exploración de mundos, mantenimiento de cuenta, "
        "realización de misiones, eventos especiales, desafíos del Abismo y desafíos al Teatro Espectral. "
        "NO inventes servicios, recompensas, horarios, disponibilidad ni datos que no estén en el contexto proporcionado. "
        "Si faltan datos, pide al usuario la información necesaria de manera breve y directa.\n\n"
        f"Intent: {intent}\n"
        f"User message: {safe_message}\n"
        f"Service data:\n{service_block}\n"
        f"Availability data:\n{availability_block}\n"
    )

    return IntentResult(
        intent=intent,
        service_name=selected_service.name if selected_service else None,
        prompt=prompt,
    )
