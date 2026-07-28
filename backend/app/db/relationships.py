"""Priming relationships on freshly-created ORM objects.

In async SQLAlchemy, touching an *unloaded* relationship emits a lazy SELECT
outside the greenlet and raises ``MissingGreenlet``. Objects loaded by a query
are fine — their eager loaders ran. Objects **created** in the session are not:
``session.flush()`` makes them persistent, and their relationships become
unloaded rather than empty.

Two ordinary-looking operations then fail:

* ``parent.children.append(child)`` — appending reads the collection first
* ``ParentOut.model_validate(parent)`` — Pydantic reads every mapped attribute

Both are silent until runtime, and the traceback points at the append or the
serialiser rather than at the missing load, which makes them expensive to
diagnose. Calling :func:`prime` right after the flush removes the whole class.
"""

from __future__ import annotations

from typing import Any, Iterable

from sqlalchemy import inspect
from sqlalchemy.orm.attributes import set_committed_value


def prime(instance: Any, only: Iterable[str] | None = None) -> None:
    """Mark relationships as loaded-and-empty on a newly-created object.

    ``set_committed_value`` records the value as though it had been loaded,
    bypassing both the loader and the cascade machinery — which is what makes it
    safe here, where a plain assignment would still consult the old value.

    Already-populated relationships are left untouched, so this is safe to call
    after some children have been attached.

    Parameters
    ----------
    instance:
        A mapped object that was created (not loaded) in this session.
    only:
        Restrict to these relationship names. Defaults to all of them.
    """
    mapper = inspect(instance).mapper
    state = inspect(instance)
    wanted = set(only) if only is not None else None

    for relationship in mapper.relationships:
        name = relationship.key
        if wanted is not None and name not in wanted:
            continue
        # Skip anything already loaded or explicitly set: overwriting would
        # discard children the caller has just attached.
        if name in state.dict:
            continue
        set_committed_value(instance, name, [] if relationship.uselist else None)


def unloaded(instance: Any) -> list[str]:
    """Relationship names that would trigger a lazy load if touched.

    Useful in tests and when diagnosing a MissingGreenlet: it names the
    attribute before something else reads it.
    """
    state = inspect(instance)
    return [
        relationship.key
        for relationship in state.mapper.relationships
        if relationship.key not in state.dict
    ]
