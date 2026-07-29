"""Get-or-create for the distinct frozen prompt setups.

One row per distinct combination of the three frozen blocks, created the first
time that combination runs and reused every time afterwards. Three experiments
under two distinct setups leave two rows, and going back to the first setup
finds the row it already made rather than adding a third.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.prompt_configuration import PromptConfiguration


def describe(system: str | None, technical: str | None, emg: str | None) -> str:
    """`S1.0 · T1.0 · E1.0` — the three versions, in block order.

    Short enough to sit in a table column, and ordered so two labels can be
    compared at a glance to see which block moved. An edited block with no
    version of its own shows as `?`, which is the honest answer: the text was
    supplied per request and belongs to no artefact.
    """
    return " · ".join([
        f"S{system or '?'}",
        f"T{technical or '?'}",
        f"E{emg or '?'}",
    ])


async def resolve(
    session: AsyncSession,
    *,
    frozen_context_sha256: str,
    frozen_context_text: str,
    system_version=None,
    technical_version=None,
    emg_version=None,
) -> PromptConfiguration:
    """Find the configuration for this frozen context, or create it.

    Matched on the digest rather than on the three version ids. The digest is
    computed from the text that was actually assembled, so it catches what the
    ids cannot: a block edited in place without a version bump, or an override
    passed with the request that points at no artefact at all. Two runs whose
    ids agree but whose text differs are not the same configuration, and
    treating them as one is the kind of error that survives into a conclusion.

    ``last_used_at`` is touched on every hit, which is what lets the dashboard
    order configurations by recency rather than by when they were first seen —
    the setup you were using this morning is the one you want at the top.
    """
    existing = (
        await session.execute(
            select(PromptConfiguration).where(
                PromptConfiguration.frozen_context_sha256 == frozen_context_sha256
            )
        )
    ).scalar_one_or_none()

    if existing is not None:
        existing.last_used_at = datetime.now(timezone.utc)
        return existing

    configuration = PromptConfiguration(
        frozen_context_sha256=frozen_context_sha256,
        frozen_context_text=frozen_context_text,
        label=describe(
            getattr(system_version, "version", None),
            getattr(technical_version, "version", None),
            getattr(emg_version, "version", None),
        ),
        system_prompt_version_id=getattr(system_version, "id", None),
        technical_context_version_id=getattr(technical_version, "id", None),
        emg_context_version_id=getattr(emg_version, "id", None),
        system_prompt_version=getattr(system_version, "version", None),
        technical_context_version=getattr(technical_version, "version", None),
        emg_context_version=getattr(emg_version, "version", None),
    )
    session.add(configuration)
    await session.flush()
    return configuration
