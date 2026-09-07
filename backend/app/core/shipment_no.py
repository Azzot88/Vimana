"""T3.11.23 — the number a person says out loud.

Owner's request 2026-09-07: a deal needs «название, цена, номер отправки», and
what it had was a UUID. Nobody dictates `55468906-95a9-4cb1-89e5-56d42384836f`
over the phone and nobody pastes it into a message about a parcel.

**Random, not sequential**, and that is the one decision here worth defending. A
counter is easier and tells every user how many deals the platform has ever had,
every time they look at their own. For a young marketplace that is a number to
keep; and once it is out, it is out of every screenshot anybody ever took.

The alphabet drops what gets misread when it is read aloud or copied by hand:
`0`/`O`, `1`/`I`/`L`. What is left is 31 characters, and eight of them give
about 2×10¹² combinations — enough that a collision is a retry rather than a
design problem, and short enough to say in one breath.
"""

from __future__ import annotations

import secrets

# Crockford's alphabet minus the vowels that make words nobody wants printed on
# their shipment. `U` is the one usually dropped for that reason; the rest go
# because a code that spells something is a code people remember wrong.
ALPHABET = "23456789ACDEFGHJKMNPQRTVWXYZ"

LENGTH = 8


def new_shipment_no() -> str:
    """A fresh code. Not checked for uniqueness here — the column carries the
    unique index, and the caller retries on the conflict.

    Called by: `api.deals.match_deal`, `alembic/0073` (backfill).
    """
    return "".join(secrets.choice(ALPHABET) for _ in range(LENGTH))
