"""T3.12 pt.2b — identity container survives the move to a self-custody key.

Until now a container's AES key *was* the owner's nsec (`core/verification.py`).
That is fine while the platform holds the nsec and fatal the moment it does not:
`establish` destroys the service key, and nothing — not the platform, not the
owner — could open the container again.

New shape: the blob is encrypted with a random content key, and that key is
wrapped NIP-04 to the owner's public key. Re-keying then costs one small
re-wrap instead of re-encrypting the document, and the owner can open it
client-side with a key the server has never seen.

`key_envelope_sender_pubkey` is not redundant: NIP-04 is ECDH between two keys,
so the reader needs to know whose public key completes the exchange. The wrap is
performed with the retiring service key, which exists only at that moment.

Both columns are nullable — legacy containers keep the old scheme until their
owner establishes an identity.

Revision ID: 0030
Revises: 0029
Create Date: 2026-07-26
"""
from alembic import op


revision = "0030"
down_revision = "0029"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE identity_containers "
        "ADD COLUMN IF NOT EXISTS key_envelope TEXT, "
        "ADD COLUMN IF NOT EXISTS key_envelope_sender_pubkey VARCHAR(64)"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE identity_containers "
        "DROP COLUMN IF EXISTS key_envelope, "
        "DROP COLUMN IF EXISTS key_envelope_sender_pubkey"
    )
