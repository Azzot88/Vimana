"""T3.32 — which kinds of event reach which channel, per account.

Until now a channel was on or off for **everything**: three booleans on `users`
(`notify_email` / `notify_telegram` / `notify_whatsapp`). Wanting "cargo
delivered" in Telegram and the rest by mail was not expressible, so the only way
to quieten one thing was to quieten all of them — which is how people end up
with every notification off and then miss the one that mattered.

The matrix is event **class** × channel, not event × channel. A row per
individual message would be a settings screen nobody finishes reading, and the
classes below are the granularity at which people actually differ.

**Storage is one JSONB column, and a missing key means the default.** Not a
table: the read is always "this one user's preferences", loaded with the user
anyway. Not a fully-materialised dict either — a stored blob that must contain
every key is a blob that goes stale the moment a class is added, and the
migration to fix it would have to guess what each existing account wanted.
Reading a gap as the default means a new class arrives switched to something
sensible for everybody, with no migration at all.

**The security class cannot be turned off.** This was already true in practice —
`send_verification_code`, `send_recovery_code_used`, `send_platform_copy_deleted`,
`send_archive_window_opened`, `send_password_reset`, `send_password_changed` and
`send_new_device` never consulted `notify_email` — but it was true only as a
habit repeated in seven places. Here it is a property of the class, so the next
security letter inherits it instead of having to remember it. The reason is not
tidiness: since `T3.28` a mailbox alone opens an account, and "somebody signed
in with your recovery code" is not a subscription, it is the single signal by
which an owner learns the account is no longer only theirs.

**Classes with nothing to emit are declared but not shown.** `vault`, `trust`
and `dispute` are real classes of the product that no code sends yet. They are
in the registry so the taxonomy is complete and so turning one on later is a
flag rather than a migration — and `emitted=False` keeps them out of the screen,
because a switch for a message that never arrives is a promise the product does
not keep.

Functions (PROJECT §6.2a):
- `class_of(kind) -> str | None` — which class a letter belongs to.
  Called by: `tasks/notifications._notify_user`.
- `wants(user, event_class, channel) -> bool` — the actual decision.
  Called by: `tasks/notifications._notify_user`, `resolved`.
- `resolved(user) -> dict` — the full matrix for the screen, gaps filled in.
  Called by: `core/avatar_url.me_out_with_avatar`.
- `locked_classes() -> list[str]` — classes the screen must render as fixed.
  Called by: `core/avatar_url.me_out_with_avatar`.
- `active_channels() -> tuple[str, ...]` — the matrix's columns.
  Called by: `resolved`, `sanitize`.
- `connected_channels(user) -> dict[str, bool]` — which of them this account
  actually has an address on. Called by: `core/avatar_url.me_out_with_avatar`.
- `sanitize(raw) -> dict` — what a client is allowed to write.
  Called by: `schemas/user.UserUpdate`.
- `merged(current, incoming) -> dict` — apply a partial write.
  Called by: `api/auth.update_me`.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.core import channels

# Channels a notification can travel down. Not the same list as
# `core/channels.CHANNELS`: `sms` and `telegram_gateway` deliver a code to a
# number and were never notification transports. Which of these three is
# actually live is `channels.enabled` — one switch, not a second list here that
# could disagree with it.
NOTIFY_CHANNELS: tuple[str, ...] = (channels.EMAIL, channels.TELEGRAM, channels.WHATSAPP)


@dataclass(frozen=True)
class EventClass:
    key: str
    #: Kinds of letter that belong here (`core/email_templates._LETTERS` keys).
    kinds: tuple[str, ...]
    #: What an account gets before it has ever touched the screen.
    default: bool = True
    #: Cannot be switched off. See the module docstring.
    mandatory: bool = False
    #: Something in the codebase actually sends this today.
    emitted: bool = True


#: Order matters — it is the order of the rows on the screen.
EVENT_CLASSES: tuple[EventClass, ...] = (
    EventClass("deal", kinds=("deal_status",)),
    EventClass("deadline", kinds=("deadline_reminder",)),
    # No producer yet. Declared so the taxonomy is whole and so the day one
    # appears is a one-word change here rather than a migration.
    EventClass("vault", kinds=(), emitted=False),
    EventClass("trust", kinds=(), emitted=False),
    EventClass("dispute", kinds=(), emitted=False),
    EventClass(
        "security",
        kinds=(
            "verification_code",
            "recovery_code_used",
            "password_reset",
            "password_changed",
            "new_device",
            "platform_copy_deleted",
            "archive_window_opened",
            # T3.42 — a change of what somebody may do with other people's data
            # cannot depend on a notification toggle.
            "role_offered",
        ),
        mandatory=True,
    ),
)

_BY_KEY = {cls.key: cls for cls in EVENT_CLASSES}
_BY_KIND = {kind: cls.key for cls in EVENT_CLASSES for kind in cls.kinds}


def class_of(kind: str) -> str | None:
    """Which class a letter belongs to, or `None` for one that has no class.

    `None` is a real answer, not a failure: the waitlist letters go to an
    address with no account behind it, so there is nobody whose preferences
    could apply.
    """
    return _BY_KIND.get(kind)


def active_channels() -> tuple[str, ...]:
    """All three transports, always, in a fixed order.

    This hid a channel until `channels.enabled` said yes, so WhatsApp was to
    appear on the day `T3.31` turned it on. Owner's decision 2026-08-11: show
    all three. The worry that produced the earlier rule — a column for a pipe
    that does not exist — is answered better by `connected_channels`: the column
    is there, and it is visibly unusable until the account has an address on it.
    Hiding it left the person wondering whether WhatsApp exists here at all.
    """
    return NOTIFY_CHANNELS


def connected_channels(user) -> dict[str, bool]:
    """Which channels this account can actually be reached on.

    The same three attributes `_notify_user` checks before handing anything to
    a transport — deliberately, so that "the screen says connected" and "the
    worker will actually send" cannot drift apart. A preference on a channel
    with no address is a wish, and the screen should say so rather than offer a
    switch that changes nothing.
    """
    return {
        channels.EMAIL: bool(getattr(user, "email", None)),
        channels.TELEGRAM: bool(getattr(user, "telegram_chat_id", None)),
        channels.WHATSAPP: bool(getattr(user, "whatsapp_number", None)),
    }


def visible_classes() -> tuple[EventClass, ...]:
    return tuple(cls for cls in EVENT_CLASSES if cls.emitted)


def locked_classes() -> list[str]:
    return [cls.key for cls in visible_classes() if cls.mandatory]


def wants(user, event_class: str, channel: str) -> bool:
    """Does this account want this class of event on this channel?

    The single decision the rest of the code asks for. Everything else in this
    module exists to build it, store it, or draw it.
    """
    known = _BY_KEY.get(event_class)
    if known is None:
        # An unknown class is not silence. A message with a class nobody
        # registered is a bug, and delivering it is recoverable while dropping
        # it is not — the owner would simply never learn the thing happened.
        return True
    if known.mandatory:
        return True

    prefs = getattr(user, "notification_prefs", None) or {}
    row = prefs.get(event_class)
    if not isinstance(row, dict) or channel not in row:
        return known.default
    return bool(row[channel])


def resolved(user) -> dict[str, dict[str, bool]]:
    """The matrix as the screen needs it: every visible cell, gaps filled in.

    The client never sees the stored blob. It is partial by design, and a screen
    that had to know the defaults in order to draw a half-empty object would be
    a second copy of the rules living in TypeScript.
    """
    return {
        cls.key: {name: wants(user, cls.key, name) for name in active_channels()}
        for cls in visible_classes()
    }


def sanitize(raw) -> dict[str, dict[str, bool]]:
    """Keep only what a client is allowed to say. Raises on the wrong shape.

    Unknown classes and unknown channels are dropped rather than rejected: they
    are what an older or newer client sends, and refusing the whole write over
    one stale key would break the screen for everybody mid-deploy. A value that
    is not a boolean is a different matter — that is a client that has
    misunderstood the field, and it is told so.
    """
    if not isinstance(raw, dict):
        raise ValueError("notification_prefs must be an object")

    allowed_channels = set(active_channels())
    cleaned: dict[str, dict[str, bool]] = {}
    for key, row in raw.items():
        known = _BY_KEY.get(key)
        # Mandatory classes are dropped, not refused. The screen renders them
        # as fixed, so a write arriving for one is a stale client rather than an
        # attack — and it changes nothing either way, because `wants` does not
        # consult storage for them.
        if known is None or known.mandatory or not known.emitted:
            continue
        if not isinstance(row, dict):
            raise ValueError(f"notification_prefs['{key}'] must be an object")
        row_clean = {}
        for channel, value in row.items():
            if channel not in allowed_channels:
                continue
            if not isinstance(value, bool):
                raise ValueError(
                    f"notification_prefs['{key}']['{channel}'] must be true or false"
                )
            row_clean[channel] = value
        if row_clean:
            cleaned[key] = row_clean
    return cleaned


def merged(current, incoming: dict[str, dict[str, bool]]) -> dict[str, dict[str, bool]]:
    """Apply a partial write on top of what is stored.

    A `PATCH` that carried the whole matrix would make two people editing two
    different rows overwrite each other, and would require the screen to send
    settings it may not even render — a client one version behind would quietly
    reset the class it does not know about.
    """
    result = {key: dict(row) for key, row in (current or {}).items()}
    for key, row in incoming.items():
        result.setdefault(key, {}).update(row)
    return result
