from datetime import datetime

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.decision.weights import (
    DEFAULT_WEIGHTS, PROFILE_NAME, DecisionWeights, weights_to_dict,
)
from app.models.external import DecisionWeightProfile

router = APIRouter(prefix="/api/decision-weights", tags=["decision-weights"])


class DecisionWeightsOut(DecisionWeights):
    updated_at: datetime | None = None


def weights_out(weights: DecisionWeights, updated_at: datetime | None) -> DecisionWeightsOut:
    return DecisionWeightsOut(**weights_to_dict(weights), updated_at=updated_at)


def profile_out(profile: DecisionWeightProfile | None) -> DecisionWeightsOut:
    """The stored profile, or the defaults (updated_at null) when there is none or it no longer validates."""
    if profile is None:
        return weights_out(DEFAULT_WEIGHTS, None)
    try:
        return weights_out(DecisionWeights.model_validate(profile.weights), profile.updated_at)
    except ValueError:
        return weights_out(DEFAULT_WEIGHTS, None)


async def _profile(db: AsyncSession) -> DecisionWeightProfile | None:
    return (
        await db.execute(select(DecisionWeightProfile).where(DecisionWeightProfile.name == PROFILE_NAME))
    ).scalar_one_or_none()


@router.get("", response_model=DecisionWeightsOut)
async def get_decision_weights(db: AsyncSession = Depends(get_db)) -> DecisionWeightsOut:
    return profile_out(await _profile(db))


@router.put("", response_model=DecisionWeightsOut)
async def put_decision_weights(body: DecisionWeights, db: AsyncSession = Depends(get_db)) -> DecisionWeightsOut:
    """Validate (422 on bad input) and upsert the "default" weight profile."""
    profile = await _profile(db)
    if profile is None:
        profile = DecisionWeightProfile(name=PROFILE_NAME, weights=weights_to_dict(body))
        db.add(profile)
    else:
        profile.weights = weights_to_dict(body)
    await db.commit()
    await db.refresh(profile)
    return profile_out(profile)
