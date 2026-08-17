"""T3.40 — admin surface for business-logic parameters.

Reads are open to anyone holding the permission; writes append a version and
never touch an existing row, so the history that answers "who changed the fee
and when" cannot be edited away from this API.
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.core.params import REGISTRY, REGISTRY_BY_KEY, parse_value
from app.core.permissions import Permission, require_perm
from app.models.platform_params import GLOBAL_SCOPE, PlatformParameter
from app.models.user import User
from app.schemas.platform_params import ParamCurrentOut, ParamSetIn, ParamVersionOut

router = APIRouter()


async def _latest_row(
    db: AsyncSession, key: str, scope: str, moment: datetime
) -> PlatformParameter | None:
    stmt = (
        select(PlatformParameter)
        .where(
            PlatformParameter.key == key,
            PlatformParameter.scope == scope,
            PlatformParameter.effective_from <= moment,
        )
        .order_by(PlatformParameter.effective_from.desc())
        .limit(1)
    )
    return (await db.execute(stmt)).scalar_one_or_none()


@router.get("/admin/params", response_model=list[ParamCurrentOut])
async def list_params(
    scope: str = Query(GLOBAL_SCOPE),
    _: User = Depends(require_perm(Permission.PARAMS_MANAGE)),
    db: AsyncSession = Depends(get_db),
):
    """Values in force for `scope`, with corridor rows shadowing global ones."""
    moment = datetime.now(timezone.utc)
    out: list[ParamCurrentOut] = []

    for spec in REGISTRY:
        row = None
        source = "default"
        if scope and scope != GLOBAL_SCOPE:
            row = await _latest_row(db, spec.key, scope, moment)
            if row is not None:
                source = "corridor"
        if row is None:
            row = await _latest_row(db, spec.key, GLOBAL_SCOPE, moment)
            if row is not None:
                source = "global"

        out.append(
            ParamCurrentOut(
                key=spec.key,
                scope=scope or GLOBAL_SCOPE,
                value=row.value if row else spec.default,
                value_type=row.value_type if row else spec.value_type,
                group=spec.group,
                approved=spec.approved,
                note=spec.note,
                source=source,
                effective_from=row.effective_from if row else None,
                comment=row.comment if row else "",
            )
        )
    return out


@router.get("/admin/params/{key}/history", response_model=list[ParamVersionOut])
async def param_history(
    key: str,
    scope: str | None = Query(None),
    _: User = Depends(require_perm(Permission.PARAMS_MANAGE)),
    db: AsyncSession = Depends(get_db),
):
    if key not in REGISTRY_BY_KEY:
        raise HTTPException(status_code=404, detail="Unknown parameter")

    stmt = select(PlatformParameter).where(PlatformParameter.key == key)
    if scope:
        stmt = stmt.where(PlatformParameter.scope == scope)
    stmt = stmt.order_by(PlatformParameter.effective_from.desc())
    return list((await db.execute(stmt)).scalars().all())


@router.post("/admin/params", response_model=ParamVersionOut, status_code=201)
async def set_param(
    payload: ParamSetIn,
    current_user: User = Depends(require_perm(Permission.PARAMS_MANAGE)),
    db: AsyncSession = Depends(get_db),
):
    """Append a new version. Nothing is updated in place — see the model docstring."""
    spec = REGISTRY_BY_KEY.get(payload.key)
    if spec is None:
        raise HTTPException(status_code=404, detail="Unknown parameter")

    # Reject a malformed number here rather than at settlement time, where it
    # would surface as a failed deal instead of a failed form.
    try:
        parse_value(payload.value, spec.value_type)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    row = PlatformParameter(
        key=spec.key,
        scope=payload.scope,
        value=payload.value,
        value_type=spec.value_type,
        effective_from=payload.effective_from or datetime.now(timezone.utc),
        comment=payload.comment,
        created_by_id=current_user.id,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row
