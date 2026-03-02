from __future__ import annotations

import re
import unicodedata
from typing import Dict, List, Optional

from app.models.schemas import Availability, Service


class NormalizationError(ValueError):
    pass


_NON_ALNUM = re.compile(r"[^a-z0-9\s]")


def _normalize_text(value: str) -> str:
    lowered = value.lower().strip().replace("_", " ").replace("-", " ")
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


def _normalize_mission(value: object) -> Optional[bool]:
    if value is None:
        return None
    text = str(value).strip().lower()
    if not text:
        return None
    if text == "true":
        return True
    if text == "false":
        return False
    raise NormalizationError(f"Invalid mission value: {value}")


def normalize_services(raw_services: List[dict]) -> List[Service]:
    services: List[Service] = []
    for row in raw_services:
        normalized_row = {
            "service_name": _normalize_field(row.get("service_name")),
            "description": _normalize_field(row.get("description")),
            "region": _normalize_field(row.get("region")),
            "mission": _normalize_mission(row.get("mission")),
            "price": row.get("price"),
            "currency": _normalize_field(row.get("currency")),
        }
        try:
            service = Service(**normalized_row)
        except Exception as exc:
            raise NormalizationError(f"Invalid service row: {row}") from exc
        if not service.name:
            raise NormalizationError(f"Missing service_name in row: {row}")
        services.append(service)
    return services


def normalize_availability(
    raw_availability: List[dict], services: List[Service]
) -> Dict[str, Availability]:
    availability: Dict[str, Availability] = {}
    service_names = {
        _normalize_field(service.name) for service in services if service.name
    }

    for row in raw_availability:
        try:
            raw_slots = row.get("available_slots", row.get("slots"))
            slots = int(raw_slots)
            service_name = row["service_name"]
            item = Availability(service_name=service_name, available_slots=slots)
        except Exception as exc:
            raise NormalizationError(f"Invalid availability row: {row}") from exc

        service_key = _normalize_field(item.service_name)
        if service_key not in service_names:
            raise NormalizationError(
                f"Availability references unknown service: {item.service_name}"
            )

        availability[service_key] = item

    return availability
