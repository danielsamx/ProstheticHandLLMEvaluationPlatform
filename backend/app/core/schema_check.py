"""Startup check: does the live database match the mapped models?

A pending migration does not announce itself. The application starts, serves
reference data happily, and then dies on the first INSERT that touches a missing
column — which surfaces in the browser as a dropped connection with no
explanation at all.

Checking once at startup turns that into a single, actionable log line.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.logging import get_logger
from app.db.base import Base

logger = get_logger(__name__)


@dataclass(slots=True)
class SchemaReport:
    ok: bool = True
    missing_tables: list[str] = field(default_factory=list)
    missing_columns: dict[str, list[str]] = field(default_factory=dict)
    alembic_revision: str | None = None
    error: str | None = None

    def summary(self) -> str:
        if self.error:
            return f"Schema check could not run: {self.error}"
        if self.ok:
            return "Database schema matches the mapped models."
        parts = []
        if self.missing_tables:
            parts.append(f"missing tables: {', '.join(sorted(self.missing_tables))}")
        if self.missing_columns:
            detail = "; ".join(
                f"{table} -> {', '.join(cols)}"
                for table, cols in sorted(self.missing_columns.items())
            )
            parts.append(f"missing columns: {detail}")
        return "Database schema is behind the models — " + " | ".join(parts)


async def inspect_schema(engine: AsyncEngine) -> SchemaReport:
    """Compare live tables and columns against ``Base.metadata``."""
    report = SchemaReport()

    try:
        async with engine.connect() as connection:
            def _read(sync_connection) -> tuple[set[str], dict[str, set[str]]]:
                inspector = inspect(sync_connection)
                names = set(inspector.get_table_names())
                columns = {
                    name: {c["name"] for c in inspector.get_columns(name)}
                    for name in names
                }
                return names, columns

            live_tables, live_columns = await connection.run_sync(_read)

            try:
                revision = await connection.execute(
                    text("SELECT version_num FROM alembic_version LIMIT 1")
                )
                row = revision.first()
                report.alembic_revision = row[0] if row else None
            except Exception:
                report.alembic_revision = None
    except Exception as exc:
        report.error = f"{type(exc).__name__}: {exc}"
        report.ok = False
        return report

    for table_name, table in Base.metadata.tables.items():
        if table_name not in live_tables:
            report.missing_tables.append(table_name)
            continue
        expected = {column.name for column in table.columns}
        missing = sorted(expected - live_columns.get(table_name, set()))
        if missing:
            report.missing_columns[table_name] = missing

    report.ok = not report.missing_tables and not report.missing_columns
    return report


async def check_and_log(engine: AsyncEngine) -> SchemaReport:
    """Run the check and log the outcome at a level that matches its severity."""
    report = await inspect_schema(engine)

    if report.error:
        logger.error("schema_check_failed", extra={"detail": report.error})
    elif report.ok:
        logger.info(
            "schema_ok",
            extra={
                "tables": len(Base.metadata.tables),
                "alembic_revision": report.alembic_revision,
            },
        )
    else:
        logger.error(
            "schema_out_of_date",
            extra={
                "summary": report.summary(),
                "alembic_revision": report.alembic_revision,
                "remedy": "Run `alembic upgrade head`. With Docker: "
                          "`docker compose down && docker compose up --build`.",
            },
        )

    return report
