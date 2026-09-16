"""T_DATA.1 — one spelling of «empty» in every JSON column.

A JSON column holds two kinds of empty: SQL NULL and JSON `null`. SQLAlchemy
wrote an explicit Python `None` as the second one, so rows that look empty to a
person are invisible to `IS NULL` — which is how `0093` skipped every cargo it
was written for (`0098` repaired that one field).

The models now declare `none_as_null=True`, so new writes land as SQL NULL.
This brings the rows already written into line. Data only, no schema change:
idempotent, and safe to run twice.

`BACKFILL` is read by `tests/conftest.py` so the shared test database — never
reset — stops carrying the old spelling too.

Revision ID: 0099
Revises: 0098
Create Date: 2026-09-15
"""
from alembic import op

revision = "0099"
down_revision = "0098"
branch_labels = None
depends_on = None


#: Every nullable JSON column in the mapping. The NOT NULL ones
#: (`disputes.passed_over`, `compliance_cases.attrs`/`checklist`,
#: `users.notification_prefs`) are left out: SQL NULL is not available there, so
#: the two spellings never meet.
#:
#: Spelled out rather than generated from a list of pairs — `tests/conftest.py`
#: reads this literal with `ast` and never imports the module, and a
#: comprehension is not a literal.
BACKFILL = [
    "UPDATE deal_events SET payload = NULL WHERE payload::text = 'null'",
    "UPDATE deal_chain_anchors SET relays = NULL WHERE relays::text = 'null'",
    "UPDATE deal_vault_messages SET card_payload = NULL WHERE card_payload::text = 'null'",
    "UPDATE deal_vault_messages SET wrapped_shares = NULL WHERE wrapped_shares::text = 'null'",
    "UPDATE deal_vault_messages SET read_packages = NULL WHERE read_packages::text = 'null'",
    "UPDATE trips SET allowed_categories = NULL WHERE allowed_categories::text = 'null'",
    "UPDATE trips SET handover_origin = NULL WHERE handover_origin::text = 'null'",
    "UPDATE trips SET handover_destination = NULL WHERE handover_destination::text = 'null'",
    "UPDATE trips SET excluded = NULL WHERE excluded::text = 'null'",
    "UPDATE trips SET services = NULL WHERE services::text = 'null'",
    "UPDATE trips SET payment_systems = NULL WHERE payment_systems::text = 'null'",
    "UPDATE cargos SET dimensions_cm = NULL WHERE dimensions_cm::text = 'null'",
    "UPDATE cargo_templates SET dimensions_cm = NULL WHERE dimensions_cm::text = 'null'",
    "UPDATE document_requirements SET condition = NULL WHERE condition::text = 'null'",
    "UPDATE compliance_cases SET transit = NULL WHERE transit::text = 'null'",
    "UPDATE webauthn_credentials SET transports = NULL WHERE transports::text = 'null'",
]


def upgrade() -> None:
    for statement in BACKFILL:
        op.execute(statement)


def downgrade() -> None:
    # Nothing to undo. Writing JSON `null` back would restore the defect, and
    # «no value» is what these rows meant in the first place.
    pass
