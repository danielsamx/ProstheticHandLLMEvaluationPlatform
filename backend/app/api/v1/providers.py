"""LLM providers and models, including LM Studio discovery."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.session import get_session
from app.models.llm import LlmModel, LlmProvider
from app.schemas.api import (
    LmStudioProbeOut,
    LmStudioSyncOut,
    ModelCreate,
    ModelOut,
    ProviderOut,
)
from app.services.llm_service import probe_lm_studio

router = APIRouter(prefix="/providers", tags=["providers"])


@router.get("", response_model=list[ProviderOut])
async def list_providers(
    only_enabled: bool = Query(default=True),
    session: AsyncSession = Depends(get_session),
) -> list[LlmProvider]:
    stmt = select(LlmProvider).order_by(LlmProvider.is_local.desc(), LlmProvider.display_name)
    if only_enabled:
        stmt = stmt.where(LlmProvider.is_enabled.is_(True))
    return list((await session.execute(stmt)).scalars().all())


@router.get("/models", response_model=list[ModelOut])
async def list_models(
    provider_id: uuid.UUID | None = None,
    only_enabled: bool = Query(default=True),
    session: AsyncSession = Depends(get_session),
) -> list[LlmModel]:
    stmt = select(LlmModel).order_by(LlmModel.display_name)
    if provider_id:
        stmt = stmt.where(LlmModel.provider_id == provider_id)
    if only_enabled:
        stmt = stmt.where(LlmModel.is_enabled.is_(True))
    return list((await session.execute(stmt)).scalars().all())


@router.post("/models", response_model=ModelOut, status_code=status.HTTP_201_CREATED)
async def create_model(
    payload: ModelCreate, session: AsyncSession = Depends(get_session)
) -> LlmModel:
    provider = await session.get(LlmProvider, payload.provider_id)
    if provider is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Provider not found.")
    model = LlmModel(**payload.model_dump())
    session.add(model)
    await session.flush()
    return model


@router.get("/lm-studio/probe", response_model=LmStudioProbeOut)
async def lm_studio_probe(api_base: str | None = None) -> LmStudioProbeOut:
    """Ask the local LM Studio server which models are currently loaded."""
    return LmStudioProbeOut(**await probe_lm_studio(api_base))


@router.post("/lm-studio/sync", response_model=LmStudioSyncOut)
async def lm_studio_sync(
    api_base: str | None = None,
    session: AsyncSession = Depends(get_session),
) -> LmStudioSyncOut:
    """Import every model LM Studio currently exposes into the catalogue.

    Capability flags default conservatively (JSON mode on, JSON Schema off,
    no seed, no top_k) because GGUF runtimes vary; the researcher can raise
    them per model once verified.
    """
    probe = await probe_lm_studio(api_base)
    if not probe["reachable"]:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            f"LM Studio is not reachable at {probe['api_base']}: {probe['error']}",
        )

    provider = (
        await session.execute(select(LlmProvider).where(LlmProvider.slug == "lm_studio"))
    ).scalar_one_or_none()
    if provider is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "LM Studio provider is not seeded.")

    existing = {
        m.model_key
        for m in (
            await session.execute(
                select(LlmModel).where(LlmModel.provider_id == provider.id)
            )
        ).scalars()
    }

    imported: list[LlmModel] = []
    already: list[str] = []
    for item in probe["models"]:
        key = item["id"]
        if key in existing:
            already.append(key)
            continue
        model = LlmModel(
            provider_id=provider.id,
            model_key=key,
            display_name=key,
            family=key.split("-")[0] if "-" in key else None,
            supports_json_mode=True,
            supports_json_schema=False,
            supports_seed=True,
            supports_top_k=True,
            supports_penalties=True,
            input_cost_per_1k=0.0,
            output_cost_per_1k=0.0,
            metadata_json={"discovered_from": "lm_studio", "raw": item},
        )
        session.add(model)
        imported.append(model)

    await session.flush()
    return LmStudioSyncOut(
        imported=[ModelOut.model_validate(m) for m in imported],
        already_known=already,
        api_base=probe["api_base"] or settings.lm_studio_api_base,
    )
