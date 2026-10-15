import asyncio
import json
import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.spec import AgentSpec
from app.config import get_settings
from app.evidence import catalog
from app.evidence.base import EvidenceItem, EvidenceRequest

logger = logging.getLogger(__name__)

_MAX_REASON_CHARS = 200


def _route_from(previous_results: list[dict]) -> str | None:
    """The route of the first NETWORK result, if there is one."""
    for result in previous_results:
        if result.get("agent_type") == "NETWORK":
            return result.get("route")
    return None


def _reason(exc: BaseException) -> str:
    text = f"{type(exc).__name__}: {exc}" if str(exc) else type(exc).__name__
    return text[:_MAX_REASON_CHARS]


async def _recover(db: AsyncSession) -> None:
    """Make the session usable again after a provider failed.

    Normally the savepoint rollback is enough. Cancelling a query mid-flight (a timeout) invalidates
    the connection's transaction instead, and the only way out is a full rollback. That is safe here:
    agents gather evidence before they write anything, so there is nothing uncommitted to lose.
    """
    try:
        await db.execute(text("SELECT 1"))
    except Exception:  # noqa: BLE001 - any failure here means the transaction is unusable
        await db.rollback()


async def gather_evidence(
    db: AsyncSession, *, spec: AgentSpec, objective: str, previous_results: list[dict]
) -> tuple[list[dict], list[str]]:
    """Run the spec's evidence providers and return (evidence items as JSON dicts, unavailable notes).

    Each provider runs in its own savepoint under a timeout, so a failed query or a slow source can
    neither poison the agent's transaction nor stall it. Failures are logged and reported as
    "<provider>: <reason>" in the second element; this function never raises for a provider. Items are
    de-duplicated by id, ordered most reliable first, then capped by count and total JSON size.
    """
    settings = get_settings()
    request = EvidenceRequest(
        agent_type=spec.agent_type,
        objective=objective,
        route=_route_from(previous_results),
        previous_results=previous_results,
    )

    collected: list[EvidenceItem] = []
    unavailable: list[str] = []
    for name in spec.evidence_providers:
        provider = catalog.EVIDENCE_PROVIDERS.get(name)
        if provider is None:
            logger.warning("evidence provider %s is not registered", name)
            unavailable.append(f"{name}: unknown provider")
            continue
        try:
            async with db.begin_nested():
                items = await asyncio.wait_for(
                    provider(db, request), timeout=settings.evidence_provider_timeout_seconds
                )
        except asyncio.TimeoutError:
            logger.warning("evidence provider %s timed out", name)
            unavailable.append(f"{name}: timed out after {settings.evidence_provider_timeout_seconds:g}s")
            await _recover(db)
        except Exception as exc:  # noqa: BLE001 - a provider must never fail the agent
            logger.warning("evidence provider %s failed: %s", name, exc)
            unavailable.append(f"{name}: {_reason(exc)}")
            await _recover(db)
        else:
            collected.extend(items)

    unique: dict[str, EvidenceItem] = {}
    for item in collected:
        unique.setdefault(item.id, item)
    ranked = sorted(unique.values(), key=lambda item: item.reliability, reverse=True)  # stable

    kept: list[dict] = []
    total_chars = 0
    for item in ranked:
        if len(kept) >= settings.evidence_max_items_per_agent:
            break
        dumped = item.model_dump(mode="json")
        size = len(json.dumps(dumped))
        if total_chars + size > settings.evidence_max_chars_per_agent:
            break
        kept.append(dumped)
        total_chars += size
    return kept, unavailable
