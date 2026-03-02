from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field, constr


class Service(BaseModel):
    name: constr(strip_whitespace=True, min_length=1) = Field(..., alias="service_name")
    description: constr(strip_whitespace=True, min_length=1)
    region: constr(strip_whitespace=True) = Field(default="")
    mission: Optional[bool] = None
    price: float = Field(..., ge=0)
    currency: constr(strip_whitespace=True, min_length=3, max_length=3)


class Availability(BaseModel):
    service_name: constr(strip_whitespace=True, min_length=1)
    slots: int = Field(..., ge=0, alias="available_slots")


class ChatRequest(BaseModel):
    user_id: constr(strip_whitespace=True, min_length=1, max_length=64)
    message: constr(strip_whitespace=True, min_length=1, max_length=2000)


class ServiceOption(BaseModel):
    service_name: constr(strip_whitespace=True, min_length=1)
    region: constr(strip_whitespace=True) = Field(default="")
    mission: Optional[bool] = None
    price: float = Field(..., ge=0)
    currency: constr(strip_whitespace=True, min_length=3, max_length=3)


class ChatResponse(BaseModel):
    response: str
    intent: str
    service_name: Optional[str] = None
    status: str = "ok"
    message: Optional[str] = None
    options: Optional[List[ServiceOption]] = None
