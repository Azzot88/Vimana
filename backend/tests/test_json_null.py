"""T_DATA.1 — «пусто» в JSON-колонке пишется одним способом.

A JSON column can hold two different kinds of empty: SQL NULL («there is no
value») and JSON `null` («the value is null»). SQLAlchemy writes an explicit
Python `None` as the second one unless the column says `none_as_null=True`, and
`IS NULL` is true only for the first.

That difference cost a data move: `0093` filled the cargo's dimensions from the
terms with `COALESCE(c.dimensions_cm, …)`, and every cargo created through the
API without a size held JSON `null` — which `COALESCE` reads as a value already
there. The rows the migration existed for were the rows it skipped.

Two tests, because the defect has two halves: a declaration that permits it, and
a write that performs it.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import JSON, text
from sqlalchemy.dialects.postgresql import JSONB


def test_every_nullable_json_column_says_none_is_null():
    """The declaration. Enumerated from the mapping rather than from a list, so
    a column added next year is covered without anybody remembering this file.
    """
    from app.core.database import Base
    import app.models  # noqa: F401 — imports every model onto the metadata

    offenders = []
    for table in Base.metadata.sorted_tables:
        for column in table.columns:
            if not isinstance(column.type, (JSON, JSONB)):
                continue
            if not column.nullable:
                # NOT NULL columns cannot hold SQL NULL at all, so the two
                # spellings of empty do not meet there.
                continue
            if getattr(column.type, "none_as_null", False) is not True:
                offenders.append(f"{table.name}.{column.name}")

    assert offenders == [], (
        "these JSON columns still write Python None as JSON null: "
        + ", ".join(offenders)
    )


async def test_an_empty_size_is_stored_as_sql_null(
    session_maker, seed_sender, seed_carrier
):
    """The write, end to end: the cargo the API creates without dimensions must
    be invisible to `IS NULL` no longer."""
    from app.models.marketplace import Cargo

    async with session_maker() as db:
        cargo = Cargo(
            created_by_id=seed_sender.id,
            category="document",
            declared_value=10.0,
            currency="USD",
            final_destination="NUL",
            weight_kg=1.0,
            # Exactly how `api/deals.match_deal` writes a cargo whose response
            # carried no size: an explicit None, not an omitted field.
            dimensions_cm=None,
        )
        db.add(cargo)
        await db.commit()
        cargo_id = cargo.id

    async with session_maker() as db:
        stored = (
            await db.execute(
                text("SELECT dimensions_cm::text FROM cargos WHERE id = :id"),
                {"id": str(cargo_id)},
            )
        ).scalar()
        assert stored is None, f"stored as {stored!r} instead of SQL NULL"

        found = (
            await db.execute(
                text(
                    "SELECT count(*) FROM cargos "
                    "WHERE id = :id AND dimensions_cm IS NULL"
                ),
                {"id": str(cargo_id)},
            )
        ).scalar()
        assert found == 1, "the row a migration would look for is invisible to it"
