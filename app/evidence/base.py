from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession


class EvidenceItem(BaseModel):
    """One piece of external evidence put into an agent's context and citable by `id`."""

    id: str  # unique within one context, e.g. "fuel:eia:2026-10-10" or "web:3f9a1c2e"
    source: Literal[
        "openflights", "eia_jet_fuel", "eia_brent", "fx", "dgca", "web", "aviation_weather", "open_meteo",
        "faa_airworthiness_directives", "world_bank", "india_holidays", "imd",
    ]
    kind: Literal["dataset", "web"]
    title: str
    url: str | None = None
    fetched_at: datetime | None = None
    reliability: float = Field(ge=0, le=1)
    content: dict | str


@dataclass
class EvidenceRequest:
    agent_type: str
    objective: str
    route: str | None  # e.g. "BOM-DEL", from the network agent's recommendation, if any
    previous_results: list[dict] = field(default_factory=list)


EvidenceProvider = Callable[[AsyncSession, EvidenceRequest], Awaitable[list[EvidenceItem]]]
