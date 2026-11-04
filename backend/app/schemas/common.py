from typing import Annotated

from pydantic import AfterValidator, BaseModel, Field

Currency = Annotated[
    str,
    AfterValidator(str.upper),
    Field(pattern=r"^[A-Za-z]{3}$", description="ISO 4217 code", examples=["USD"]),
]
MinorAmount = Annotated[int, Field(ge=0, description="Amount in minor units (cents)")]
Name = Annotated[str, Field(min_length=1, max_length=160)]


class Page[T](BaseModel):
    items: list[T]
    next_cursor: str | None = Field(description="Pass as ?cursor= to get the next page")
