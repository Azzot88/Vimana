"""T3.35 — normalising a proposal to a comparable shape.

Two people can propose the same delivery in incomparable ways: one quotes a flat
$120, another $30 per kilo, a third names a figure for a box whose weight nobody
stated. The normalised view answers the question a sender actually has — *is
this a good price for this route* — by reducing every proposal to the same four
numbers: corridor, distance, chargeable weight, and price per kilo and per
kilometre.

It is computed on the server and stored in the agreed card, not recomputed for
display. A number that moves after both sides agreed is not a term.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.airports import corridor_of, route_distance_km
from app.core.params import resolve


@dataclass(frozen=True)
class NormalizedTerms:
    direction: str | None            # corridor, e.g. "AE->US"
    route: str                       # the IATA pair as published
    distance_km: float | None        # straight line — see airports.route_distance_km
    weight_kg: float
    chargeable_weight_kg: float
    price_total: float
    currency: str
    price_per_kg: float | None
    price_per_km: float | None

    def as_dict(self) -> dict:
        return asdict(self)


def volumetric_weight_kg(dimensions_cm: list | None, divisor: int) -> float | None:
    """L×W×H / divisor, the airline convention. `None` when unmeasured — which
    is different from zero and must not be allowed to win a max()."""
    if not dimensions_cm or len(dimensions_cm) != 3:
        return None
    try:
        length, width, height = (float(x) for x in dimensions_cm)
    except (TypeError, ValueError):
        return None
    if min(length, width, height) <= 0:
        return None
    return (length * width * height) / float(divisor)


async def normalize(
    db: AsyncSession,
    *,
    origin: str,
    destination: str,
    weight_kg: float,
    price_total: float,
    currency: str,
    dimensions_cm: list | None = None,
) -> NormalizedTerms:
    corridor = corridor_of(origin, destination)
    divisor = int(await resolve(db, "volumetric_divisor", scope=corridor))

    volumetric = volumetric_weight_kg(dimensions_cm, divisor)
    chargeable = max(weight_kg, volumetric) if volumetric is not None else weight_kg

    distance = route_distance_km(origin, destination)

    # Guarded rather than assumed: a zero weight or an unknown airport pair is a
    # legitimate proposal, and a ZeroDivisionError in the middle of agreeing
    # terms would be a spectacular way to lose a deal.
    per_kg = round(price_total / chargeable, 2) if chargeable > 0 else None
    per_km = (
        round(price_total / distance, 4) if distance and distance > 0 else None
    )

    return NormalizedTerms(
        direction=corridor,
        route=f"{(origin or '').upper()}->{(destination or '').upper()}",
        distance_km=round(distance, 1) if distance is not None else None,
        weight_kg=weight_kg,
        chargeable_weight_kg=round(chargeable, 3),
        price_total=price_total,
        currency=currency,
        price_per_kg=per_kg,
        price_per_km=per_km,
    )


def below_carrier_minimum(trip, price_total: float) -> bool:
    """A proposal under the carrier's published floor. Not an error — the
    carrier may still accept it — but the card says so, so nobody agrees to a
    number they had already ruled out."""
    if trip.min_deal_price is None:
        return False
    return Decimal(str(price_total)) < Decimal(str(trip.min_deal_price))
