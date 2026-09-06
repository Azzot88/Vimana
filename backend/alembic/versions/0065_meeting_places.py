"""T3.11.07 — meeting places: a list in the profile, one of them default.

Owner's decision 2026-09-06. The trip form asks where the carrier accepts cargo
and where they hand it over, and "in person" needs somewhere to point at. That
somewhere is not an address.

An address is a place a parcel is *sent* to and carries the structure the post
office needs — country, city, street, postal code. A meeting place is «у метро
Фили, у выхода №3» or «Terminal D, departures, by the Costa»: a sentence one
person says to another. Forcing it into the address table would either refuse
those strings or keep only the half that fits, and the half that matters —
"which exit", "by the coffee place" — is the half that would be lost.

Shaped exactly like `receiving_addresses` otherwise: several per user, at most
one default, enforced by a partial unique index rather than by application code
that has to remember. A carrier meets people in two or three usual spots;
picking one per trip is a choice, not a form to fill in again.

Revision ID: 0065
Revises: 0064
Create Date: 2026-09-06
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "0065"
down_revision = "0064"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "meeting_places",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("description", sa.String(length=300), nullable=False),
        sa.Column(
            "is_default", sa.Boolean(), nullable=False, server_default="false"
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_meeting_places_user_id", "meeting_places", ["user_id"])
    # At most one default per user, enforced by the database. The alternative is
    # application code that has to remember to clear the old default on every
    # path that can set one, and the path somebody forgets is the one that
    # leaves two.
    op.create_index(
        "uq_meeting_places_user_default",
        "meeting_places",
        ["user_id"],
        unique=True,
        postgresql_where=sa.text("is_default"),
    )


def downgrade() -> None:
    op.drop_index("uq_meeting_places_user_default", table_name="meeting_places")
    op.drop_index("ix_meeting_places_user_id", table_name="meeting_places")
    op.drop_table("meeting_places")
