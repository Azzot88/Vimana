"""T_UX.31 — who is waiting for a trip on this corridor, asked in one place.

The letter (`tasks.notifications.notify_corridor_subscribers`, sync, after the
commit) and the bell (`api.trips.create_trip`, async, inside the transaction)
ask the same question from two kinds of session. A SQLAlchemy `select` belongs
to neither, so the question is written once here and both execute it — two
copies of a matching rule are two rules, and `T_DATA.2` is about to change it.

Functions (PROJECT §6.2a):
- `waiting_requests(trip)` — open requests whose corridor and window this trip
  answers. Called by: `api.trips.create_trip`,
  `tasks.notifications.notify_corridor_subscribers`.
"""
from __future__ import annotations

from sqlalchemy import Select, select

from app.models.marketplace import SenderRequest, Trip


def waiting_requests(trip: Trip) -> Select:
    """Open requests on the trip's corridor whose window holds its departure.

    Matched on the corridor **and the window**: a trip leaving after somebody's
    last useful day is not their trip (T3.11.19). The corridor is still the
    first and last airport code; city and segment matching is `T_DATA.2`.
    """
    departs = trip.depart_at.date()
    return select(SenderRequest).where(
        SenderRequest.origin == trip.origin,
        SenderRequest.destination == trip.destination,
        SenderRequest.is_open.is_(True),
        SenderRequest.window_from <= departs,
        SenderRequest.window_to >= departs,
    )
