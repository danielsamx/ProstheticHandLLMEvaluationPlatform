"""Reusable sampling configurations and one-click lab presets."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import Permission, require_permission
from app.db.session import get_session
from app.models.llm import LlmModel, SamplingConfiguration
from app.models.prompts import LabPreset
from app.schemas.api import (
    LabPresetIn,
    LabPresetOut,
    SamplingConfigurationIn,
    SamplingConfigurationOut,
)

router = APIRouter(prefix="/configurations", tags=["configurations"])


@router.get("", response_model=list[SamplingConfigurationOut])
async def list_configurations(
    model_id: uuid.UUID | None = None,
    favorites_only: bool = Query(default=False),
    limit: int = Query(default=100, le=500),
    session: AsyncSession = Depends(get_session),
):
    stmt = (
        select(SamplingConfiguration)
        .order_by(
            SamplingConfiguration.is_favorite.desc(),
            SamplingConfiguration.use_count.desc(),
            SamplingConfiguration.created_at.desc(),
        )
        .limit(limit)
    )
    if model_id:
        stmt = stmt.where(SamplingConfiguration.model_id == model_id)
    if favorites_only:
        stmt = stmt.where(SamplingConfiguration.is_favorite.is_(True))
    return list((await session.execute(stmt)).scalars().all())


@router.post("", response_model=SamplingConfigurationOut, status_code=status.HTTP_201_CREATED,
             dependencies=[Depends(require_permission(Permission.EDIT_PROMPTS))])
async def create_configuration(
    payload: SamplingConfigurationIn, session: AsyncSession = Depends(get_session)
):
    model = await session.get(LlmModel, payload.model_id)
    if model is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Model not found.")
    if payload.top_k is not None and not model.supports_top_k:
        # Not fatal: LiteLLM drops it. Recorded so the run is still honest.
        pass
    row = SamplingConfiguration(**payload.model_dump())
    session.add(row)
    await session.flush()
    return row


@router.get("/{configuration_id}", response_model=SamplingConfigurationOut)
async def get_configuration(
    configuration_id: uuid.UUID, session: AsyncSession = Depends(get_session)
):
    row = await session.get(SamplingConfiguration, configuration_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Configuration not found.")
    return row


@router.put("/{configuration_id}", response_model=SamplingConfigurationOut,
            dependencies=[Depends(require_permission(Permission.EDIT_PROMPTS))])
async def update_configuration(
    configuration_id: uuid.UUID,
    payload: SamplingConfigurationIn,
    session: AsyncSession = Depends(get_session),
):
    row = await session.get(SamplingConfiguration, configuration_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Configuration not found.")
    for key, value in payload.model_dump().items():
        setattr(row, key, value)
    await session.flush()
    return row


@router.delete("/{configuration_id}", status_code=status.HTTP_204_NO_CONTENT,
               dependencies=[Depends(require_permission(Permission.EDIT_PROMPTS))])
async def delete_configuration(
    configuration_id: uuid.UUID, session: AsyncSession = Depends(get_session)
):
    row = await session.get(SamplingConfiguration, configuration_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Configuration not found.")
    await session.delete(row)


# ── Lab presets ─────────────────────────────────────────────────────────────

presets_router = APIRouter(prefix="/presets", tags=["configurations"])


@presets_router.get("", response_model=list[LabPresetOut])
async def list_presets(session: AsyncSession = Depends(get_session)):
    stmt = select(LabPreset).order_by(
        LabPreset.is_favorite.desc(), LabPreset.use_count.desc(), LabPreset.created_at.desc()
    )
    return list((await session.execute(stmt)).scalars().all())


@presets_router.post("", response_model=LabPresetOut, status_code=status.HTTP_201_CREATED,
                     dependencies=[Depends(require_permission(Permission.EDIT_PROMPTS))])
async def create_preset(payload: LabPresetIn, session: AsyncSession = Depends(get_session)):
    row = LabPreset(
        **payload.model_dump(exclude={"handedness", "limit_profile"}),
        handedness=payload.handedness.value,
        limit_profile=payload.limit_profile.value,
    )
    session.add(row)
    await session.flush()
    return row


@presets_router.post("/{preset_id}/use", response_model=LabPresetOut)
async def mark_preset_used(preset_id: uuid.UUID, session: AsyncSession = Depends(get_session)):
    row = await session.get(LabPreset, preset_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Preset not found.")
    row.use_count += 1
    row.last_used_at = datetime.now(UTC)
    await session.flush()
    return row


@presets_router.delete("/{preset_id}", status_code=status.HTTP_204_NO_CONTENT,
                       dependencies=[Depends(require_permission(Permission.EDIT_PROMPTS))])
async def delete_preset(preset_id: uuid.UUID, session: AsyncSession = Depends(get_session)):
    row = await session.get(LabPreset, preset_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Preset not found.")
    await session.delete(row)
