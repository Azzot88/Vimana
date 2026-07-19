"""T_UX.2 — public read endpoints for RouteNote + PlatformNotice.

Public (no auth): notices are informational and shown on every trip card /
footer / deal page regardless of user state. Admin CRUD (superuser) is a
pt.2 follow-up.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.permissions import Permission, require_perm
from app.models.notices import (
    NoticeSeverity,
    NoticeSurface,
    PlatformNotice,
    RouteNote,
    RouteStatus,
)
from app.models.user import User

router = APIRouter()


class RouteNoteOut(BaseModel):
    id: uuid.UUID
    origin_iso: str
    destination_iso: str
    status: str
    severity: str
    headline: str
    body: str
    active_from: datetime
    active_until: datetime | None


class PlatformNoticeOut(BaseModel):
    id: uuid.UUID
    key: str
    severity: str
    target_surface: str
    headline: str
    body: str
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
            headline=n.headline,
            body=n.body,
            active_from=n.active_from,
            active_until=n.active_until,
        )
        for n in rows_sorted
    ]


@router.get("/platform-notices", response_model=list[PlatformNoticeOut])
async def list_platform_notices(
    surface: NoticeSurface | None = Query(
        default=None,
        description="Filter by surface (footer / trip_card / deal_page / all). Omit for all.",
    ),
    db: AsyncSession = Depends(get_db),
):
    """Active platform-wide notices. `surface` filter matches either the
    specific value OR `all` (both are relevant for the caller's screen).

    Typed as `NoticeSurface` so FastAPI 422s on unknown values before we
    hand a bad string to the Postgres enum. (Found via T_TEST.4 fuzz.)"""
    now = datetime.now(tz=timezone.utc)
    stmt = select(PlatformNotice).where(
        PlatformNotice.active_from <= now,
        or_(
            PlatformNotice.active_until.is_(None),
            PlatformNotice.active_until > now,
        ),
    )
    if surface is not None:
        stmt = stmt.where(
            or_(
                PlatformNotice.target_surface == surface,
                PlatformNotice.target_surface == NoticeSurface.all,
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
            headline=n.headline,
            body=n.body,
            active_from=n.active_from,
            active_until=n.active_until,
        )
        for n in rows
    ]


# ─────────────────────────────────────────────────────────────
# T_UX.2 pt.2 — superuser CRUD (permission NOTICES_MANAGE)
# ─────────────────────────────────────────────────────────────


class RouteNoteCreate(BaseModel):
    origin_iso: str
    destination_iso: str
    status: str = "attention"
    severity: str = "info"
    headline: str
    body: str = ""
    active_until: datetime | None = None


class RouteNoteUpdate(BaseModel):
    origin_iso: str | None = None
    destination_iso: str | None = None
    status: str | None = None
    severity: str | None = None
    headline: str | None = None
    body: str | None = None
    active_until: datetime | None = None


@router.post("/admin/route-notes", response_model=RouteNoteOut, status_code=201)
async def create_route_note(
    body: RouteNoteCreate,
    current_user: User = Depends(require_perm(Permission.NOTICES_MANAGE)),
    db: AsyncSession = Depends(get_db),
):
    try:
        status_enum = RouteStatus(body.status)
        severity_enum = NoticeSeverity(body.severity)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    note = RouteNote(
        origin_iso=body.origin_iso,
        destination_iso=body.destination_iso,
        status=status_enum,
        severity=severity_enum,
        headline=body.headline,
        body=body.body,
        active_until=body.active_until,
        created_by=current_user.id,
    )
    db.add(note)
    await db.commit()
    await db.refresh(note)
    return RouteNoteOut(
        id=note.id,
        origin_iso=note.origin_iso,
        destination_iso=note.destination_iso,
        status=note.status.value,
        severity=note.severity.value,
        headline=note.headline,
        body=note.body,
        active_from=note.active_from,
        active_until=note.active_until,
    )


@router.patch("/admin/route-notes/{note_id}", response_model=RouteNoteOut)
async def update_route_note(
    note_id: uuid.UUID,
    body: RouteNoteUpdate,
    _: User = Depends(require_perm(Permission.NOTICES_MANAGE)),
    db: AsyncSession = Depends(get_db),
):
    note = await db.get(RouteNote, note_id)
    if note is None:
        raise HTTPException(status_code=404, detail="RouteNote not found")
    if body.origin_iso is not None:
        note.origin_iso = body.origin_iso
    if body.destination_iso is not None:
        note.destination_iso = body.destination_iso
    if body.status is not None:
        try:
            note.status = RouteStatus(body.status)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc))
    if body.severity is not None:
        try:
            note.severity = NoticeSeverity(body.severity)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc))
    if body.headline is not None:
        note.headline = body.headline
    if body.body is not None:
        note.body = body.body
    if body.active_until is not None:
        note.active_until = body.active_until
    await db.commit()
    await db.refresh(note)
    return RouteNoteOut(
        id=note.id,
        origin_iso=note.origin_iso,
        destination_iso=note.destination_iso,
        status=note.status.value,
        severity=note.severity.value,
        headline=note.headline,
        body=note.body,
        active_from=note.active_from,
        active_until=note.active_until,
    )


@router.delete("/admin/route-notes/{note_id}", status_code=204)
async def delete_route_note(
    note_id: uuid.UUID,
    _: User = Depends(require_perm(Permission.NOTICES_MANAGE)),
    db: AsyncSession = Depends(get_db),
):
    note = await db.get(RouteNote, note_id)
    if note is None:
        raise HTTPException(status_code=404, detail="RouteNote not found")
    from sqlalchemy import delete as sql_delete
    await db.execute(sql_delete(RouteNote).where(RouteNote.id == note_id))
    await db.commit()
    return


class PlatformNoticeCreate(BaseModel):
    key: str
    severity: str = "info"
    target_surface: str = "all"
    headline: str
    body: str = ""
    active_until: datetime | None = None


@router.post("/admin/platform-notices", response_model=PlatformNoticeOut, status_code=201)
async def create_platform_notice(
    body: PlatformNoticeCreate,
    current_user: User = Depends(require_perm(Permission.NOTICES_MANAGE)),
    db: AsyncSession = Depends(get_db),
):
    try:
        severity_enum = NoticeSeverity(body.severity)
        surface_enum = NoticeSurface(body.target_surface)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    # Enforce UNIQUE(key) at app level with a friendlier error.
    existing = (
        await db.execute(select(PlatformNotice).where(PlatformNotice.key == body.key))
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(status_code=409, detail=f"key '{body.key}' already exists")
    notice = PlatformNotice(
        key=body.key,
        severity=severity_enum,
        target_surface=surface_enum,
        headline=body.headline,
        body=body.body,
        active_until=body.active_until,
        created_by=current_user.id,
    )
    db.add(notice)
    await db.commit()
    await db.refresh(notice)
    return PlatformNoticeOut(
        id=notice.id,
        key=notice.key,
        severity=notice.severity.value,
        target_surface=notice.target_surface.value,
        headline=notice.headline,
        body=notice.body,
        active_from=notice.active_from,
        active_until=notice.active_until,
    )


@router.delete("/admin/platform-notices/{notice_id}", status_code=204)
async def delete_platform_notice(
    notice_id: uuid.UUID,
    _: User = Depends(require_perm(Permission.NOTICES_MANAGE)),
    db: AsyncSession = Depends(get_db),
):
    notice = await db.get(PlatformNotice, notice_id)
    if notice is None:
        raise HTTPException(status_code=404, detail="PlatformNotice not found")
    from sqlalchemy import delete as sql_delete
    await db.execute(sql_delete(PlatformNotice).where(PlatformNotice.id == notice_id))
    await db.commit()
    return
