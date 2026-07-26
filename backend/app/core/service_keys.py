"""T3.12 pt.1 — every account gets a service keypair, idempotently, on startup.

A *service key* is not the user's identity (see `D-KEY-IS-IDENTITY`). It is the
key the platform uses to encrypt that user's vault contents and to sign their
records. The user never sees it and it is never published outside. Identity
begins later, at `establish identity`, and always with a *different* key.

Why this runs at startup rather than inside migration `0029`:

- The project's migrations are plain SQL. Generating keypairs needs
  `app.core.keypair`, which needs `NSEC_ENCRYPTION_KEY` — importing app code
  into a migration couples schema history to runtime config.
- It has to be idempotent anyway: accounts predating T2.2 exist, and accounts
  created by a rollback would need it again.
- `ensure_user_zero` already establishes this pattern in `main.lifespan`.

Consequence to keep in mind: `users.nostr_pubkey` cannot become NOT NULL until
this has run everywhere. That constraint is deliberately left for a follow-up
migration, after prod shows zero NULLs.

Fixes a live defect on the way: the arbiter account has no keypair, and
`api/threshold.py` requires `arbiter.nostr_pubkey` — meaning threshold 2-of-3
could not be assembled at all. Backfilling the arbiter repairs it.
"""
from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.keypair import encrypt_nsec, generate_keypair
from app.models.user import User

logger = logging.getLogger(__name__)


async def ensure_service_keys(db: AsyncSession) -> int:
    """Give a service keypair to every account that has none. Returns the count.

    Accounts that already hold a key — service or identity — are left alone:
    replacing a key that has signed records would orphan those signatures, and
    replacing an identity key is precisely what this phase forbids.
    """
    result = await db.execute(select(User).where(User.nostr_pubkey.is_(None)))
    users = list(result.scalars().all())
    if not users:
        return 0

    for user in users:
        nsec_hex, npub_hex = generate_keypair()
        nonce, ciphertext = encrypt_nsec(nsec_hex)
        user.nostr_pubkey = npub_hex
        user.nsec_encrypted = ciphertext
        user.nsec_nonce = nonce
        user.key_self_custody = False

    await db.commit()
    logger.info("ensure_service_keys issued %d service keypairs", len(users))
    return len(users)
