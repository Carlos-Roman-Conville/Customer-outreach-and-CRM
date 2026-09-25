"""Pydantic schemas."""
from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


class UserOut(BaseModel):
    id: int
    name: str
    email: str
    role: str
    demo_mode: bool = False


class DispositionIn(BaseModel):
    disposition: str
    notes: str = ""
    callback_days: int = 2
    callback_date: Optional[str] = None
    discovery: Optional["DiscoveryIn"] = None


class DiscoveryIn(BaseModel):
    after_hours: Optional[str] = None
    current_tool: Optional[str] = None
    hiring_front_desk: Optional[int] = None
    missed_calls: Optional[str] = None
    answering_spend: Optional[float] = None


class DiscoveryPatch(DiscoveryIn):
    pass


class StatusPatch(BaseModel):
    status: str


class NoteIn(BaseModel):
    body: str


class DealPatch(BaseModel):
    value: Optional[float] = None
    probability: Optional[float] = None
    stage: Optional[str] = None
    expected_close: Optional[str] = None


class SavedViewIn(BaseModel):
    name: str
    filters: dict[str, Any]


class EnrichStartIn(BaseModel):
    kind: str = Field(default="verify", pattern="^(enrich|verify|signals)$")
    limit: Optional[int] = None
