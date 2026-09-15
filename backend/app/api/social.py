import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy import func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_user
from app.core.contacts import normalize
from app.core.database import get_db
from app.core.rate_limit import limiter
from app.core.social import (
    add_connection as add_contact,
    close_states,
    closeness,
    open_pair,
    open_pairs,
    state_of,
)
from app.core.trust import add_invited
from app.models.contact import UserContact
from app.models.social import ClosePair, Connection, InviteLink
from app.models.user import User
from app.schemas.social import ClosePairOut, ConnectionOut, InviteLinkOut, MyInviteOut

router = APIRouter()

INVITE_TTL_DAYS = 14


class InviteBody(BaseModel):
    recipient_contact: str | None = None


@router.post("/invites", response_model=InviteLinkOut, status_code=201)
async def create_invite(
    body: InviteBody = InviteBody(),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    invite = InviteLink(
        creator_id=current_user.id,
        token=secrets.token_urlsafe(32),
        expires_at=datetime.now(timezone.utc) + timedelta(days=INVITE_TTL_DAYS),
    )
    db.add(invite)
    await db.commit()
    await db.refresh(invite)
    return invite


@router.get("/invites/mine", response_model=list[MyInviteOut])
async def list_my_invites(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(InviteLink)
        .where(InviteLink.creator_id == current_user.id)
        .order_by(InviteLink.created_at.desc())
    )
    invites = result.scalars().all()

    now = datetime.now(timezone.utc)
    accepted_names: dict[uuid.UUID, str] = {}
    accepted_ids = [inv.used_by for inv in invites if inv.used_by is not None]
    if accepted_ids:
        users_result = await db.execute(select(User).where(User.id.in_(accepted_ids)))
        for u in users_result.scalars().all():
            accepted_names[u.id] = u.display_name

    out: list[MyInviteOut] = []
    for inv in invites:
        expires_at = inv.expires_at.replace(tzinfo=timezone.utc) if inv.expires_at.tzinfo is None else inv.expires_at
        if inv.used_by is not None:
            status = "accepted"
        elif expires_at < now:
            status = "expired"
        else:
            status = "pending"
        out.append(
            MyInviteOut(
                token=inv.token,
                created_at=inv.created_at,
                expires_at=inv.expires_at,
                status=status,
                accepted_by_display_name=accepted_names.get(inv.used_by) if inv.used_by else None,
            )
        )
    return out


@router.post("/invites/{token}/accept")
async def accept_invite(
    token: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    result = await db.execute(select(InviteLink).where(InviteLink.token == token))
    invite = result.scalar_one_or_none()

    if not invite:
        raise HTTPException(status_code=404, detail="Invite not found")
    if invite.expires_at.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
        raise HTTPException(status_code=410, detail="Invite expired")
    if invite.creator_id == current_user.id:
        raise HTTPException(status_code=400, detail="Cannot accept your own invite")
    # Idempotent per user — re-accept by the same user is a no-op success.
    # Guards against double-click, React StrictMode double-effect, retry.
    if invite.used_by == current_user.id:
        return {"ok": True}

    # Atomic claim: only unclaimed invite can be updated
    claim = await db.execute(
        update(InviteLink)
        .where(InviteLink.token == token, InviteLink.used_by.is_(None))
        .values(used_by=current_user.id)
    )
    if claim.rowcount == 0:
        # Race — either another user claimed between our SELECT and UPDATE,
        # or the same user claimed concurrently (double-fire). Read only the
        # winning user_id column — avoids ORM refresh + greenlet issues.
        recheck = await db.execute(
            select(InviteLink.used_by).where(InviteLink.token == token)
        )
        winner_id = recheck.scalar_one_or_none()
        if winner_id == current_user.id:
            return {"ok": True}
        raise HTTPException(status_code=409, detail="Invite already used")

    try:
        db.add(Connection(
            user_id=invite.creator_id,
            connected_user_id=current_user.id,
            invite_token=token,
        ))
        db.add(Connection(
            user_id=current_user.id,
            connected_user_id=invite.creator_id,
            invite_token=token,
        ))
        # T2.4 — Trust graph: `invited` edge (symmetric).
        await add_invited(
            db,
            inviter_id=invite.creator_id,
            invitee_id=current_user.id,
            invite_token=token,
        )
        await db.commit()
    except IntegrityError:
        await db.rollback()
    return {"ok": True}


@router.get("/me/connections", response_model=list[ConnectionOut])
async def list_connections(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    q: str | None = Query(default=None, max_length=100),
):
    """My contacts, newest rules applied: my tier, and the state of the pair.

    T3.11.24 — `q` is the search box the recipient picker needs above its list.
    It matches the display name and the public key, because those are the two
    things a person actually has to hand: a name they remember, or a key
    somebody pasted them. Matching is case-insensitive on both — a key is
    dictated in whatever case the client showed it.
    """
    stmt = (
        select(Connection)
        .where(Connection.user_id == current_user.id)
        .options(selectinload(Connection.connected_user))
    )
    needle = (q or "").strip().lower()
    if needle:
        stmt = stmt.join(User, User.id == Connection.connected_user_id).where(
            or_(
                func.lower(User.display_name).like(f"%{needle}%"),
                func.lower(User.nostr_pubkey).like(f"%{needle}%"),
            )
        )
    connections = list((await db.execute(stmt)).scalars().all())

    # T3.12.06 — closeness of every row, in one query over `close_pairs`.
    states = await close_states(
        db, current_user.id, [c.connected_user_id for c in connections]
    )

    return [
        ConnectionOut(
            id=c.id,
            connected_user_id=c.connected_user_id,
            connected_user=c.connected_user,
            created_at=c.created_at,
            state=states.get(c.connected_user_id, "connection"),
        )
        for c in connections
    ]


class ConnectionBody(BaseModel):
    user_id: uuid.UUID


@router.post("/me/connections", response_model=ConnectionOut, status_code=201)
async def add_connection(
    body: ConnectionBody,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """T3.11.24 — «добавить в контакты», one direction.

    Until now a `Connection` could only come from accepting an invite, which
    wrote both rows: the only way to have a contact was to have exchanged a
    link with them. The owner's model is looser — «Контакты могут быть и
    односторонними» — and this is the path for it: from a carrier's card, from
    the people in a deal, from search.

    Nothing is written into the other person's list. A contact list says whom
    *you* keep; writing the mirror row would let anyone put themselves into a
    stranger's contacts.
    """
    if body.user_id == current_user.id:
        raise HTTPException(status_code=400, detail="Cannot add yourself")
    other = await db.get(User, body.user_id)
    if other is None:
        raise HTTPException(status_code=404, detail="User not found")

    row = await add_contact(db, current_user.id, body.user_id)
    await db.refresh(row, ["connected_user"])
    return ConnectionOut(
        id=row.id,
        connected_user_id=row.connected_user_id,
        connected_user=row.connected_user,
        created_at=row.created_at,
        state=await closeness(db, current_user.id, row.connected_user_id),
    )


@router.delete("/me/connections/{user_id}", status_code=204)
async def remove_connection(
    user_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Drop someone from my contacts. Their row, if they keep one, is theirs."""
    row = (
        await db.execute(
            select(Connection).where(
                Connection.user_id == current_user.id,
                Connection.connected_user_id == user_id,
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Not in your contacts")
    await db.delete(row)
    await db.commit()


# ── T3.12.06 · close people: asked, and answered ───────────────────────────


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def _close_out(db: AsyncSession, pair: ClosePair, me: uuid.UUID) -> ClosePairOut:
    other_id = pair.addressee_id if pair.requester_id == me else pair.requester_id
    other = await db.get(User, other_id)
    return ClosePairOut(
        id=pair.id,
        user_id=other_id,
        display_name=other.display_name if other else None,
        handle=other.handle if other else None,
        state=state_of(pair, me),
        requested_at=pair.requested_at,
        accepted_at=pair.accepted_at,
    )


async def _request_for_me(db: AsyncSession, pair_id: uuid.UUID, me: uuid.UUID) -> ClosePair:
    """A request is answered only by the person it was made to. Anybody else's
    is not found rather than forbidden: its existence is not theirs to learn."""
    pair = await db.get(ClosePair, pair_id)
    if pair is None or pair.addressee_id != me:
        raise HTTPException(status_code=404, detail="Request not found")
    if pair.accepted_at or pair.declined_at or pair.ended_at:
        raise HTTPException(status_code=409, detail="This request is no longer open")
    return pair


class CloseBody(BaseModel):
    user_id: uuid.UUID


@router.get("/me/close", response_model=list[ClosePairOut])
async def list_close(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """My close people, the requests I made, and the requests made of me."""
    return [
        await _close_out(db, pair, current_user.id)
        for pair in await open_pairs(db, current_user.id)
    ]


@router.post("/me/close", response_model=ClosePairOut, status_code=201)
async def request_close(
    body: CloseBody,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Ask a contact to be close.

    Only of somebody already in my contacts (owner, 2026-09-14) — refused by the
    API, not by a hidden button. Asking somebody who has already asked me is the
    answer to their request: both have said it. Asking twice is the same request.
    """
    if body.user_id == current_user.id:
        raise HTTPException(status_code=400, detail="Cannot be close to yourself")
    contact = (
        await db.execute(
            select(Connection.id).where(
                Connection.user_id == current_user.id,
                Connection.connected_user_id == body.user_id,
            )
        )
    ).first()
    if contact is None:
        raise HTTPException(status_code=404, detail="Add them to your contacts first")

    pair = await open_pair(db, current_user.id, body.user_id)
    if pair is None:
        pair = ClosePair(requester_id=current_user.id, addressee_id=body.user_id)
        db.add(pair)
        try:
            await db.commit()
        except IntegrityError:
            # Both asked at once: the unique open-pair index let one through.
            await db.rollback()
            pair = await open_pair(db, current_user.id, body.user_id)
    if pair is not None and pair.accepted_at is None and pair.addressee_id == current_user.id:
        pair.accepted_at = _now()
        await db.commit()
    await db.refresh(pair)
    return await _close_out(db, pair, current_user.id)


@router.post("/me/close/{pair_id}/accept", response_model=ClosePairOut)
async def accept_close(
    pair_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    pair = await _request_for_me(db, pair_id, current_user.id)
    pair.accepted_at = _now()
    await db.commit()
    await db.refresh(pair)
    return await _close_out(db, pair, current_user.id)


@router.post("/me/close/{pair_id}/decline", response_model=ClosePairOut)
async def decline_close(
    pair_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    pair = await _request_for_me(db, pair_id, current_user.id)
    pair.declined_at = _now()
    await db.commit()
    await db.refresh(pair)
    return await _close_out(db, pair, current_user.id)


@router.delete("/me/close/{user_id}", status_code=204)
async def end_close(
    user_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """End it from either side: stop being close, withdraw my request, or turn
    down theirs. The path names a person; the row touched is always one the
    caller is in, so a stranger gets 404 by construction."""
    pair = await open_pair(db, current_user.id, user_id)
    if pair is None:
        raise HTTPException(status_code=404, detail="Nothing between you to end")
    if pair.accepted_at is None and pair.addressee_id == current_user.id:
        pair.declined_at = _now()
    else:
        pair.ended_at = _now()
        pair.ended_by_id = current_user.id
    await db.commit()


class FoundUser(BaseModel):
    """T3.11.24 — the least a picker needs to show a person and attach them.

    Deliberately not `UserOut`: that one carries the email and phone, and this
    endpoint is reached by anybody who can type. What comes back is what the
    searcher already had (the handle they typed, or nothing) plus a name to
    recognise — never a second contact detail they did not have.
    """

    id: uuid.UUID
    display_name: str
    handle: str | None = None


@router.get("/users/lookup", response_model=list[FoundUser])
@limiter.limit("30/minute")
async def lookup_user(
    request: Request,
    q: str = Query(min_length=3, max_length=255),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Find one person by something you already know about them.

    Owner's decision 2026-09-07: «поиск сделаем по почте и номеру телефона
    указанному в личном кабинете», plus the handle chosen there.

    **Exact match only, on all three.** Not a nicety — a prefix search over
    emails or phone numbers is an address-book harvester: `+9715...` would walk
    a country's numbering plan a page at a time. Requiring the whole value means
    the searcher already had it, which is the same standing every messenger
    grants a contact import.

    Handles are matched whole for the same reason, though the argument is
    weaker: a handle is chosen to be public. Prefix search over handles can come
    later as a product decision; it is not one to make silently inside a
    contacts feature.

    Phone numbers are normalised to E.164 first — `+7 900 000-00-00` and
    `+79000000000` are one number, and comparing raw text would find neither.
    Both `users.phone` and confirmed `user_contacts` rows are searched: an
    account may have arrived by email and added a phone afterwards, and the two
    live in different places for reasons `T3.25` explains.

    Rate-limited because exact match still answers «does this address have an
    account here», one guess at a time. Thirty a minute is a person typing; a
    list of addresses being tested is not.
    """
    needle = q.strip()

    handle = needle.lstrip("@").lower()
    email = normalize("email", needle)
    phone = normalize("sms", needle)

    conditions = [User.handle == handle]
    if email:
        conditions.append(User.email == email)
    if phone:
        conditions.append(User.phone == phone)
    rows = (await db.execute(select(User).where(or_(*conditions)))).scalars().all()
    found = {u.id: u for u in rows}

    if email or phone:
        contact_rows = (
            await db.execute(
                select(UserContact.user_id).where(
                    UserContact.value.in_([v for v in (email, phone) if v]),
                    UserContact.verified_at.isnot(None),
                )
            )
        ).scalars().all()
        extra = [uid for uid in contact_rows if uid not in found]
        if extra:
            for u in (
                (await db.execute(select(User).where(User.id.in_(extra))))
                .scalars()
                .all()
            ):
                found[u.id] = u

    return [
        FoundUser(id=u.id, display_name=u.display_name, handle=u.handle)
        for u in found.values()
        # Finding yourself is not a result: the picker would offer to make you
        # your own contact, and the API refuses that anyway.
        if u.id != current_user.id
    ]
