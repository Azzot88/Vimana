"""T3.11.23 — the number a person says out loud. T3.12.03 — it belongs to the cargo.

Owner's request 2026-09-07: a deal needs «название, цена, номер отправки», and
what it had was a UUID. Nobody dictates `55468906-95a9-4cb1-89e5-56d42384836f`
over the phone and nobody pastes it into a message about a parcel.

**Format, owner's decision 2026-09-13: `PF-` and eight random digits with a dash
after the third** — `PF-482-19375`. The deal's own number adds its position in
the cargo's chain (`PF-482-19375-1`), derived in `core.cargo.deal_no` and never
stored. Numbers issued before the change keep their eight letters and are shown
without a suffix: they are already in people's mail and chats.

**Random, not sequential**, and that is the one decision here worth defending. A
counter is easier and tells every user how many shipments the platform has ever
had, every time they look at their own. For a young marketplace that is a number
to keep; and once it is out, it is out of every screenshot anybody ever took.
Eight digits give 10⁸ combinations — a collision is a retry on the unique index,
not a design problem.
"""

from __future__ import annotations

import secrets

PREFIX = "PF"


def new_shipment_no() -> str:
    """A fresh number. Not checked for uniqueness here — the column carries the
    unique index, and the caller retries on the conflict.

    Called by: `api.deals.match_deal`.
    """
    digits = f"{secrets.randbelow(10**8):08d}"
    return f"{PREFIX}-{digits[:3]}-{digits[3:]}"
