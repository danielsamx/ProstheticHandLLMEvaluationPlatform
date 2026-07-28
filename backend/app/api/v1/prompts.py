"""Versioned prompt artefacts and the read-only prompt preview."""

from __future__ import annotations

import hashlib
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.domain.hand_spec import get_limit_profile
from app.models.llm import LlmModel
from app.models.prompts import (
    DynamicPromptTemplate,
    SystemPromptVersion,
    TechnicalContextVersion,
)
from app.prompts import budget as prompt_budget
from app.prompts.builder import build_prompt
from app.prompts.technical_context import build_technical_context
from app.schemas.api import (
    DynamicTemplateIn,
    DynamicTemplateOut,
    PromptPreviewIn,
    PromptPreviewOut,
    PromptVersionOut,
    SystemPromptIn,
    TechnicalContextIn,
    TechnicalContextOut,
)

router = APIRouter(prefix="/prompts", tags=["prompts"])


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


async def _deactivate_others(session: AsyncSession, model_cls, keep_id: uuid.UUID) -> None:
    await session.execute(
        update(model_cls).where(model_cls.id != keep_id).values(is_active=False)
    )


# ── System prompt (block 1) ─────────────────────────────────────────────────


@router.get("/system", response_model=list[PromptVersionOut])
async def list_system_prompts(session: AsyncSession = Depends(get_session)):
    stmt = select(SystemPromptVersion).order_by(SystemPromptVersion.created_at.desc())
    return list((await session.execute(stmt)).scalars().all())


@router.post("/system", response_model=PromptVersionOut, status_code=status.HTTP_201_CREATED)
async def create_system_prompt(
    payload: SystemPromptIn, session: AsyncSession = Depends(get_session)
):
    """Editing a prompt creates a new version. Existing rows are never mutated,
    so every published result stays reproducible."""
    row = SystemPromptVersion(
        name=payload.name,
        version=payload.version,
        content=payload.content,
        content_sha256=_sha(payload.content),
        description=payload.description,
        char_count=len(payload.content),
        is_active=payload.activate,
    )
    session.add(row)
    await session.flush()
    if payload.activate:
        await _deactivate_others(session, SystemPromptVersion, row.id)
    return row


@router.post("/system/{version_id}/activate", response_model=PromptVersionOut)
async def activate_system_prompt(
    version_id: uuid.UUID, session: AsyncSession = Depends(get_session)
):
    row = await session.get(SystemPromptVersion, version_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "System prompt version not found.")
    row.is_active = True
    await _deactivate_others(session, SystemPromptVersion, row.id)
    return row


# ── Technical context (block 2) ─────────────────────────────────────────────


@router.get("/technical-context", response_model=list[TechnicalContextOut])
async def list_technical_contexts(session: AsyncSession = Depends(get_session)):
    stmt = select(TechnicalContextVersion).order_by(TechnicalContextVersion.created_at.desc())
    return list((await session.execute(stmt)).scalars().all())


@router.get("/technical-context/generated", response_model=dict)
async def preview_generated_context(
    limit_profile: str | None = None, include_json_schema: bool = True
):
    """Regenerate the canonical context straight from the domain model.

    Useful as a diff target: if a hand-edited context has drifted from the
    validators, this is what it should say.
    """
    profile = get_limit_profile(limit_profile)
    content = build_technical_context(profile, include_json_schema=include_json_schema)
    return {
        "limit_profile": profile.id.value,
        "content": content,
        "content_sha256": _sha(content),
        "char_count": len(content),
    }


@router.post(
    "/technical-context", response_model=TechnicalContextOut, status_code=status.HTTP_201_CREATED
)
async def create_technical_context(
    payload: TechnicalContextIn, session: AsyncSession = Depends(get_session)
):
    row = TechnicalContextVersion(
        name=payload.name,
        version=payload.version,
        content=payload.content,
        content_sha256=_sha(payload.content),
        description=payload.description,
        char_count=len(payload.content),
        is_active=payload.activate,
        limit_profile=payload.limit_profile.value,
        generated_from_domain=False,
        includes_json_schema=payload.includes_json_schema,
    )
    session.add(row)
    await session.flush()
    if payload.activate:
        await _deactivate_others(session, TechnicalContextVersion, row.id)
    return row


@router.post("/technical-context/{version_id}/activate", response_model=TechnicalContextOut)
async def activate_technical_context(
    version_id: uuid.UUID, session: AsyncSession = Depends(get_session)
):
    row = await session.get(TechnicalContextVersion, version_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Technical context version not found.")
    row.is_active = True
    await _deactivate_others(session, TechnicalContextVersion, row.id)
    return row


# ── Dynamic template (block 3) ──────────────────────────────────────────────


@router.get("/dynamic-templates", response_model=list[DynamicTemplateOut])
async def list_dynamic_templates(session: AsyncSession = Depends(get_session)):
    stmt = select(DynamicPromptTemplate).order_by(DynamicPromptTemplate.created_at.desc())
    return list((await session.execute(stmt)).scalars().all())


@router.post(
    "/dynamic-templates", response_model=DynamicTemplateOut, status_code=status.HTTP_201_CREATED
)
async def create_dynamic_template(
    payload: DynamicTemplateIn, session: AsyncSession = Depends(get_session)
):
    row = DynamicPromptTemplate(
        name=payload.name,
        version=payload.version,
        content=payload.content,
        content_sha256=_sha(payload.content),
        description=payload.description,
        char_count=len(payload.content),
        is_active=payload.activate,
        include_channel_sites=payload.include_channel_sites,
        include_extended_features=payload.include_extended_features,
        required_placeholders=[
            "hand", "experiment_type", "source_mode", "window_ms",
            "sample_rate_hz", "subject_block", "emg_block", "mean_rms", "extra_block",
        ],
    )
    session.add(row)
    await session.flush()
    if payload.activate:
        await _deactivate_others(session, DynamicPromptTemplate, row.id)
    return row


# ── Preview (no tokens spent) ───────────────────────────────────────────────


@router.post("/preview", response_model=PromptPreviewOut)
async def preview_prompt(
    payload: PromptPreviewIn, session: AsyncSession = Depends(get_session)
) -> PromptPreviewOut:
    """Assemble the final three-block prompt exactly as ``run_execution`` would.

    The researcher inspects it; they never author it.
    """
    system_row = await _resolve(session, SystemPromptVersion, payload.system_prompt_version_id)
    context_row = await _resolve(
        session, TechnicalContextVersion, payload.technical_context_version_id
    )
    template_row = await _resolve(
        session, DynamicPromptTemplate, payload.dynamic_prompt_template_id
    )

    profile = get_limit_profile(
        payload.limit_profile.value if payload.limit_profile
        else (context_row.limit_profile if context_row else None)
    )

    assembled = build_prompt(
        payload.window,
        handedness=payload.handedness,
        system_prompt=payload.system_prompt_override
        or (system_row.content if system_row else None),
        technical_context=payload.technical_context_override
        or (context_row.content if context_row else None),
        dynamic_template=payload.dynamic_template_override
        or (template_row.content if template_row else None),
        limit_profile=profile,
        experiment_type=payload.experiment_type,
        subject_ref=payload.subject_ref,
        subject_notes=payload.subject_notes,
        extra_parameters=payload.extra_parameters,
        merge_context_into_system=payload.merge_context_into_system,
    )

    # The context window that matters is the one the model was *loaded* with,
    # which LM Studio sets well below the architecture's maximum.
    context_window: int | None = None
    if payload.model_id is not None:
        model = await session.get(LlmModel, payload.model_id)
        context_window = model.context_window if model else None

    budget = prompt_budget.check(
        system_prompt=assembled.system_prompt,
        technical_context=assembled.technical_context,
        dynamic_prompt=assembled.dynamic_prompt,
        context_window=context_window,
        matrix_rows=min(payload.window.sample_count, 64),
    )

    return PromptPreviewOut(
        system_prompt=assembled.system_prompt,
        technical_context=assembled.technical_context,
        dynamic_prompt=assembled.dynamic_prompt,
        full_prompt=assembled.full_prompt,
        messages=assembled.messages,
        limit_profile=assembled.limit_profile,
        char_counts=assembled.char_counts(),
        system_prompt_sha256=assembled.system_prompt_sha256,
        technical_context_sha256=assembled.technical_context_sha256,
        dynamic_prompt_sha256=assembled.dynamic_prompt_sha256,
        frozen_context_sha256=assembled.frozen_context_sha256,
        full_prompt_sha256=assembled.full_prompt_sha256,
        estimated_prompt_tokens=budget.prompt_tokens,
        token_breakdown=budget.breakdown,
        context_window=budget.context_window,
        fits_context=budget.fits,
        budget_advice=budget.advice,
    )


async def _resolve(session: AsyncSession, model_cls, artefact_id):
    if artefact_id is not None:
        row = await session.get(model_cls, artefact_id)
        if row is None:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND, f"{model_cls.__name__} {artefact_id} not found."
            )
        return row
    stmt = select(model_cls).where(model_cls.is_active.is_(True)).limit(1)
    return (await session.execute(stmt)).scalar_one_or_none()
