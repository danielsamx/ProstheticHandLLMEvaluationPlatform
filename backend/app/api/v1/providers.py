"""LLM providers and models, including LM Studio discovery."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.session import get_session
from app.models.llm import LlmModel, LlmProvider, SamplingConfiguration
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
    check_availability: bool = Query(
        default=True,
        description="Cross-check local models against the running runtime, so "
        "the catalogue cannot offer a model that is not loaded.",
    ),
    session: AsyncSession = Depends(get_session),
) -> list[ModelOut]:
    """The model catalogue.

    A catalogue entry is not proof that a model can be run: a local model may
    have been imported earlier and unloaded since. `is_available` answers that
    separately, so the interface can offer what is runnable without discarding
    rows that past executions still reference.
    """
    stmt = select(LlmModel).order_by(LlmModel.display_name)
    if provider_id:
        stmt = stmt.where(LlmModel.provider_id == provider_id)
    if only_enabled:
        stmt = stmt.where(LlmModel.is_enabled.is_(True))
    models = list((await session.execute(stmt)).scalars().all())

    loaded: set[str] | None = None
    if check_availability and any(m.provider and m.provider.is_local for m in models):
        probe = await probe_lm_studio()
        # Unreachable is not the same as "not loaded"; leaving `loaded` as None
        # keeps availability unknown rather than asserting a falsehood.
        if probe["reachable"]:
            loaded = {item["id"] for item in probe["models"]}

    result: list[ModelOut] = []
    for model in models:
        out = ModelOut.model_validate(model)
        if model.provider and model.provider.is_local and loaded is not None:
            out.is_available = model.model_key in loaded
        result.append(out)
    return result


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
            # LM Studio implements structured output at the server level, so
            # `json_schema` is available for any loaded model. It does NOT
            # implement `json_object`; the call layer maps that across.
            # /v1/models does not report the loaded context length, and the
            # architecture maximum is not what decides whether a request fits.
            # LM Studio's own default is assumed; correct it per model if you
            # loaded it with more.
            context_window=8192,
            supports_json_mode=False,
            supports_json_schema=True,
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

    # A model with no configuration cannot be run, and the Run button stays
    # disabled with nothing to explain it. Every import gets a greedy baseline:
    # temperature 0 and a fixed seed is the correct control condition here,
    # since the task measures instruction adherence rather than creativity.
    for model in imported:
        session.add(
            SamplingConfiguration(
                name=f"Deterministic · {model.display_name}",
                description="Greedy baseline created on import: temperature 0, "
                            "fixed seed. Use it as the control condition.",
                model_id=model.id,
                temperature=0.0,
                top_p=1.0,
                top_k=None,
                max_tokens=64,
                seed=42,
                frequency_penalty=0.0,
                presence_penalty=0.0,
                stop_sequences=[],
                response_format="json_schema",
                extra_params={},
                is_favorite=True,
            )
        )

    await session.flush()
    return LmStudioSyncOut(
        imported=[ModelOut.model_validate(m) for m in imported],
        already_known=already,
        api_base=probe["api_base"] or settings.lm_studio_api_base,
    )
