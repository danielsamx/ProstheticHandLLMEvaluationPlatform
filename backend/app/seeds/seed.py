"""Idempotent seed: providers, a starter model catalogue and the baseline
prompt versions generated from the technical manuals.

Run with ``python -m app.seeds.seed``.  Safe to re-run.
"""

from __future__ import annotations

import asyncio
import hashlib

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import configure_logging, get_logger
from app.db.session import AsyncSessionLocal
from app.domain.hand_spec import LimitProfileId, get_limit_profile
from app.models.experiment import Execution
from app.models.llm import LlmModel, LlmProvider, SamplingConfiguration
from app.models.prompts import (
    EmgContextVersion,
    SystemPromptVersion,
    TechnicalContextVersion,
)
from app.prompts.emg_context import (
    EMG_CONTEXT_NAME,
    EMG_CONTEXT_VERSION,
    build_emg_context,
)
from app.prompts.system_prompt import (
    SYSTEM_PROMPT,
    SYSTEM_PROMPT_NAME,
    SYSTEM_PROMPT_VERSION,
)
from app.prompts.technical_context import (
    TECHNICAL_CONTEXT_OPEN_CLOSE_NAME,
    TECHNICAL_CONTEXT_OPEN_CLOSE_VERSION,
    build_technical_context_open_close,
)

logger = get_logger(__name__)


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


#: Only LM Studio ships enabled.
#:
#: The other rows are retained rather than removed so a future comparison
#: against a hosted model needs a flag flip, not a migration — but an
#: unselectable provider in a dropdown is clutter, and a provider with no API
#: key configured is worse than clutter: it fails at inference time.
PROVIDERS = [
    # LM Studio first: it is the primary runtime for this project.
    {
        "slug": "lm_studio",
        "display_name": "LM Studio (local)",
        "litellm_prefix": "lm_studio",
        # Taken from settings so the value is correct whether the backend runs
        # natively (localhost) or in Docker (host.docker.internal).
        "api_base": settings.lm_studio_api_base,
        "api_key_env_var": None,
        "requires_api_key": False,
        "is_local": True,
        "notes": "OpenAI-compatible local server. Start LM Studio, load a model "
                 "and enable the local server on port 1234, then POST to "
                 "/api/v1/providers/lm-studio/sync. Note that its API accepts "
                 "response_format 'json_schema' or 'text' only — 'json_object' "
                 "is rejected, and the call layer maps it across automatically.",
    },
    {
        "slug": "ollama",
        "display_name": "Ollama (local)",
        "litellm_prefix": "ollama_chat",
        "api_base": settings.ollama_api_base,
        "requires_api_key": False,
        "is_local": True,
        "is_enabled": False,
        "notes": "Secondary local runtime, kept as a cross-check option. Disabled "
                 "by default; enable the row to make it selectable.",
    },
    {
        "slug": "openai",
        "display_name": "OpenAI",
        "litellm_prefix": "openai",
        "api_base": None,
        "api_key_env_var": "OPENAI_API_KEY",
        "requires_api_key": True,
        "is_local": False,
        "is_enabled": False,
        "notes": "Hosted baseline. Disabled by default; set OPENAI_API_KEY and "
                 "enable the row to make it selectable.",
    },
    {
        "slug": "anthropic",
        "display_name": "Anthropic",
        "litellm_prefix": "anthropic",
        "api_base": None,
        "api_key_env_var": "ANTHROPIC_API_KEY",
        "requires_api_key": True,
        "is_local": False,
        "is_enabled": False,
        "notes": "Hosted baseline. Disabled by default; set ANTHROPIC_API_KEY and "
                 "enable the row to make it selectable.",
    },
]

#: The catalogue ships EMPTY for local runtimes.
#:
#: It used to carry three plausible LM Studio entries as a starting point, which
#: was a mistake: the dropdown offered models the researcher had never
#: downloaded, and picking one failed at inference time with a confusing
#: provider error. What is *installed* is knowable — `POST
#: /providers/lm-studio/sync` reads it from the running server — so guessing is
#: both unnecessary and misleading.
#:
#: Hosted providers are different: their catalogue is fixed and public, so
#: naming a few known-good models costs nothing and saves typing.
MODELS: list[dict] = []

#: Placeholder rows seeded by earlier versions. Removed on startup when nothing
#: references them; kept when they do, because an execution must always resolve
#: to the model row it ran against.
LEGACY_PLACEHOLDER_KEYS: tuple[str, ...] = (
    "qwen2.5-7b-instruct",
    "llama-3.1-8b-instruct",
    "mistral-7b-instruct-v0.3",
)


async def _seed_providers(session: AsyncSession) -> dict[str, LlmProvider]:
    result: dict[str, LlmProvider] = {}
    for spec in PROVIDERS:
        row = (
            await session.execute(
                select(LlmProvider).where(LlmProvider.slug == spec["slug"])
            )
        ).scalar_one_or_none()
        if row is None:
            row = LlmProvider(**spec)
            session.add(row)
            await session.flush()
            logger.info("seeded_provider", extra={"slug": spec["slug"]})
        else:
            desired = spec.get("is_enabled", True)
            if row.is_enabled != desired:
                logger.info(
                    "updated_provider_enabled",
                    extra={"slug": spec["slug"], "is_enabled": desired},
                )
                row.is_enabled = desired
                await session.flush()

        if row.is_local and row.api_base != spec["api_base"]:
            # Self-heal: the correct endpoint differs between a native run and a
            # containerised one, and a stale row would silently route every
            # local inference at the wrong host.
            logger.info(
                "updated_provider_api_base",
                extra={"slug": spec["slug"], "from": row.api_base, "to": spec["api_base"]},
            )
            row.api_base = spec["api_base"]
            await session.flush()
        result[spec["slug"]] = row
    return result


async def _remove_unused_placeholders(
    session: AsyncSession, providers: dict[str, LlmProvider]
) -> int:
    """Drop placeholder models nothing has ever run against.

    A model row referenced by an execution is never deleted: traceability
    requires that a past result still resolves to the model it used. Only
    untouched placeholders go.
    """
    provider = providers.get("lm_studio")
    if provider is None:
        return 0

    candidates = (
        await session.execute(
            select(LlmModel).where(
                LlmModel.provider_id == provider.id,
                LlmModel.model_key.in_(LEGACY_PLACEHOLDER_KEYS),
            )
        )
    ).scalars().all()

    removed = 0
    for model in candidates:
        used = (
            await session.execute(
                select(func.count(Execution.id)).where(Execution.llm_model_id == model.id)
            )
        ).scalar_one()
        if used:
            logger.info(
                "placeholder_kept",
                extra={"model": model.model_key, "executions": used},
            )
            continue

        # Configurations pointing at it go too; they are equally fictional.
        await session.execute(
            delete(SamplingConfiguration).where(SamplingConfiguration.model_id == model.id)
        )
        await session.delete(model)
        removed += 1
        logger.info("placeholder_removed", extra={"model": model.model_key})

    if removed:
        await session.flush()
    return removed


async def _seed_models(session: AsyncSession, providers: dict[str, LlmProvider]) -> list[LlmModel]:
    created: list[LlmModel] = []
    for spec in MODELS:
        provider = providers[spec["provider"]]
        existing = (
            await session.execute(
                select(LlmModel).where(
                    LlmModel.provider_id == provider.id,
                    LlmModel.model_key == spec["model_key"],
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            created.append(existing)
            continue
        payload = {k: v for k, v in spec.items() if k != "provider"}
        row = LlmModel(provider_id=provider.id, **payload)
        session.add(row)
        await session.flush()
        created.append(row)
        logger.info("seeded_model", extra={"model": spec["model_key"]})
    return created


async def _resolve_artefact_version(
    session: AsyncSession, model_cls, name: str, version: str, digest: str
) -> str | None:
    """Decide which version tag a generated prompt artefact should be stored under.

    Returns the version to insert, or ``None`` when the exact content is already
    present and nothing needs writing.

    Two separate keys are in play and conflating them is what broke the seed
    before: idempotency was tested on ``content_sha256`` while the table's
    unique constraint is on ``(name, version)``. Regenerating the technical
    context after a domain change produced new content under the same name and
    version, so the insert always violated the constraint and the container
    restart-looped.

    Prompt versions are immutable — a published result must resolve to the exact
    bytes that produced it — so an existing row is never overwritten. When the
    generated text has drifted without a version bump, the new content is filed
    under a content-addressed suffix instead, which keeps history intact and
    makes the drift visible rather than silent.
    """
    by_digest = (
        await session.execute(select(model_cls).where(model_cls.content_sha256 == digest))
    ).scalar_one_or_none()
    if by_digest is not None:
        return None

    by_name = (
        await session.execute(
            select(model_cls).where(model_cls.name == name, model_cls.version == version)
        )
    ).scalar_one_or_none()
    if by_name is None:
        return version

    suffixed = f"{version}+{digest[:8]}"
    logger.warning(
        "generated_prompt_drifted",
        extra={
            "artefact": model_cls.__name__,
            "artefact_name": name,
            "declared_version": version,
            "stored_under": suffixed,
        },
    )
    return suffixed


async def _deactivate_generated(session: AsyncSession, model_cls) -> None:
    """Only one generated default may be active at a time."""
    await session.execute(
        update(model_cls)
        .where(model_cls.is_system_default.is_(True))
        .values(is_active=False, is_system_default=False)
    )


async def _seed_prompts(session: AsyncSession) -> None:
    # ── Block 1 ─────────────────────────────────────────────────────────────
    digest = _sha(SYSTEM_PROMPT)
    version = await _resolve_artefact_version(
        session, SystemPromptVersion, SYSTEM_PROMPT_NAME, SYSTEM_PROMPT_VERSION, digest
    )
    if version is not None:
        await _deactivate_generated(session, SystemPromptVersion)
        session.add(
            SystemPromptVersion(
                name=SYSTEM_PROMPT_NAME,
                version=version,
                content=SYSTEM_PROMPT,
                content_sha256=digest,
                description="Baseline behaviour contract derived from the HANDi EPN V3 manuals.",
                char_count=len(SYSTEM_PROMPT),
                is_active=True,
                is_system_default=True,
            )
        )
        await session.flush()
        logger.info("seeded_system_prompt", extra={"version": version})

    # ── Block 4: the hardware contract, open and close only ─────────────────
    #
    # One row, not one per limit profile. The reduced contract has no actuator
    # table, so nothing in its text depends on the profile's bounds: seeding
    # three identical rows under three names would file a variable that does not
    # vary and invite a comparison between prompts that are byte-identical.
    #
    # The profile itself still matters — it bounds the poses the validator
    # accepts — and is still recorded on the execution. It just no longer
    # reaches the model, because the model no longer names positions.
    profile = get_limit_profile(LimitProfileId.TABLE_5_V3)
    content = build_technical_context_open_close()
    digest = _sha(content)
    version = await _resolve_artefact_version(
        session,
        TechnicalContextVersion,
        TECHNICAL_CONTEXT_OPEN_CLOSE_NAME,
        TECHNICAL_CONTEXT_OPEN_CLOSE_VERSION,
        digest,
    )
    if version is not None:
        await _deactivate_generated(session, TechnicalContextVersion)
        session.add(
            TechnicalContextVersion(
                name=TECHNICAL_CONTEXT_OPEN_CLOSE_NAME,
                version=version,
                content=content,
                content_sha256=digest,
                description=(
                    "Open, close, or do nothing. The fourteen-gesture contract is "
                    "not a version of this text: it describes a different "
                    "capability set, and executions run under the two are not "
                    "comparable."
                ),
                char_count=len(content),
                is_active=True,
                is_system_default=True,
                limit_profile=profile.id.value,
                generated_from_domain=True,
                includes_json_schema=False,
            )
        )
        await session.flush()
        logger.info("seeded_technical_context", extra={"version": version})

    # ── Block 2: EMG knowledge ──────────────────────────────────────────────
    emg_text = build_emg_context()
    digest = _sha(emg_text)
    version = await _resolve_artefact_version(
        session, EmgContextVersion, EMG_CONTEXT_NAME, EMG_CONTEXT_VERSION, digest
    )
    if version is not None:
        await _deactivate_generated(session, EmgContextVersion)
        session.add(
            EmgContextVersion(
                name=EMG_CONTEXT_NAME,
                version=version,
                content=emg_text,
                content_sha256=digest,
                description=(
                    "Electrode map and interpretation guidance. Separate from the "
                    "hardware description so it can be revised as a variable."
                ),
                char_count=len(emg_text),
                is_active=True,
                is_system_default=True,
                generated_from_domain=True,
            )
        )
        await session.flush()
        logger.info("seeded_emg_context", extra={"version": version})

    # No dynamic template is seeded. The user turn is generated from the
    # analysis — the feature table and the picture — so there is no text a
    # researcher could edit without editing what the numbers mean. The
    # `dynamic_prompt_templates` table is left in place for the executions
    # already recorded against it; migration 0011 decides its fate.


async def _backfill_missing_configurations(session: AsyncSession) -> int:
    """Give every model at least one way to be run.

    Models imported before the import step created configurations are otherwise
    unusable: `canRun` requires a configuration, so the Run button stays
    disabled with nothing on screen to explain it.
    """
    models = (
        await session.execute(
            select(LlmModel).where(
                ~select(SamplingConfiguration.id)
                .where(SamplingConfiguration.model_id == LlmModel.id)
                .exists()
            )
        )
    ).scalars().all()

    for model in models:
        session.add(
            SamplingConfiguration(
                name=f"Deterministic · {model.display_name}",
                description="Greedy baseline: temperature 0, fixed seed.",
                model_id=model.id,
                temperature=0.0,
                top_p=1.0,
                max_tokens=320,
                seed=42,
                frequency_penalty=0.0,
                presence_penalty=0.0,
                stop_sequences=[],
                response_format="json_schema" if model.supports_json_schema else "json_object",
                extra_params={},
                is_favorite=True,
            )
        )
        logger.info("backfilled_configuration", extra={"model": model.model_key})

    if models:
        await session.flush()
    return len(models)


async def _seed_configurations(session: AsyncSession, models: list[LlmModel]) -> None:
    """A deterministic default per model.

    Temperature 0 / top_p 1 / fixed seed is the correct starting point for this
    task: we are measuring instruction adherence, not creativity.
    """
    for model in models:
        name = f"Deterministic - {model.display_name}"
        existing = (
            await session.execute(
                select(SamplingConfiguration).where(
                    SamplingConfiguration.name == name,
                    SamplingConfiguration.model_id == model.id,
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            continue
        session.add(
            SamplingConfiguration(
                name=name,
                description="Greedy decoding baseline: temperature 0, fixed seed. "
                            "Use this as the control condition.",
                model_id=model.id,
                temperature=0.0,
                top_p=1.0,
                top_k=None,
                # The reply is a command line: one to four tokens. 64 is
                # ample headroom, and every token beyond it is budget taken
                # from the EMG matrix.
                max_tokens=320,
                seed=42 if model.supports_seed else None,
                frequency_penalty=0.0,
                presence_penalty=0.0,
                response_format="json_schema" if model.supports_json_schema else "json_object",
                is_favorite=True,
            )
        )
        logger.info("seeded_configuration", extra={"model": model.model_key})


async def seed() -> None:
    configure_logging()
    async with AsyncSessionLocal() as session:
        providers = await _seed_providers(session)
        await _remove_unused_placeholders(session, providers)
        models = await _seed_models(session, providers)
        await _seed_prompts(session)
        await _seed_configurations(session, models)
        await _backfill_missing_configurations(session)
        await session.commit()
    logger.info("seed_complete")


if __name__ == "__main__":
    asyncio.run(seed())
