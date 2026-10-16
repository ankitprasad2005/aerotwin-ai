import logging
import math

from pydantic import BaseModel, field_validator, model_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.external import DecisionWeightProfile

logger = logging.getLogger(__name__)

PROFILE_NAME = "default"
FACTOR_KEYS = ("profit", "confidence", "feasibility", "risk", "data_quality")
LEGACY_AGENT_KEYS = ("NETWORK", "FLEET", "MAINTENANCE", "CREW", "CARGO")
# Agents added after profiles were first stored; a profile with only the legacy agents gets these defaults.
NEW_AGENT_DEFAULTS = {"WEATHER": 0.10, "FINANCE": 0.10, "EMISSIONS": 0.05}
AGENT_KEYS = LEGACY_AGENT_KEYS + tuple(NEW_AGENT_DEFAULTS)
THRESHOLD_KEYS = ("recommend", "review")


def _check_group(name: str, group: dict[str, float], keys: tuple[str, ...], *, need_positive_sum: bool) -> None:
    if set(group) != set(keys):
        raise ValueError(f"{name} must contain exactly the keys {', '.join(keys)}")
    for key, value in group.items():
        if not math.isfinite(value):
            raise ValueError(f"{name}.{key} must be a finite number")
        if value < 0:
            raise ValueError(f"{name}.{key} must be >= 0")
    if need_positive_sum and sum(group.values()) <= 0:
        raise ValueError(f"{name} weights must sum to greater than 0")


class DecisionWeights(BaseModel):
    factors: dict[str, float]
    agent_confidence: dict[str, float]
    thresholds: dict[str, float]
    profit_scale_usd: float

    @model_validator(mode="before")
    @classmethod
    def _upgrade_legacy_agents(cls, data):
        if isinstance(data, dict):
            agents = data.get("agent_confidence")
            if isinstance(agents, dict) and set(agents) == set(LEGACY_AGENT_KEYS):
                data = {**data, "agent_confidence": {**agents, **NEW_AGENT_DEFAULTS}}
        return data

    @field_validator("profit_scale_usd")
    @classmethod
    def _scale_positive(cls, value: float) -> float:
        if not math.isfinite(value) or value <= 0:
            raise ValueError("profit_scale_usd must be a finite number greater than 0")
        return value

    @model_validator(mode="after")
    def _validate_groups(self) -> "DecisionWeights":
        _check_group("factors", self.factors, FACTOR_KEYS, need_positive_sum=True)
        _check_group("agent_confidence", self.agent_confidence, AGENT_KEYS, need_positive_sum=True)
        _check_group("thresholds", self.thresholds, THRESHOLD_KEYS, need_positive_sum=False)
        recommend, review = self.thresholds["recommend"], self.thresholds["review"]
        if not 0 <= review < recommend <= 100:
            raise ValueError("thresholds must satisfy 0 <= review < recommend <= 100")
        return self


DEFAULT_WEIGHTS = DecisionWeights(
    factors={"profit": 0.30, "confidence": 0.20, "feasibility": 0.25, "risk": 0.15, "data_quality": 0.10},
    agent_confidence={"NETWORK": 0.35, "FLEET": 0.20, "MAINTENANCE": 0.15, "CREW": 0.15, "CARGO": 0.15, **NEW_AGENT_DEFAULTS},
    thresholds={"recommend": 70, "review": 45},
    profit_scale_usd=10000,
)


def weights_to_dict(weights: DecisionWeights) -> dict:
    return weights.model_dump()


async def load_weights(db: AsyncSession) -> DecisionWeights:
    """The stored "default" profile, or DEFAULT_WEIGHTS when none exists or the stored one is invalid."""
    profile = (
        await db.execute(select(DecisionWeightProfile).where(DecisionWeightProfile.name == PROFILE_NAME))
    ).scalar_one_or_none()
    if profile is None:
        return DEFAULT_WEIGHTS
    try:
        return DecisionWeights.model_validate(profile.weights)
    except ValueError:
        logger.warning("stored decision weight profile is invalid; using the defaults")
        return DEFAULT_WEIGHTS
