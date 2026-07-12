"""T1.24 pt.1 — permission derivation from role + capabilities."""
from app.core.permissions import Permission, Role, has_perm, perms_of


def _make_user(role: str = "user", can_carry: bool = True, can_send: bool = True):
    from types import SimpleNamespace

    return SimpleNamespace(role=role, can_carry=can_carry, can_send=can_send)


def test_base_user_gets_capability_permissions():
    u = _make_user()
    p = perms_of(u)
    assert Permission.TRIP_PUBLISH in p
    assert Permission.ORDER_CREATE in p
    assert Permission.DISPUTE_CLAIM not in p
    assert Permission.USERS_MANAGE not in p


def test_capability_toggle_removes_permission():
    u = _make_user(can_carry=False)
    assert Permission.TRIP_PUBLISH not in perms_of(u)
    assert Permission.ORDER_CREATE in perms_of(u)


def test_arbiter_gets_dispute_permissions():
    u = _make_user(role=Role.ARBITER.value)
    p = perms_of(u)
    assert Permission.DISPUTE_CLAIM in p
    assert Permission.DISPUTE_RESOLVE in p
    assert Permission.VAULT_READ_AS_ARBITER in p
    assert Permission.USERS_MANAGE not in p


def test_superuser_gets_everything():
    u = _make_user(role=Role.SUPERUSER.value)
    p = perms_of(u)
    for perm in Permission:
        assert perm in p


def test_has_perm_matches_perms_of():
    u = _make_user(role=Role.ARBITER.value, can_carry=False)
    assert has_perm(u, Permission.DISPUTE_CLAIM)
    assert not has_perm(u, Permission.TRIP_PUBLISH)
    assert not has_perm(u, Permission.USERS_MANAGE)


def test_unknown_role_falls_back_to_user():
    u = _make_user(role="hacker-role")
    p = perms_of(u)
    # Falls back gracefully — user still has base capability perms.
    assert Permission.TRIP_PUBLISH in p
    assert Permission.DISPUTE_CLAIM not in p
