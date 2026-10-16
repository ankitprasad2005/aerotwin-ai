"""Evidence providers for the India-wide weather picture: the airport summary and the IMD warnings."""
from datetime import timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.datasets import imd, weather, weather_india
from app.datasets.common import utcnow
from app.evidence.base import EvidenceItem, EvidenceRequest
from app.evidence.reliability import SOURCE_RELIABILITY
from app.models.external import ImdWarning

# The summary is derived from METAR/TAF/forecast by our own thresholds, so it is trusted a little less than the raw METAR (0.9).
INDIA_SUMMARY_RELIABILITY = 0.85
MAX_IMD_WARNINGS = 10
# The evidence of an agent shares a 6000-character budget, so the summary lists only the few worst airports, compactly.
SUMMARY_WORST_AIRPORTS = 5
WORST_FIELDS = ("airport", "flight_category", "taf_worst_flight_category_24h", "taf_thunderstorm_24h", "disruption_days")
MESSAGE_CHARS = 300


async def india_weather_summary(db: AsyncSession, request: EvidenceRequest) -> list[EvidenceItem]:
    """One item: how many Indian airports are in each current flight category, how many expect a thunderstorm in
    the next 24 hours and which airports are worst affected. Nothing when no Indian airport has any stored weather data."""
    summary = await weather_india.india_summary(db)
    reporting = summary["airports_reporting"]
    if not summary["has_data"]:
        return []
    generated_at = summary["generated_at"]
    return [
        EvidenceItem(
            id=f"india_weather:{generated_at.astimezone(timezone.utc).strftime('%Y-%m-%dT%H')}",
            source="aviation_weather",
            kind="dataset",
            title="India-wide airport weather summary (METAR, TAF, Open-Meteo)",
            url=weather.METAR_API,
            fetched_at=generated_at,
            reliability=INDIA_SUMMARY_RELIABILITY,
            content={
                "airports_total": summary["airports_total"],
                "airports_reporting": reporting,
                "by_flight_category": summary["by_flight_category"],
                "thunderstorm_24h_count": summary["thunderstorm_24h"]["count"],
                "thunderstorm_24h_airports": summary["thunderstorm_24h"]["airports"],
                "worst_airports": [
                    {key: w[key] for key in WORST_FIELDS} for w in summary["worst_airports"][:SUMMARY_WORST_AIRPORTS]
                ],
            },
        )
    ]


async def imd_warnings(db: AsyncSession, request: EvidenceRequest) -> list[EvidenceItem]:
    """Active IMD warnings and nowcasts (not yet ended), the most severe first (at most 10)."""
    now = utcnow()
    rows = (await db.execute(select(ImdWarning).where(ImdWarning.effective_end >= now))).scalars().all()
    rows = sorted(rows, key=lambda w: (imd.SEVERITY_ORDER.get(w.severity_color, 9), w.effective_end, w.identifier))
    return [
        EvidenceItem(
            id=f"imd:{w.identifier}",
            source="imd",
            kind="dataset",
            title=f"IMD {w.severity_color} warning: {w.event} ({w.issuer})",
            url=imd.IMD_PAGE_URL,
            fetched_at=w.updated_at,
            reliability=SOURCE_RELIABILITY["imd"],
            content={
                "issuer": w.issuer,
                "event": w.event,
                "severity_color": w.severity_color,
                "likelihood": w.severity_level,
                "area": w.area,
                "message": w.message if len(w.message) <= MESSAGE_CHARS else w.message[: MESSAGE_CHARS - 3] + "...",
                "valid_from": w.effective_start.isoformat(),
                "valid_to": w.effective_end.isoformat(),
            },
        )
        for w in rows[:MAX_IMD_WARNINGS]
    ]
