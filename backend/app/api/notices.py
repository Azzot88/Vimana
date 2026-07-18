"""T_UX.2 — public read endpoints for RouteNote + PlatformNotice.

Public (no auth): notices are informational and shown on every trip card /
footer / deal page regardless of user state. Admin CRUD (superuser) is a
pt.2 follow-up.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.notices import (
    NoticeSeverity,
    NoticeSurface,
    PlatformNotice,
    RouteNote,
    RouteStatus,
)

router = APIRouter()


class RouteNoteOut(BaseModel):
    id: uuid.UUID
    origin_iso: str
    destination_iso: str
    status: str
    severity: str
    headline_i18n_key: str
    body_i18n_key: str
    active_from: datetime
    active_until: datetime | None


class PlatformNoticeOut(BaseModel):
    id: uuid.UUID
    key: str
    severity: str
    target_surface: str
    active_from: datetime
    active_until: datetime | None


def _is_active_now():
    """SQL fragment: active_from ≤ now AND (active_until IS NULL OR active_until > now)."""
    now = datetime.now(tz=timezone.utc)
    return lambda col_from, col_until: (col_from <= now) & (
        (col_until.is_(None)) | (col_until > now)
    )


@router.get("/route-notes", response_model=list[RouteNoteOut])
async def list_route_notes(
    origin: str | None = Query(default=None, description="ISO-3166 code (or omit for any)"),
    destination: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
):
    """Active notes matching (origin, destination). Wildcards `*` supported —
    a note with `origin='*'` matches ANY origin filter, and vice versa. If
    filters are omitted, returns all active notes."""
    now = datetime.now(tz=timezone.utc)
    stmt = select(RouteNote).where(
        RouteNote.active_from <= now,
        or_(RouteNote.active_until.is_(None), RouteNote.active_until > now),
    )
    if origin:
        stmt = stmt.where(or_(RouteNote.origin_iso == origin, RouteNote.origin_iso == "*"))
    if destination:
        stmt = stmt.where(
            or_(RouteNote.destination_iso == destination, RouteNote.destination_iso == "*")
        )
    # Sort by specificity: exact matches before wildcards, then by severity
    # (alert > warning > info). Done in Python — simple + correct.
    rows = (await db.execute(stmt)).scalars().all()
    severity_rank = {"alert": 0, "warning": 1, "info": 2}

    def _rank(n: RouteNote) -> tuple[int, int]:
        spec = (0 if n.origin_iso != "*" else 1) + (0 if n.destination_iso != "*" else 1)
        sev = severity_rank.get(n.severity.value if hasattr(n.severity, "value") else str(n.severity), 3)
        return (spec, sev)

    rows_sorted = sorted(rows, key=_rank)
    return [
        RouteNoteOut(
            id=n.id,
            origin_iso=n.origin_iso,
            destination_iso=n.destination_iso,
            status=n.status.value if hasattr(n.status, "value") else str(n.status),
            severity=n.severity.value if hasattr(n.severity, "value") else str(n.severity),
            headline_i18n_key=n.headline_i18n_key,
            body_i18n_key=n.body_i18n_key,
            active_from=n.active_from,
            active_until=n.active_until,
        )
        for n in rows_sorted
    ]


@router.get("/platform-notices", response_model=list[PlatformNoticeOut])
async def list_platform_notices(
    surface: str | None = Query(
        default=None,
        description="Filter by surface (footer / trip_card / deal_page). Omit for all.",
    ),
    db: AsyncSession = Depends(get_db),
):
    """Active platform-wide notices. `surface` filter matches either the
    specific value OR `all` (both are relevant for the caller's screen)."""
    now = datetime.now(tz=timezone.utc)
    stmt = select(PlatformNotice).where(
        PlatformNotice.active_from <= now,
        or_(
            PlatformNotice.active_until.is_(None),
            PlatformNotice.active_until > now,
        ),
    )
    if surface:
        stmt = stmt.where(
            or_(
                PlatformNotice.target_surface == surface,
                PlatformNotice.target_surface == "all",
            )
        )
    rows = (await db.execute(stmt)).scalars().all()
    return [
        PlatformNoticeOut(
            id=n.id,
            key=n.key,
            severity=n.severity.value if hasattr(n.severity, "value") else str(n.severity),
            target_surface=n.target_surface.value
            if hasattr(n.target_surface, "value")
            else str(n.target_surface),
            active_from=n.active_from,
            active_until=n.active_until,
        )
        for n in rows
    ]
