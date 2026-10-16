"""Detect the route change an objective proposes ("add a flight on BOM-DEL", "cut a Chennai-Kolkata flight").

The network agent must evaluate exactly that change rather than swap in a better one, so that a bad suggestion
is scored as bad; the decision engine checks that it did. Detection is deliberately strict: it needs exactly one
twin route (two airports, by code or city name, in either order) and exactly one direction, otherwise there is
no proposal and the agent picks the best option as before.
"""
import re
from collections.abc import Mapping

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.digital_twin import Airport, Route

INCREASE = "INCREASE_FREQUENCY"
DECREASE = "DECREASE_FREQUENCY"

_INCREASE_WORDS = {"add", "adding", "increase", "increasing", "more", "extra", "another", "additional", "launch",
                   "expand", "boost", "raise"}
_DECREASE_WORDS = {"cut", "cutting", "remove", "removing", "reduce", "reducing", "decrease", "decreasing", "drop",
                   "dropping", "fewer", "trim", "less", "withdraw"}
# Common alternative city names, on top of each airport's code and its city in the twin.
_EXTRA_ALIASES = {"BANGALORE": "BLR", "BOMBAY": "BOM", "NEW DELHI": "DEL", "MADRAS": "MAA", "CALCUTTA": "CCU"}
_WORD_RE = re.compile(r"[A-Za-z]+")


def _airports_in_order(objective: str, aliases: Mapping[str, str]) -> list[str]:
    text = objective.upper()
    hits: list[tuple[int, str]] = []
    for alias, code in aliases.items():
        for match in re.finditer(rf"(?<![A-Z]){re.escape(alias.upper())}(?![A-Z])", text):
            hits.append((match.start(), code))
    ordered: list[str] = []
    for _, code in sorted(hits):
        if code not in ordered:
            ordered.append(code)
    return ordered


def _direction(objective: str) -> str | None:
    words = {w.lower() for w in _WORD_RE.findall(objective)}
    up, down = bool(words & _INCREASE_WORDS), bool(words & _DECREASE_WORDS)
    if up == down:
        return None
    return INCREASE if up else DECREASE


def parse_proposed_change(objective: str, *, routes: set[str], aliases: Mapping[str, str]) -> dict | None:
    """{"route": "ORIG-DEST", "action": INCREASE/DECREASE} or None (see the module docstring)."""
    airports = _airports_in_order(objective, aliases)
    action = _direction(objective)
    if len(airports) != 2 or action is None:
        return None
    first, second = airports
    for route in (f"{first}-{second}", f"{second}-{first}"):
        if route in routes:
            return {"route": route, "action": action}
    return None


async def proposed_change_for(db: AsyncSession, objective: str) -> dict | None:
    """parse_proposed_change against the twin's routes and airport codes and city names."""
    airports = (await db.execute(select(Airport))).scalars().all()
    by_id = {airport.id: airport.code for airport in airports}
    aliases = {**_EXTRA_ALIASES}
    for airport in airports:
        aliases[airport.code.upper()] = airport.code
        if airport.city:
            aliases[airport.city.upper()] = airport.code
    rows = (await db.execute(select(Route.origin_id, Route.destination_id))).all()
    routes = {f"{by_id[origin]}-{by_id[destination]}" for origin, destination in rows}
    return parse_proposed_change(objective, routes=routes, aliases=aliases)
