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

    # Superuser surface — User Zero only
    USERS_MANAGE = "users:manage"
    ARBITER_ASSIGN = "arbiter:assign"


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
