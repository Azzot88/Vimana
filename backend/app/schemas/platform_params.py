import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_validator

from app.models.platform_params import GLOBAL_SCOPE, ParamValueType


class ParamVersionOut(BaseModel):
    id: uuid.UUID
    key: str
    scope: str
    value: str
    value_type: ParamValueType
    effective_from: datetime
    comment: str
    created_by_id: uuid.UUID | None
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class ParamCurrentOut(BaseModel):
    """One row of the admin screen: the value in force plus where it came from.

    `source` is what makes the screen honest — an operator has to be able to see
    that a number is a built-in default rather than something somebody chose.
    """

    key: str
    scope: str
    value: str
    value_type: ParamValueType
    group: str
    approved: bool
    note: str
    source: str  # "default" | "global" | "corridor"
    effective_from: datetime | None
    comment: str


class ParamSetIn(BaseModel):
    key: str
    value: str
    scope: str = GLOBAL_SCOPE
    comment: str = ""
    # Absent means "from now". A future stamp schedules the change.
    effective_from: datetime | None = None

    @field_validator("scope")
    @classmethod
    def _scope_shape(cls, v: str) -> str:
        v = v.strip()
        if not v:
            return GLOBAL_SCOPE
        if v == GLOBAL_SCOPE:
            return v
        if "->" not in v:
            raise ValueError("scope must be 'global' or a corridor like 'AE->US'")
        return v.upper()

    @field_validator("value")
    @classmethod
    def _value_present(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("value must not be empty")
        return v.strip()
