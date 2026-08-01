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
    kind: str = Field(default="verify", pattern="^(enrich|verify)$")
    limit: Optional[int] = None
