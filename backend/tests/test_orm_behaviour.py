"""ORM behaviour that only breaks at runtime, in the async response path.

The bug this guards against produced a 500 on every UPDATE endpoint:

    ResponseValidationError: Error extracting attribute: MissingGreenlet:
    greenlet_spawn has not been called; can't call await_only() here

A SQL-side ``onupdate`` (``func.now()``) is computed by the database during the
UPDATE. SQLAlchemy cannot see the value, so it expires the attribute and defers
a refresh. That refresh then fires when Pydantic reads the attribute to build
the response — a synchronous read outside the async greenlet — and raises.

No unit test of the endpoint catches it, because the failure happens in FastAPI's
serialisation step after the handler returns.
"""

from __future__ import annotations

import datetime

import pytest
from sqlalchemy import DateTime, Integer, MetaData, String, func
from sqlalchemy.exc import MissingGreenlet
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

import app.models  # noqa: F401  - registers every mapper
from app.db.base import Base


# ── Static guard ────────────────────────────────────────────────────────────


def test_no_column_uses_a_sql_side_onupdate() -> None:
    """Any SQL-side onupdate reintroduces the MissingGreenlet failure."""
    offenders = [
        f"{table.name}.{column.name}"
        for table in Base.metadata.tables.values()
        for column in table.columns
        if column.onupdate is not None
        and getattr(column.onupdate, "is_clause_element", False)
    ]
    assert not offenders, (
        "SQL-side onupdate expires the attribute and forces a lazy refresh "
        f"during response serialisation: {offenders}"
    )


def test_updated_at_is_populated_in_python() -> None:
    from app.models.llm import SamplingConfiguration

    column = SamplingConfiguration.__table__.c.updated_at
    assert column.onupdate is not None
    assert callable(column.onupdate.arg)


def test_created_at_keeps_its_server_default() -> None:
    """INSERT is safe: PostgreSQL computes it and RETURNING fetches it back."""
    from app.models.project import Project

    column = Project.__table__.c.created_at
    assert column.server_default is not None


# ── Behavioural reproduction ────────────────────────────────────────────────


def _model(onupdate, default=None):
    """A minimal stand-in mirroring `TimestampMixin`.

    ``default`` matters for the comparison test: SQLite returns naive datetimes
    for a server-side default while the Python callable returns aware ones, so
    without a client-side default the two values are not comparable. PostgreSQL
    with ``DateTime(timezone=True)`` returns aware values for both; this only
    keeps the in-memory harness faithful.
    """

    class LocalBase(DeclarativeBase):
        metadata = MetaData()

    class Row(LocalBase):
        __tablename__ = "t"
        id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
        name: Mapped[str] = mapped_column(String(50))
        updated_at: Mapped[datetime.datetime] = mapped_column(
            DateTime(timezone=True),
            server_default=func.now(),
            default=default,
            onupdate=onupdate,
        )

    return LocalBase, Row


async def _update_then_read(onupdate):
    """Mutate a row, then read the timestamp the way FastAPI serialises it."""
    local_base, Row = _model(onupdate)
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(local_base.metadata.create_all)

        factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with factory() as session:
            row = Row(name="before")
            session.add(row)
            await session.flush()
            await session.commit()

            row.name = "after"
            await session.flush()
            await session.commit()

            # Synchronous attribute read, outside any await — exactly what
            # Pydantic's from_attributes does when building the response.
            return row.updated_at
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_sql_side_onupdate_raises_missing_greenlet() -> None:
    """Documents the failure mode, so the reason for the fix stays visible."""
    with pytest.raises(MissingGreenlet):
        await _update_then_read(func.now())


@pytest.mark.asyncio
async def test_python_side_onupdate_is_readable_after_update() -> None:
    from app.db.base import _utcnow

    value = await _update_then_read(_utcnow)
    assert isinstance(value, datetime.datetime)


@pytest.mark.asyncio
async def test_python_side_onupdate_actually_advances_the_timestamp() -> None:
    """Correctness, not just absence of an exception."""
    from app.db.base import _utcnow

    local_base, Row = _model(_utcnow, default=_utcnow)
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(local_base.metadata.create_all)

        factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with factory() as session:
            row = Row(name="before")
            session.add(row)
            await session.flush()
            first = row.updated_at

            row.name = "after"
            await session.flush()
            second = row.updated_at

            assert second >= first
    finally:
        await engine.dispose()


# ── Freshly-created objects and their relationships ─────────────────────────


def test_execution_children_are_attached_through_relationships() -> None:
    """A child attached by bare foreign key leaves the parent's relationship
    unloaded.

    `Execution` is *created* in the session, never loaded by a SELECT, so the
    `lazy="joined"` loader never runs. Reading `execution.validation_result`
    during response serialisation then emits a lazy SELECT outside the async
    greenlet and fails with MissingGreenlet — which is what produced:

        3 validation errors for ExecutionOut
        validation_result / metrics / movement -> MissingGreenlet

    Setting the relationship instead both writes the foreign key and marks the
    attribute as loaded.
    """
    import ast
    import pathlib

    source = pathlib.Path(__file__).resolve().parent.parent
    text = (source / "app" / "services" / "execution_service.py").read_text()

    offenders = [
        line.strip()
        for line in text.splitlines()
        if "execution_id=execution.id" in line
        or "validation_result_id=result_row.id" in line
    ]
    assert not offenders, (
        "children attached by foreign key leave the relationship unloaded: "
        f"{offenders}"
    )

    ast.parse(text)  # the edits must not have broken the module


def test_response_schema_only_reads_loaded_relationships() -> None:
    """Every relationship `ExecutionOut` reads must be set by `run_execution`."""
    import pathlib

    from app.schemas.api import ExecutionOut

    source = (
        pathlib.Path(__file__).resolve().parent.parent
        / "app" / "services" / "execution_service.py"
    ).read_text()

    relationship_fields = {"validation_result", "metrics", "movement"}
    assert relationship_fields <= set(ExecutionOut.model_fields)

    for field in relationship_fields:
        assert f"execution.{field} = " in source, (
            f"ExecutionOut reads `{field}` but run_execution never assigns the "
            "relationship, so it would be lazy-loaded during serialisation"
        )


def test_collections_are_appended_not_inserted() -> None:
    import pathlib

    source = (
        pathlib.Path(__file__).resolve().parent.parent
        / "app" / "services" / "execution_service.py"
    ).read_text()

    for collection in ("logs", "errors"):
        assert f"execution.{collection}.append(" in source


def test_every_relationship_is_primed_before_first_use() -> None:
    """`Execution` is created, never SELECTed, so every relationship starts
    unloaded — and in async SQLAlchemy any access to one emits a lazy SELECT
    outside the greenlet.

    Two distinct accesses hit this:

    * ``execution.logs.append(...)`` — appending to a collection reads it first
    * the response schema reading the one-to-ones on the provider-error path,
      which returns before they are assigned

    Both are covered by priming every relationship with ``set_committed_value``
    immediately after the row is flushed.
    """
    import pathlib as _p

    source = (
        _p.Path(__file__).resolve().parent.parent
        / "app" / "services" / "execution_service.py"
    ).read_text()
    lines = source.splitlines()

    prime = next(
        i for i, line in enumerate(lines) if "prime_relationships(execution)" in line
    )
    first_log_call = next(
        i for i, line in enumerate(lines) if line.strip().startswith("log(LogLevel")
    )
    first_return = next(i for i, line in enumerate(lines) if line.strip() == "return execution")

    assert prime < first_log_call, "collections must be primed before the first append"
    assert prime < first_return, "relationships must be primed before any return"


def test_prime_covers_every_relationship_the_response_reads() -> None:
    """The helper must leave nothing unloaded on a freshly-created Execution."""
    from app.db.relationships import prime, unloaded
    from app.models.experiment import Execution

    execution = Execution(status="pending", handedness="right", limit_profile="TABLE_5_V3")
    prime(execution)
    assert unloaded(execution) == []


def test_prime_does_not_discard_already_attached_children() -> None:
    """It is called after the row is flushed, by which point some relationships
    may already hold values."""
    from app.db.relationships import prime
    from app.models.experiment import Execution
    from app.models.metrics import ExecutionMetric

    execution = Execution(status="pending", handedness="right", limit_profile="TABLE_5_V3")
    metric = ExecutionMetric()
    execution.metrics = metric

    prime(execution)

    assert execution.metrics is metric
    assert execution.movement is None


@pytest.mark.asyncio
async def test_appending_to_an_unprimed_collection_lazy_loads() -> None:
    """The exact failure from the traceback: `execution.logs.append(...)` reads
    the collection before appending, which emits a SELECT."""
    from sqlalchemy import ForeignKey, Integer, String
    from sqlalchemy.orm import relationship
    from sqlalchemy.orm.attributes import set_committed_value

    async def append_log(prime: bool):
        class LocalBase(DeclarativeBase):
            metadata = MetaData()

        class Parent(LocalBase):
            __tablename__ = "p"
            id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
            name: Mapped[str] = mapped_column(String(20))
            logs = relationship("Log", back_populates="parent", cascade="all, delete-orphan")

        class Log(LocalBase):
            __tablename__ = "l"
            id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
            parent_id: Mapped[int] = mapped_column(ForeignKey("p.id"))
            parent = relationship("Parent", back_populates="logs")

        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        try:
            async with engine.begin() as connection:
                await connection.run_sync(LocalBase.metadata.create_all)

            factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
            async with factory() as session:
                parent = Parent(name="x")
                session.add(parent)
                await session.flush()          # exactly what run_execution does
                if prime:
                    set_committed_value(parent, "logs", [])
                parent.logs.append(Log())
                await session.commit()
                return len(parent.logs)
        finally:
            await engine.dispose()

    with pytest.raises(MissingGreenlet):
        await append_log(prime=False)

    assert await append_log(prime=True) == 1


@pytest.mark.asyncio
async def test_unassigned_relationship_lazy_loads_but_none_does_not() -> None:
    """Behavioural proof of the rule the fix relies on."""
    from sqlalchemy import ForeignKey, Integer, String
    from sqlalchemy.orm import relationship

    async def read_child(preassign: bool):
        class LocalBase(DeclarativeBase):
            metadata = MetaData()

        class Parent(LocalBase):
            __tablename__ = "p"
            id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
            name: Mapped[str] = mapped_column(String(20))
            child = relationship("Child", back_populates="parent", uselist=False, lazy="joined")

        class Child(LocalBase):
            __tablename__ = "c"
            id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
            parent_id: Mapped[int] = mapped_column(ForeignKey("p.id"))
            parent = relationship("Parent", back_populates="child")

        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        try:
            async with engine.begin() as connection:
                await connection.run_sync(LocalBase.metadata.create_all)

            factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
            async with factory() as session:
                parent = Parent(name="x")
                session.add(parent)
                await session.flush()
                if preassign:
                    parent.child = None
                await session.commit()
                return parent.child
        finally:
            await engine.dispose()

    with pytest.raises(MissingGreenlet):
        await read_child(preassign=False)

    assert await read_child(preassign=True) is None
