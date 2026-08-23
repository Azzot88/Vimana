"""T1.24 pt.1 — permission derivation from role + capabilities.

The second half of this file (T3.18 / T3.19) exists because of T_TEST.10. These
functions were covered only sideways, through endpoints that happened to call
them, and mutation testing showed what that was worth: inverting the superuser
check in `visible_to` — which hands every signed-in stranger a full view of an
account that chose to hide — left all 1746 tests green.

Unit tests here rather than more endpoint tests on purpose. `visible_to` is the
single gate every public slice asks, and the cases worth pinning are its own
decisions, not any one route's use of them.
"""
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException

from app.core.permissions import (
    ARCHIVE_WINDOW_DAYS,
    Permission,
    Role,
    archive_window_ends_at,
    archive_window_open,
    has_perm,
    perms_of,
    require_visible,
    visible_to,
)


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


# ── T3.18: how much of an identity a given viewer may see ─────────────────


def _identity(uid=1, role="user", public_profile="full", archive_choice=None):
    from types import SimpleNamespace

    return SimpleNamespace(
        id=uid,
        role=role,
        public_profile=public_profile,
        archive_choice=archive_choice,
    )


def test_owner_sees_themselves_whatever_they_chose():
    me = _identity(uid=1, public_profile="hidden")
    assert visible_to(me, me) == "full"


def test_superuser_sees_a_hidden_account():
    subject = _identity(uid=1, public_profile="hidden")
    assert visible_to(subject, _identity(uid=2, role="superuser")) == "full"


def test_an_ordinary_viewer_is_not_privileged():
    """The comparison is `== "superuser"` and has to stay that way round.

    Inverted, every signed-in stranger reads as an administrator, and the whole
    setting quietly stops existing — an account that believes itself hidden goes
    on answering questions about itself to anyone with a session. That inversion
    survived the entire suite before this test.
    """
    subject = _identity(uid=1, public_profile="hidden")
    assert visible_to(subject, _identity(uid=2, role="user")) == "hidden"


def test_a_stranger_without_a_session_gets_the_chosen_level():
    assert visible_to(_identity(public_profile="minimal"), None) == "minimal"


def test_closed_archive_outranks_the_profile_setting():
    """Same word, different decision: this one was made by a retired owner and
    is not theirs to revisit through the ordinary setting."""
    subject = _identity(public_profile="full", archive_choice="Hide")
    assert visible_to(subject, None) == "hidden"


def test_an_unrecognised_level_is_not_a_level():
    """A value the product no longer writes must fall back, not pass through —
    otherwise a stale row invents a visibility nobody implemented."""
    assert visible_to(_identity(public_profile="friends-only"), None) == "full"


def test_hidden_is_refused_as_404_not_403():
    """403 confirms the account exists, which is exactly what hiding is for.

    The status is the promise; the wording of `detail` deliberately is not, so
    it is left unpinned — a test that spells out error prose fails on rewording
    and catches nothing.
    """
    with pytest.raises(HTTPException) as refused:
        require_visible(_identity(public_profile="hidden"), None)
    assert refused.value.status_code == 404


def test_visible_levels_pass_through_require_visible():
    assert require_visible(_identity(public_profile="minimal"), None) == "minimal"


# ── T3.19: the window for closing a retired identity's archive ────────────


def _retired(lost_at):
    from types import SimpleNamespace

    return SimpleNamespace(key_lost_at=lost_at)


def test_a_live_identity_has_no_window():
    assert archive_window_ends_at(_retired(None)) is None


def test_a_live_identity_cannot_make_the_choice():
    """`None` means "nothing to decide while the key works", not "no deadline,
    so go ahead" — the difference is whether an account that never lost anything
    can close an archive."""
    assert archive_window_open(_retired(None)) is False


def test_the_window_is_open_inside_it():
    lost = datetime.now(tz=timezone.utc) - timedelta(days=1)
    assert archive_window_open(_retired(lost)) is True


def test_the_window_shuts_on_the_promised_date_and_not_after():
    """The notice names a date after which the decision is fixed. An API still
    accepting changes on that date would make the notice false — so the boundary
    itself is the test, not a day either side of it.
    """
    lost = datetime(2026, 8, 1, tzinfo=timezone.utc)
    user = _retired(lost)
    ends = archive_window_ends_at(user)

    assert ends == lost + timedelta(days=ARCHIVE_WINDOW_DAYS)
    assert archive_window_open(user, now=ends - timedelta(seconds=1)) is True
    assert archive_window_open(user, now=ends) is False
