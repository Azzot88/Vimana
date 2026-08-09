"""T1.24 pt.1 — Role-based access control.

Design:
- `Permission` is the unit of authorization. Every protected action names one.
- `Role` is a named bundle of permissions (`ROLE_PERMISSIONS`).
- `User.role` holds a single role.
- Self-service capabilities (`can_carry`, `can_send`) contribute permissions on
  top of the role — a base user opts into publishing trips or creating orders.

When the model needs to grow (per-user overrides, multi-role, custom bundles),
only `perms_of()` implementation changes — endpoint call-sites don't move.
"""
from __future__ import annotations

import enum
from datetime import datetime, timedelta, timezone
from functools import lru_cache

from fastapi import Depends, HTTPException

from app.api.deps import get_current_user
from app.models.user import User


class Permission(str, enum.Enum):
    # Self-service capabilities (opt-in via user profile)
    TRIP_PUBLISH = "trip:publish"
    ORDER_CREATE = "order:create"

    # T2.1 — Peer verification surface
    IDENTITY_REQUEST = "identity:request"
    IDENTITY_SELF_UPLOAD = "identity:self_upload"
    VERIFICATION_REVOKE_OWN = "verification:revoke_own"

    # Arbiter surface — assigned by superuser
    DISPUTE_CLAIM = "dispute:claim"
    DISPUTE_RESOLVE = "dispute:resolve"
    VAULT_READ_AS_ARBITER = "vault:read_as_arbiter"
    DISPUTE_LIST_ADMIN = "dispute:list_admin"
    IDENTITY_CONTAINER_READ = "identity:container_read"  # via escalation
    VERIFICATION_REVOKE_ANY = "verification:revoke_any"
    THRESHOLD_ARBITER_REVEAL = "threshold:arbiter_reveal"  # T2.3
    NOSTR_REPUBLISH = "nostr:republish"  # T3.5 pt.2 — superuser force republish
    NOTICES_MANAGE = "notices:manage"  # T_UX.2 pt.2 — CRUD RouteNote/PlatformNotice

    # Superuser surface — User Zero only
    USERS_MANAGE = "users:manage"
    ARBITER_ASSIGN = "arbiter:assign"
    # T_UX.8 pt.2 — reading the waitlist. Its own name rather than a reuse of
    # `USERS_MANAGE`: these are people who are *not* users yet, and a permission
    # that reads "manage users" would quietly grant a second, different thing.
    WAITLIST_READ = "waitlist:read"
    # T_UX.9 pt.2 — the mail console: read the circuits' state and preview the
    # letters. Read-only by nature; the one action behind it (a test send) is
    # wired to the preview circuit and cannot reach a real inbox.
    EMAIL_MANAGE = "email:manage"
    # T_UX.12 — re-pointing the bot's webhook. Its own name because it is not
    # "manage users" by any reading, and because the action is infrastructural:
    # whoever holds it decides where Telegram delivers every update.
    TELEGRAM_MANAGE = "telegram:manage"


class Role(str, enum.Enum):
    USER = "user"
    ARBITER = "arbiter"
    SUPERUSER = "superuser"


_ARBITER_PERMS: frozenset[Permission] = frozenset({
    Permission.DISPUTE_CLAIM,
    Permission.DISPUTE_RESOLVE,
    Permission.VAULT_READ_AS_ARBITER,
    Permission.DISPUTE_LIST_ADMIN,
    Permission.IDENTITY_CONTAINER_READ,
    Permission.VERIFICATION_REVOKE_ANY,
    Permission.THRESHOLD_ARBITER_REVEAL,
})

_SUPERUSER_PERMS: frozenset[Permission] = frozenset(Permission)  # all

ROLE_PERMISSIONS: dict[Role, frozenset[Permission]] = {
    Role.USER: frozenset(),
    Role.ARBITER: _ARBITER_PERMS,
    Role.SUPERUSER: _SUPERUSER_PERMS,
}


@lru_cache(maxsize=8)
def _base_perms_for(role_value: str) -> frozenset[Permission]:
    try:
        role = Role(role_value)
    except ValueError:
        role = Role.USER
    return ROLE_PERMISSIONS[role]


def perms_of(user: User) -> frozenset[Permission]:
    """All permissions this user currently has."""
    perms: set[Permission] = set(_base_perms_for(user.role or Role.USER.value))
    if user.can_carry:
        perms.add(Permission.TRIP_PUBLISH)
    if user.can_send:
        perms.add(Permission.ORDER_CREATE)
    # T2.1 — every authenticated user can request verification, self-upload,
    # and revoke their own peer-verification badges.
    perms.update(
        {
            Permission.IDENTITY_REQUEST,
            Permission.IDENTITY_SELF_UPLOAD,
            Permission.VERIFICATION_REVOKE_OWN,
        }
    )
    return frozenset(perms)


def has_perm(user: User, permission: Permission) -> bool:
    return permission in perms_of(user)


def require(user: User, *permissions: Permission) -> None:
    have = perms_of(user)
    for p in permissions:
        if p not in have:
            raise HTTPException(
                status_code=403,
                detail=f"Missing permission: {p.value}",
            )


def require_perm(*permissions: Permission):
    """FastAPI dependency factory. Usage: `Depends(require_perm(Permission.X))`."""

    async def _dep(user: User = Depends(get_current_user)) -> User:
        require(user, *permissions)
        return user

    return _dep


# ─────────────────────────────────────────────────────────────
# T3.18 — how much of an identity a given viewer may see
# ─────────────────────────────────────────────────────────────

PUBLIC_PROFILE_VALUES = ("full", "minimal", "hidden")


def visible_to(subject: User, viewer: User | None) -> str:
    """`full` | `minimal` | `hidden` for this pair.

    One function on purpose, called from every public slice. The alternative —
    the same condition copied into each endpoint — fails the same way every
    time: the next public field is added by someone who never heard of the
    setting, and an account that believes itself hidden keeps answering
    questions about itself through a different URL.

    The owner always sees themselves in full; so does a superuser, whose whole
    job is looking at accounts. Everyone else gets what the account chose.
    """
    if viewer is not None and (viewer.id == subject.id or viewer.role == "superuser"):
        return "full"
    # T3.19 — a closed archive outranks the ordinary setting. It is the same
    # word ('hidden') but a different decision: the account below is retired and
    # its owner said no. Checking it here, rather than in the identity endpoint,
    # is the whole point of having one gate — the next public slice inherits it
    # without knowing this feature exists.
    if (subject.archive_choice or "").lower() == "hide":
        return "hidden"
    level = (subject.public_profile or "full").lower()
    return level if level in PUBLIC_PROFILE_VALUES else "full"


def require_visible(subject: User, viewer: User | None) -> str:
    """Same, but 404 for `hidden` — not 403.

    403 would confirm that the account exists, which is exactly what hiding is
    meant to stop. "No such identity" is the only answer that does not leak the
    thing it refuses to show.
    """
    level = visible_to(subject, viewer)
    if level == "hidden":
        raise HTTPException(status_code=404, detail="No such identity")
    return level


# ─────────────────────────────────────────────────────────────
# T3.19 — the window in which a retired identity may close its archive
# ─────────────────────────────────────────────────────────────

ARCHIVE_WINDOW_DAYS = 15


def archive_window_ends_at(user: User) -> datetime | None:
    """When this account's say over its own exhibit stops being available.

    None for an identity that is still live — there is nothing to decide while
    the key works. Derived from `key_lost_at` rather than stored, so the date
    shown in the notice, the date checked by the endpoint and the date in the
    email cannot disagree.

    Fifteen days is short enough that the archive is not held hostage by
    accounts that will never log in again, and long enough that someone who
    lost a key on holiday still gets to answer.
    """
    if user.key_lost_at is None:
        return None
    return user.key_lost_at + timedelta(days=ARCHIVE_WINDOW_DAYS)


def archive_window_open(user: User, now: datetime | None = None) -> bool:
    """Whether the choice can still be made or changed.

    Closing is *only* possible inside the window. The notice promises a date
    after which the decision is fixed, and an API that quietly kept accepting
    changes afterwards would make that promise false — worse than a stricter
    rule, because people plan around it.
    """
    ends = archive_window_ends_at(user)
    if ends is None:
        return False
    return (now or datetime.now(tz=timezone.utc)) < ends
