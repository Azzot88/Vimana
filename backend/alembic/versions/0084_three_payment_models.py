"""T3.11.07 — three settlement models, and answering becomes obligatory.

Owner's decision 2026-09-08, replacing the two optional models of 2026-09-06:

    cash_on_delivery    — наличными при получении
    emoney_on_delivery  — электронными деньгами при получении
    platform_wallet     — с кошелька на платформе

The previous revision folded the first two into `off_platform`, reasoning that
«cash or transfer?» is the same question as «which system?». Right about the
words, wrong about the people: cash is settled hand to hand at the door and
e-money by two phones, and a sender who cannot carry notes needs to know which
before they agree, not after.

**Existing rows are mapped, never guessed at.** `on_platform` becomes
`platform_wallet`. `off_platform` splits on evidence already in the row: a
carrier who named a payment system was answering «электронными», one who named
none was answering «наличными». Rows that said nothing stay NULL — the column
stays nullable because a trip published before the question existed did not
answer it, and filling it in would be the platform speaking for its carriers.
Obligatory is enforced at the API (`TripCreate.payment_model`), which is where
new trips pass and old rows do not.

Revision ID: 0084
Revises: 0083
Create Date: 2026-09-08
"""
from alembic import op


revision = "0084"
down_revision = "0083"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # The constraint goes first: it names the old vocabulary and would refuse
    # every UPDATE below.
    op.execute("ALTER TABLE trips DROP CONSTRAINT IF EXISTS ck_trips_payment_model")
    op.execute(
        "UPDATE trips SET payment_model = 'platform_wallet' "
        "WHERE payment_model = 'on_platform'"
    )
    # `jsonb_array_length` would need a cast and a null guard on every row;
    # comparing the JSON text to the two shapes of "no systems" is exact and
    # reads the same as the sentence above it.
    op.execute(
        "UPDATE trips SET payment_model = 'emoney_on_delivery' "
        "WHERE payment_model = 'off_platform' "
        "  AND payment_systems IS NOT NULL "
        "  AND payment_systems::text NOT IN ('[]', 'null')"
    )
    op.execute(
        "UPDATE trips SET payment_model = 'cash_on_delivery' "
        "WHERE payment_model = 'off_platform'"
    )
    op.execute(
        "ALTER TABLE trips ADD CONSTRAINT ck_trips_payment_model CHECK ("
        "payment_model IS NULL OR payment_model IN "
        "('cash_on_delivery','emoney_on_delivery','platform_wallet'))"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE trips DROP CONSTRAINT IF EXISTS ck_trips_payment_model")
    op.execute(
        "UPDATE trips SET payment_model = 'on_platform' "
        "WHERE payment_model = 'platform_wallet'"
    )
    op.execute(
        "UPDATE trips SET payment_model = 'off_platform' "
        "WHERE payment_model IN ('cash_on_delivery','emoney_on_delivery')"
    )
    op.execute(
        "ALTER TABLE trips ADD CONSTRAINT ck_trips_payment_model CHECK ("
        "payment_model IS NULL OR payment_model IN "
        "('on_platform','off_platform'))"
    )
