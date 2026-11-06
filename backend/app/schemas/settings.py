from datetime import datetime
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, Field

from app.schemas.common import Currency


class SalesTargetOut(BaseModel):
    amount_minor: int
    currency: str
    set_by: str | None = Field(description="Who set it; null while the deployment default applies")
    set_at: datetime | None


class SalesTargetUpdate(BaseModel):
    amount: Annotated[
        Decimal,
        Field(gt=0, le=Decimal("1000000000000"), description="Quarterly target, e.g. '400000'"),
    ]
    currency: Currency = "USD"
