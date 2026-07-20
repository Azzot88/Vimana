"""T_UX.4 B — helper that turns a User → MeOut with a fresh presigned
avatar URL. Kept out of the schema module so schemas stay free of I/O."""
from __future__ import annotations

from app.core.storage import get_presigned_url
from app.models.user import User
from app.schemas.user import MeOut


def me_out_with_avatar(user: User) -> MeOut:
    out = MeOut.model_validate(user, from_attributes=True)
    out.avatar_url = get_presigned_url(user.avatar_key) if user.avatar_key else None
    return out
