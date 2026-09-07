import uuid
from datetime import datetime
from typing import Literal

from pydantic import (
    AliasChoices,
    BaseModel,
    ConfigDict,
    Field,
    computed_field,
    field_validator,
    model_validator,
)

from app.core.currencies import CURRENCIES
from app.core.trip_legs import MAX_LEGS
from app.models.marketplace import EXCLUSIONS, TRIP_SERVICES
# T3.11.22 — imported, not re-typed. This list used to be written out here as
# well as in `schemas/cards.py`: two literal copies obliged to agree forever and
# connected by nothing. The old comment justified the copy by avoiding a
# marketplace→cards dependency — a dependency that costs nothing (nothing in
# `cards` imports this module) and whose absence bought a second vocabulary that
# would have drifted silently, surfacing on the deal card as a method the trip
# offered and the card could not name.
from app.schemas.cards import HANDOVER_METHODS


def _closed_list(
    value: list[str] | None, vocabulary: tuple[str, ...], what: str
) -> list[str] | None:
    """T3.11.07 — validate one of the trip's closed-vocabulary lists.

    Deduplicates rather than refuses a repeat: a repeated value is a client bug,
    not a carrier saying something twice, and stored it would draw the same chip
    twice on the card. `None` passes through untouched — "said nothing" is a
    real answer and a different one from an empty list.

    Called by: `TripCreate._known_exclusions`, `TripCreate._known_services`.
    """
    if value is None:
        return None
    unknown = set(value) - set(vocabulary)
    if unknown:
        raise ValueError(f"unknown {what}: {sorted(unknown)}")
    return list(dict.fromkeys(value))


class TripLegIn(BaseModel):
    """T3.11.15 — one flight of the chain. `leg_order` is assigned on write, not
    submitted: see `core.trip_legs.normalise_legs`."""

    origin: str = Field(min_length=1, max_length=100)
    destination: str = Field(min_length=1, max_length=100)
    depart_at: datetime
    # T3.11.07 — optional, and the form asks it only for the end of the route.
    # A landing time the carrier does not know is not one they should be made to
    # invent, and `None` says so.
    arrive_at: datetime | None = None
    # Declared, never inferred. "Flying in person" is the most valuable claim on
    # this market and the one nothing checks today.
    flown_by: Literal["self", "proxy"] = "self"


class TripLegOut(BaseModel):
    # The column is `leg_order` (`order` is reserved in SQL) but the wire word is
    # `order`: the client has no reason to inherit a database workaround.
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    order: int = Field(validation_alias=AliasChoices("leg_order", "order"))
    origin: str
    destination: str
    depart_at: datetime
    # T3.11.07 — when the carrier lands (owner's decision 2026-09-06). Asked for
    # the **end of the route**, which is the leg that has one; `None` everywhere
    # else, and `None` on older trips, which is a real answer rather than a gap.
    arrive_at: datetime | None = None
    flown_by: str

    # T3.11.07 — the city behind each code, so a collapsed trip reads
    # «New York, JFK» rather than `JFK`. Computed rather than stored: the trip
    # holds the code the carrier stated, and a city copied into the row would be
    # a second version of it that never gets corrected. `None` for a code we do
    # not know — the client then prints the code alone, which is what it did
    # before and is never wrong.
    @computed_field  # type: ignore[prop-decorator]
    @property
    def origin_city(self) -> str | None:
        from app.core.airports import city_of

        return city_of(self.origin)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def destination_city(self) -> str | None:
        from app.core.airports import city_of

        return city_of(self.destination)


class HandoverSide(BaseModel):
    """T3.11.15 — how the carrier takes cargo at one end of the route.

    `points` is free text on purpose: the market names districts, suburbs and
    satellite cities ("Tustin, Irvine or LAX", "Fili, Moscow"), and a picker
    over airports cannot say any of that. Bounded rather than validated — a
    taxonomy of neighbourhoods is not something this task can be right about.

    T3.11.07 — the three references. An address and a meeting place are **ids**
    into the carrier's own lists rather than copies of their text: a person who
    corrects a typo in their address should not have to republish every trip
    that mentions it. Checked for ownership in `api.trips`, not here — a schema
    cannot know whose row it is.

    `postal_services` is the third level of the chain (service → method →
    which service), and it is **free strings, not codes**: the catalogue behind
    it has no external source, covers ~55 countries, and must not be able to
    tell a carrier that the one company collecting parcels in their town does
    not exist.
    """

    methods: list[str] = Field(default_factory=list, max_length=len(HANDOVER_METHODS))
    points: list[str] = Field(default_factory=list, max_length=6)
    address_id: uuid.UUID | None = None
    meeting_place_id: uuid.UUID | None = None
    postal_services: list[str] = Field(default_factory=list, max_length=8)

    @field_validator("methods")
    @classmethod
    def _known_methods(cls, v: list[str]) -> list[str]:
        unknown = set(v) - HANDOVER_METHODS
        if unknown:
            raise ValueError(f"unknown handover methods: {sorted(unknown)}")
        return v

    @field_validator("points", "postal_services")
    @classmethod
    def _trim_free_text(cls, v: list[str]) -> list[str]:
        cleaned = [p.strip() for p in v if p and p.strip()]
        for item in cleaned:
            if len(item) > 120:
                raise ValueError("at most 120 characters")
        return list(dict.fromkeys(cleaned))

    @model_validator(mode="after")
    def _services_need_the_method(self) -> "HandoverSide":
        """T3.11.22 — the third level cannot be answered before the second.

        Naming postal companies while not handing over by post is the
        contradiction this task exists to remove: three independent answers, no
        one of them authoritative, and the deal card left to guess. Making the
        levels **depend** on each other is what makes the contradiction
        impossible — you cannot say «only CDEK is near me» without having said
        you post it at all.

        The coarse level above (`services.domestic_shipping`) is not asked for
        twice: `api.trips._services_with_derived` computes it from the same
        method. Derived where derivable, refused where it would be a guess —
        nobody can work out from a list of couriers whether the carrier meant to
        post anything.
        """
        if self.postal_services and "local_post" not in self.methods:
            raise ValueError(
                "postal_services without the local_post handover method"
            )
        return self


class TripCreate(BaseModel):
    # T3.11.15 — the route arrives as a chain and only as a chain. The flat
    # `origin`/`destination`/`depart_at` trio is gone from the wire: keeping it
    # alongside `legs` would mean two ways to say the same thing and a rule
    # about which one wins. The columns of those names survive on the model as
    # the denormalised head of the chain — see `core.trip_legs.head_and_tail`.
    legs: list[TripLegIn] = Field(min_length=1, max_length=MAX_LEGS)
    # T3.11.07 — optional since the express path. The route is the only thing a
    # carrier must state to be findable; everything else is a detail they can
    # add later, and 31 % of this market publishes inside two days of the
    # flight. Weight in kilograms is stated in 2.4 % of real posts.
    capacity: float | None = Field(default=None, gt=0, le=100)
    allowed_categories: list[str] | None = None
    # T3.35 — the carrier's baseline terms. Optional on purpose: a trip without
    # a stated price is a legitimate listing ("price on request"), and forcing a
    # number would make carriers invent one to get past the form.
    price_per_kg: float | None = Field(default=None, gt=0, le=10_000)
    min_deal_price: float | None = Field(default=None, ge=0, le=1_000_000)
    # T3.11.07 — three or four characters, and one of ours. It was `max_length=3`,
    # which refused `USDT` and `USDC` outright the moment an account could hold
    # them — the form offers the carrier's own list, so the one value it sends
    # would have been rejected by the field it came from. Checked against the
    # closed list for the same reason the account field is: a typo in a currency
    # code is a price nobody can compare.
    currency: str = Field(default="USD", min_length=3, max_length=4)
    max_declared_value: float | None = Field(default=None, ge=0)
    # T3.11.07 — the allowance is denominated by the country the parcel lands in
    # ($2 000 into the US), which is routinely not the currency the carrier
    # quotes prices in. `None` means "same as the trip", the common case.
    max_declared_value_currency: str | None = Field(
        default=None, min_length=3, max_length=4
    )
    # T3.11.07 — a closed list, so a sender can filter on it. `None` means the
    # carrier said nothing, which is what 94 % of this market does; an empty
    # list would claim they considered the question and had no exclusions.
    excluded: list[str] | None = Field(default=None, max_length=len(EXCLUSIONS))
    # T3.11.07 — what the carrier does around the flight, and how they expect to
    # be paid. Both nullable: the settlement model is stated by 61.7 % of this
    # market and a price by 0.1 %, so the model is the field that matters — but
    # silence still has to stay distinguishable from the commonest answer.
    services: list[str] | None = Field(default=None, max_length=len(TRIP_SERVICES))
    payment_model: Literal["on_platform", "off_platform"] | None = None
    # Free text turned into chips by the form, not a closed list: what people
    # transfer through is local and changes faster than a vocabulary we could
    # ship, and a carrier naming one we had not heard of would be told they are
    # wrong.
    payment_systems: list[str] | None = Field(default=None, max_length=8)
    # T_UX.15 — omitted means "use my standing rules"; an explicit empty string
    # means "this trip has none", and the two must stay distinguishable.
    carriage_rules: str | None = Field(default=None, max_length=4000)
    space_kind: Literal[
        "cabin", "checked_partial", "checked_full", "unspecified"
    ] = "unspecified"
    size_hint: Literal["small", "medium", "large"] | None = None
    # T3.11.15 — asymmetric by design. These replace the single
    # `allowed_handover_methods` list: once both ends are stated separately, one
    # combined list is a second way to say the same thing.
    handover_origin: HandoverSide | None = None
    handover_destination: HandoverSide | None = None

    @field_validator("max_declared_value_currency")
    @classmethod
    def _known_allowance_currency(cls, v: str | None) -> str | None:
        """Same closed list as `currency`, and `None` stays `None`.

        Nullable rather than defaulted: "the trip's currency" is a different
        answer from "USD", and writing the second would put a currency on every
        trip whose carrier never chose one.
        """
        if v is None:
            return None
        code = v.strip().upper()
        if not code:
            return None
        if code not in CURRENCIES:
            raise ValueError(f"unknown currency: {code}")
        return code

    @field_validator("currency")
    @classmethod
    def _known_currency(cls, v: str) -> str:
        """Upper-cased and checked against the closed list.

        The form offers the carrier's own currencies, so a value arriving here
        that is not on the list did not come from the form.
        """
        code = v.strip().upper()
        if code not in CURRENCIES:
            raise ValueError(f"unknown currency: {code}")
        return code

    @field_validator("excluded")
    @classmethod
    def _known_exclusions(cls, v: list[str] | None) -> list[str] | None:
        return _closed_list(v, EXCLUSIONS, "exclusions")

    @field_validator("services")
    @classmethod
    def _known_services(cls, v: list[str] | None) -> list[str] | None:
        return _closed_list(v, TRIP_SERVICES, "services")

    @field_validator("payment_systems")
    @classmethod
    def _clean_systems(cls, v: list[str] | None) -> list[str] | None:
        """Trimmed, deduplicated, bounded — but not checked against a list.

        The form turns typed text into chips, so what arrives is whatever the
        carrier called it. Blanks are dropped rather than rejected: a trailing
        comma is a typo, not an answer, and refusing the whole trip over one is
        the wrong trade.
        """
        if v is None:
            return None
        cleaned = [s.strip() for s in v if s and s.strip()]
        for system in cleaned:
            if len(system) > 40:
                raise ValueError("a payment system name is at most 40 characters")
        return list(dict.fromkeys(cleaned)) or None


class TripOut(BaseModel):
    id: uuid.UUID
    carrier_id: uuid.UUID
    carrier_name: str | None = None
    # T3.1/T3.2 — UBA is a first-class trust signal on trip cards.
    carrier_uba: int | None = None
    carrier_uba_level: str | None = None
    # T3.17 — a retired identity, visible before anyone offers it a deal. The
    # account can still be signed into but can no longer act, and finding that
    # out after choosing a carrier is finding it out too late.
    carrier_key_lost: bool = False
    origin: str
    destination: str
    depart_at: datetime
    capacity: float | None = None
    allowed_categories: list[str] | None
    # T3.35 — shown on the trip card so two trips on one corridor are
    # comparable before anyone opens a chat.
    price_per_kg: float | None = None
    min_deal_price: float | None = None
    currency: str = "USD"
    # T3.11.07 — the customs allowance the carrier has left, not a ceiling, and
    # the currency it is counted in. `None` on the currency means the trip's own.
    max_declared_value: float | None = None
    max_declared_value_currency: str | None = None
    space_kind: str = "unspecified"
    size_hint: str | None = None
    handover_origin: dict | None = None
    handover_destination: dict | None = None
    legs: list[TripLegOut] = Field(default_factory=list)
    excluded: list[str] | None = None
    services: list[str] | None = None
    payment_model: str | None = None
    payment_systems: list[str] | None = None
    carriage_rules: str | None = None
    status: str
    # T3.11.16 — how fresh the listing is, and when it stops being one. Both are
    # on the card because both change what the reader should do with it: a trip
    # raised an hour ago is being actively offered, and one whose last flight
    # leaves tonight is not worth writing to about a parcel next week.
    listed_at: datetime | None = None
    expires_at: datetime | None = None
    created_at: datetime
    # T3.5 — Nostr publish state (surfaced to clients for the "📡 Also on Nostr" chip).
    nostr_event_id: str | None = None
    nostr_published_at: datetime | None = None
    model_config = ConfigDict(from_attributes=True)


class OrderCreate(BaseModel):
    recipient_contact: str
    origin: str
    destination: str
    category: str
    declared_value: float
    currency: str = "USD"
    description: str | None = None
    deadline: datetime | None = None


class DealOut(BaseModel):
    id: uuid.UUID
    order_id: uuid.UUID
    trip_id: uuid.UUID
    sender_id: uuid.UUID
    carrier_id: uuid.UUID
    recipient_id: uuid.UUID | None
    status: str
    created_at: datetime
    # T3.11.26 — enough to tell one deal from another in a list, and to group the
    # list by the person it is with. Ids cannot do either: «55468906…» beside
    # «7c3a91b2…» is two rows nobody can choose between, which is why the deals
    # page could not be built on what this schema returned.
    #
    # Filled by `list_deals` from two batched lookups rather than left to the
    # client: a page of twenty deals would otherwise be forty requests for names
    # the server already has open in front of it.
    sender_name: str | None = None
    carrier_name: str | None = None
    origin: str | None = None
    destination: str | None = None
    # T3.11.23 — what makes a row in the chat a *deal card* instead of a link.
    # The number is what people say out loud; the category and the route are the
    # name («Документы · DXB → JFK»), derived rather than asked for, because a
    # name field would come back empty on a market that fills nothing in; the
    # price is the agreed one, and it is missing exactly while nothing has been
    # agreed — a deal being negotiated has no price, and printing zero would be
    # a claim nobody made.
    shipment_no: str | None = None
    chat_id: uuid.UUID | None = None
    cargo_category: str | None = None
    price_total: float | None = None
    currency: str | None = None
    model_config = ConfigDict(from_attributes=True)


class DealDetailOut(BaseModel):
    id: uuid.UUID
    order_id: uuid.UUID
    trip_id: uuid.UUID
    sender_id: uuid.UUID
    carrier_id: uuid.UUID
    recipient_id: uuid.UUID | None
    status: str
    created_at: datetime
    origin: str
    destination: str
    depart_at: datetime
    sender_name: str
    carrier_name: str
    # T2.3 — needed by client to encrypt vault messages under both parties' npubs.
    sender_npub: str | None = None
    carrier_npub: str | None = None
    cargo_description: str
    cargo_category: str
    declared_value: float
    currency: str
    # T_UX.15 — the rules the sender agreed to when they chose this trip. Read
    # from the trip's own copy, not the carrier's current template: a rule
    # edited after the match is not the rule this deal was struck under.
    carriage_rules: str | None = None
    # T3.11.23 — the number people say out loud. It belongs on the detail as
    # well as in the list: the boarding pass is where someone looks it up to
    # dictate it, and the UUID beside it is for support, not for speech.
    shipment_no: str | None = None
    model_config = ConfigDict(from_attributes=True)


class DealEventOut(BaseModel):
    id: uuid.UUID
    deal_id: uuid.UUID
    event_type: str
    payload: dict | None
    actor_id: uuid.UUID
    timestamp: datetime
    model_config = ConfigDict(from_attributes=True)
