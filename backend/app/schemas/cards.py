"""T3.36–T3.39 — payload shapes, one per card kind.

Every model here holds only what the server must be able to read: enumerations,
amounts, dates. Free text and addresses travel in the message's encrypted `text`
column (§6.9.3), which is why none of these models has a `description` field
even where the card obviously has something to say.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal, get_args

from pydantic import BaseModel, Field, model_validator

from app.core.cards import CardKind

#: T3.11.22 — **the** list of handover methods, declared once.
#:
#: It lived here and, word for word, in `schemas/marketplace.py`: two literal
#: lists obliged to agree forever and connected by nothing. They would have
#: diverged in silence, and the place it became visible is the worst one — a
#: deal card unable to name the method the trip was published with, which is
#: exactly the moment the parcel changes hands.
#:
#: This file owns it because the deal card is where the method is *executed*;
#: the trip merely offers it. `schemas/marketplace` imports the tuple below
#: rather than re-typing the words. The earlier comment there said the
#: duplication avoided a marketplace→cards dependency — that dependency does not
#: exist (nothing in `cards` imports `marketplace`), and avoiding it bought a
#: second copy of the vocabulary.
HandoverMethod = Literal[
    "in_person", "local_post", "courier", "parcel_locker", "poste_restante"
]

#: The same vocabulary at runtime, for validators that check membership rather
#: than annotate a field. Derived from the `Literal` so the two cannot drift:
#: adding a method means editing one line above and nothing else.
HANDOVER_METHODS: frozenset[str] = frozenset(get_args(HandoverMethod))

#: T3.11.27 — **the** settlement vocabulary, declared once, for the same reason
#: as the handover methods above.
#:
#: Owner, 2026-09-08: «Опция расчета три: наличными при получении, электронными
#: деньгами при получении, с кошелька на платформе». The trip is published with
#: exactly these words (`models.marketplace`), and until now the deal answered
#: the same question with a different set — `cash | platform | escrow` — that
#: nothing translated into them. A carrier could publish «электронными при
#: получении» and be handed an agreement saying «cash», and no screen could tell
#: that was the same answer or a different one.
#:
#: Payloads written before today keep their old words: they are history, not
#: choices, and the card renderer falls back to the raw key.
PaymentMethod = Literal[
    "cash_on_delivery", "emoney_on_delivery", "platform_wallet"
]

PAYMENT_METHODS: frozenset[str] = frozenset(get_args(PaymentMethod))


class HandoverConditions(BaseModel):
    packaging: str | None = Field(default=None, max_length=200)
    open_on_handover: bool = False
    photo_required: bool = True
    fragile: bool = False


class MeetingPoint(BaseModel):
    """Shared by pickup and dropoff — the shape of "where and when" does not
    change depending on which end of the route it describes."""

    method: HandoverMethod
    city: str | None = Field(default=None, max_length=120)
    at: datetime | None = None
    window_minutes: int | None = Field(default=None, ge=0, le=24 * 60)
    tracking_number: str | None = Field(default=None, max_length=64)
    # T3.11.22 — **which** company actually took it, beside the number they gave.
    # The trip says what the carrier can do («CDEK is the one near me»); the card
    # says what happened («posted with CDEK, here is the code»). A tracking
    # number without the company that issued it is a string nobody can follow —
    # the two belong on the same card and always did.
    #
    # Free text, like the trip's list and for the same reason: the catalogue has
    # no external source and must not be able to tell somebody the company that
    # took their parcel does not exist.
    postal_service: str | None = Field(default=None, max_length=120)

    @model_validator(mode="after")
    def _service_needs_a_carrier_of_parcels(self) -> "MeetingPoint":
        """T3.11.22 — the same narrowing as on the trip, one step further in.

        A company name on a hand-to-hand meeting is a contradiction: nothing was
        posted, so nobody carried it. Refused rather than ignored — a field
        quietly dropped is a field the sender believes they filled in.
        """
        if self.postal_service and self.method not in ("local_post", "courier"):
            raise ValueError(
                "postal_service only applies to local_post or courier"
            )
        return self


class HandoffDeclared(BaseModel):
    # Nothing required: the evidence is the photo, checked at acceptance.
    parcel_count: int = Field(default=1, ge=1, le=20)


class TransitUpdate(BaseModel):
    # T_DEAL.1 — `storage` joined the four (owner, 2026-09-20): «посылка
    # прилетела и не может быть вручена, или ожидает стыковочного рейса… это
    # просто хранение перед этапом вручения». A state of the journey, declared
    # by the carrier like every other one here, rather than a rung of the
    # ladder — it can happen before the carriage as well as before the
    # delivery, and a step that comes round twice is not a step.
    # T_UX.28 п.6 (owner, 2026-09-19): «Сначала Вылетел, затем Пересадка…
    # Пересадка тоже может быть повторена несколько раз, но строго до того как
    # прилетел. После прилёта Пересадка невозможна.»
    #
    # `layover` joins the list rather than becoming a rung of the ladder, for
    # the same reason storage did: it repeats, and an ordered ladder that can
    # come round again is not a ladder. The order and the once-only rule are
    # enforced in `api.cards._raise_card`, where the timeline can be read.
    # T_UX.29 pt.5 (owner, 2026-09-20): «Задержку и Таможню убираем, это будет
    # сказано в чате, если нужно.» Both are gone from what may be raised, and
    # deliberately not from `cards.opt.*` on the client: deals struck before
    # this round carry them, and an arbiter reading one must still find the
    # word. Validation runs on creation only, so the history is untouched.
    stage: Literal["departed", "layover", "arrived", "storage"]
    eta: datetime | None = None
    #: T_DEAL.1 — the storage place's offset from UTC, in minutes, as the
    #: carrier's own device reports it. The free period ends at a morning
    #: (`core.deal_storage`), and a morning in Dubai is not a morning in UTC; without
    #: this the boundary would land at nine or at two, depending on where the
    #: parcel happens to be lying. Defaults to UTC because an older client
    #: sends nothing, and a wrong-by-hours boundary is still better than a
    #: refused declaration about where the parcel is.
    tz_offset_minutes: int = Field(default=0, ge=-840, le=840)


class PostedDeclared(BaseModel):
    """T3.11.17 — «сдано в почту»: the onward stretch, declared by the carrier.

    Both fields are required, which is unusual here and deliberate. The tracking
    code is the **entire point** — `USERJOURNEY` Этап 4a ends the carrier's
    responsibility at it, and a declaration without one would end their
    responsibility on their word alone. The company is required with it because a
    code nobody can attribute is a string, not a way to follow a parcel.

    The photo is enforced elsewhere (`requires_attachment`), and it has to be
    taken **before sealing**: that is the one moment the contents are visible and
    already packed. A rule about the order of two actions cannot be checked by a
    schema, so it lives in the copy the carrier reads — and in the fact that the
    evidence is filed as `pre_seal_photo` rather than as a generic picture.
    """

    postal_service: str = Field(min_length=1, max_length=120)
    tracking_number: str = Field(min_length=1, max_length=64)
    # T3.12.08 — what the post office accepted (`IMPLEMENTATIONPLAN §3.12.5`
    # п. 2), so the other side can compare it with the cargo before confirming.
    # All optional (owner, 2026-09-14): not every service prints them.
    postage_cost: float | None = Field(default=None, gt=0, le=100000)
    postage_currency: str | None = Field(default=None, min_length=3, max_length=4)
    weight_kg: float | None = Field(default=None, gt=0, le=100)
    length_cm: float | None = Field(default=None, gt=0, le=1000)
    width_cm: float | None = Field(default=None, gt=0, le=1000)
    height_cm: float | None = Field(default=None, gt=0, le=1000)


class DeliveryDeclared(BaseModel):
    method: HandoverMethod = "in_person"


class PaymentMethodAgreed(BaseModel):
    # T3.11.27 — the same `PaymentMethod` the agreement itself uses. This card
    # exists to **change** what the agreement says («модель может быть изменена
    # по обоюдному согласию»), and a card whose options differ from the field it
    # edits can only produce a disagreement neither screen can render.
    method: PaymentMethod


class PaymentDeclared(BaseModel):
    amount: float = Field(gt=0)
    # T3.11.07 — four characters: `USDT` and `USDC` are four, and a payment is
    # declared in the currency the deal was agreed in.
    currency: str = Field(default="USD", min_length=3, max_length=4)
    method: PaymentMethod = "cash_on_delivery"


class ComplianceChecklist(BaseModel):
    """T3.11.09 — the corridor checklist, anchored in the deal.

    Only the case id travels. The list itself lives in `ComplianceCase.checklist`
    as a snapshot, and copying it into a card payload would make a second copy
    that can disagree with the first — the card would keep saying what the
    corridor asked in March while the case knows what it was told.

    What is closed is not stored here either: an item is closed when an
    attachment on this deal carries its `requirement_code`. Derived rather than
    written, because a card is never edited and ticks kept in a payload would
    need a new card per document.
    """

    case_id: uuid.UUID



class BuyoutRequested(BaseModel):
    """T3.11.17 part 2 — «выкупи и привези», as an object with parameters.

    A link, what exactly, what it costs, how many, and up to what total. All
    five, because the fraud in the market dump is precisely the missing fifth:
    «сначала просит зубную щётку выкупить, а потом ирригатор» — each item
    plausible, no ceiling, and the carrier discovers the total afterwards.

    `max_total` is what the carrier answers to, not `unit_price × count`: the
    price on a page moves between the request and the shop, and a ceiling that
    silently recomputed itself would not be a ceiling.
    """

    url: str = Field(max_length=500)
    what: str = Field(max_length=200)
    unit_price: float = Field(gt=0)
    count: int = Field(default=1, ge=1, le=100)
    max_total: float = Field(gt=0)
    currency: str = Field(default="USD", min_length=3, max_length=4)

    @model_validator(mode="after")
    def _ceiling_covers_the_order(self):
        """A ceiling below the order is not a ceiling, it is a typo.

        Refused rather than raised to fit: quietly widening somebody's exposure
        to make their own numbers agree is the opposite of what this field does.
        """
        if self.max_total < self.unit_price * self.count:
            raise ValueError("max_total is below unit_price × count")
        return self


class BuyoutPurchased(BaseModel):
    """What was actually bought, once the carrier's money has left.

    `total` rather than a repeat of the request: shops substitute, prices move,
    and the number that matters from here on is what was paid. The receipt is an
    attachment on this card — evidence through the normal hashed path (`T3.8`),
    not a figure typed into a chat.
    """

    total: float = Field(gt=0)
    currency: str = Field(default="USD", min_length=3, max_length=4)
    note: str | None = Field(default=None, max_length=300)


class IssueReported(BaseModel):

    category: Literal["delay", "damage", "unreachable", "mismatch"]


class DisputeRequested(BaseModel):
    """T3.12.05 — the recipient asks the sender to open a dispute. The reason is
    the dispute's own list, so the sender can open one with the same answer; the
    sentence goes in the encrypted `text`."""

    reason: Literal["unpaid", "undelivered", "damaged", "other"]


class CancelRequested(BaseModel):
    # Who eats the costs already incurred. Named at request time, because the
    # question surfaces anyway and answering it later means answering it in a
    # dispute.
    costs_borne_by: Literal["sender", "carrier", "split", "none"] = "none"
    #: T3.11.27 — when this stops waiting for an answer. Stamped by the server
    #: at request time, never sent by the client: it is the shorter of the two
    #: accounts' timeouts, capped by the flight, and a deadline a caller could
    #: choose would not be a deadline.
    expires_at: datetime | None = None


class StorageCharged(BaseModel):
    """T_DEAL.1 — what the storage actually cost, said by the carrier.

    Owner, 2026-09-20: «У перевозчика есть возможность добавить в сделку
    количество суток хранения по факту, отличающееся от счётчика. Счётчик
    уведомительный, и сумма за хранение может быть изменена.»

    So the days are typed, not taken: the computed number is a starting point
    the carrier may lower (a handover at seven in the morning by arrangement) or
    raise (a day the counter never learned about). The paying side confirms it,
    because this is money — a card the other party cannot answer would make one
    of them the author of the other's bill.

    `amount` is optional: with a tariff and a weight the two sides can both
    compute it, and a carrier who waives the charge says so by sending nought
    rather than by leaving the field out.
    """

    days: int = Field(ge=0, le=366)
    amount: float | None = Field(default=None, ge=0, le=1_000_000)
    currency: str | None = Field(default=None, min_length=3, max_length=4)


PAYLOAD_MODELS: dict[CardKind, type[BaseModel]] = {
    CardKind.handover_conditions: HandoverConditions,
    CardKind.pickup_proposed: MeetingPoint,
    CardKind.dropoff_proposed: MeetingPoint,
    CardKind.handoff_declared: HandoffDeclared,
    # T_UX.28 п.5 — `handoff.received` is history, not a form: nothing raises
    # it any more, so it has no payload to validate. Naming it here would also
    # tell `test_kinds_the_code_emits_are_marked_implemented` that the code
    # still produces it, which is exactly what stopped being true.
    CardKind.transit_update: TransitUpdate,
    CardKind.storage_charged: StorageCharged,
    CardKind.posted_declared: PostedDeclared,
    CardKind.delivery_declared: DeliveryDeclared,
    CardKind.payment_method_agreed: PaymentMethodAgreed,
    CardKind.payment_declared: PaymentDeclared,
    CardKind.buyout_requested: BuyoutRequested,
    CardKind.buyout_purchased: BuyoutPurchased,
    CardKind.compliance_checklist: ComplianceChecklist,
    CardKind.issue_reported: IssueReported,
    CardKind.dispute_requested: DisputeRequested,
    CardKind.cancel_requested: CancelRequested,
}


class CardCreate(BaseModel):
    kind: str
    payload: dict = Field(default_factory=dict)
    # Free text — encrypted at rest like any message.
    text: str | None = None
