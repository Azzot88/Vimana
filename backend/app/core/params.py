"""T3.40 — resolving a business parameter to the value in force.

The registry below is the source of truth for *which* parameters exist and what
they fall back to. The table holds overrides; an empty table means the platform
runs on these defaults rather than on nothing. That way a fresh database is a
working database, and a deleted row is a return to a known number instead of a
crash.

Defaults trace to MASTERPLAN §4.1. Where a number there is marked as proposed
rather than approved, it is marked here too — so the screen can show which rates
are decisions and which are placeholders.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.platform_params import GLOBAL_SCOPE, ParamValueType, PlatformParameter


@dataclass(frozen=True)
class ParamSpec:
    key: str
    default: str
    value_type: ParamValueType
    group: str
    approved: bool
    note: str


# Ordered by group so the admin screen can render sections without its own list.
REGISTRY: tuple[ParamSpec, ...] = (
    ParamSpec(
        "carrier_fee_percent", "3", ParamValueType.percent, "fees", True,
        "Сбор с перевозчика от стоимости услуги, списывается с залога.",
    ),
    ParamSpec(
        "escrow_tier1_percent", "5", ParamValueType.percent, "fees", True,
        "Предельная шкала эскроу: часть декларации до порога 1.",
    ),
    ParamSpec(
        "escrow_tier2_percent", "3", ParamValueType.percent, "fees", True,
        "Часть декларации между порогами 1 и 2.",
    ),
    ParamSpec(
        "escrow_tier3_percent", "2", ParamValueType.percent, "fees", True,
        "Часть декларации свыше порога 2.",
    ),
    ParamSpec(
        "escrow_tier1_threshold", "2000", ParamValueType.integer, "fees", True,
        "Верх первой ступени шкалы, USD.",
    ),
    ParamSpec(
        "escrow_tier2_threshold", "10000", ParamValueType.integer, "fees", True,
        "Верх второй ступени шкалы, USD.",
    ),
    ParamSpec(
        "escrow_min_declared_value", "400", ParamValueType.integer, "fees", True,
        "Нижний порог эскроу, USD. Документы идут по нему независимо от стоимости.",
    ),
    ParamSpec(
        "b2b_platform_share_percent", "18.9", ParamValueType.decimal, "fees", True,
        "Доля платформы в потоке C от оплачиваемого веса.",
    ),
    ParamSpec(
        "b2b_price_per_kg", "25", ParamValueType.decimal, "fees", True,
        "Ориентир цены за килограмм в потоке C, USD.",
    ),
    ParamSpec(
        "volumetric_divisor", "5000", ParamValueType.integer, "fees", False,
        "Делитель объёмного веса. 5000 — стандарт IATA; для ручной клади может быть строже.",
    ),
    ParamSpec(
        "exposure_multiplier_auto", "1", ParamValueType.decimal, "bond", False,
        "Множитель допустимой экспозиции при верификации auto.",
    ),
    ParamSpec(
        "exposure_multiplier_peer", "2", ParamValueType.decimal, "bond", False,
        "Множитель при верификации peer.",
    ),
    ParamSpec(
        "exposure_multiplier_kyc", "4", ParamValueType.decimal, "bond", False,
        "Множитель при regulatory KYC.",
    ),
    ParamSpec(
        "min_bond_tier1", "0", ParamValueType.integer, "bond", False,
        "Минимальный залог уровня 1, USD. Задаётся по коридорам — глобальное значение только запасное.",
    ),
    ParamSpec(
        "shop_pool_min_bond", "0", ParamValueType.integer, "bond", False,
        "Типовой порог залога для пула магазина, USD.",
    ),
    ParamSpec(
        "premium_price_month", "0", ParamValueType.decimal, "premium", False,
        "Цена премиум-подписки в месяц, USD.",
    ),
)

REGISTRY_BY_KEY: dict[str, ParamSpec] = {spec.key: spec for spec in REGISTRY}


def corridor_scope(origin_iso: str, destination_iso: str) -> str:
    """Canonical corridor scope string. Kept in one place so the screen, the
    resolver and any future importer cannot disagree on the separator."""
    return f"{origin_iso.upper()}->{destination_iso.upper()}"


def parse_value(raw: str, value_type: ParamValueType) -> Decimal | int | str:
    if value_type is ParamValueType.string:
        return raw
    try:
        if value_type is ParamValueType.integer:
            return int(Decimal(raw))
        return Decimal(raw)
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"value {raw!r} is not a valid {value_type.value}") from exc


async def resolve(
    db: AsyncSession,
    key: str,
    *,
    scope: str | None = None,
    at: datetime | None = None,
) -> Decimal | int | str:
    """Value in force for `key`, corridor-first then global, then the default.

    `at` exists so a deal can ask what the number was when it was fixed rather
    than what it is now — MASTERPLAN §4.1 forbids a rate change from reaching
    backwards into an agreed shipment.
    """
    spec = REGISTRY_BY_KEY.get(key)
    if spec is None:
        raise KeyError(f"unknown platform parameter {key!r}")

    moment = at or datetime.now(timezone.utc)
    scopes = [scope, GLOBAL_SCOPE] if scope and scope != GLOBAL_SCOPE else [GLOBAL_SCOPE]

    for candidate in scopes:
        stmt = (
            select(PlatformParameter)
            .where(
                PlatformParameter.key == key,
                PlatformParameter.scope == candidate,
                PlatformParameter.effective_from <= moment,
            )
            .order_by(PlatformParameter.effective_from.desc())
            .limit(1)
        )
        row = (await db.execute(stmt)).scalar_one_or_none()
        if row is not None:
            return parse_value(row.value, row.value_type)

    return parse_value(spec.default, spec.value_type)


async def resolve_all(
    db: AsyncSession,
    *,
    scope: str | None = None,
    at: datetime | None = None,
) -> dict[str, Decimal | int | str]:
    """Every parameter at once — what a deal stores at handoff so its terms stay
    readable years later without re-resolving anything."""
    return {
        spec.key: await resolve(db, spec.key, scope=scope, at=at) for spec in REGISTRY
    }
