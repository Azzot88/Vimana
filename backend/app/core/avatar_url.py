"""T_UX.4 B — helper that turns a User → MeOut with a fresh presigned
avatar URL. Kept out of the schema module so schemas stay free of I/O.

T3.32 — and with the notification matrix resolved. Both are the same kind of
thing: a field whose value is not the column, computed in the one place every
`MeOut` passes through, so no caller can produce a half-built owner view.
"""
from __future__ import annotations

from app.core.notification_prefs import connected_channels, locked_classes, resolved
from app.core.storage import get_presigned_url
from app.models.user import User
from app.schemas.user import MeOut


def me_out_with_avatar(user: User) -> MeOut:
    out = MeOut.model_validate(user, from_attributes=True)
    out.avatar_url = get_presigned_url(user.avatar_key) if user.avatar_key else None
    # Overwritten, not merged: `model_validate` has just copied the **stored**
    # column, which is partial by design. Sending that outward would make the
    # screen guess at the missing cells.
    out.notification_prefs = resolved(user)
    out.notification_locked = locked_classes()
    out.notification_channels = connected_channels(user)
    return out
