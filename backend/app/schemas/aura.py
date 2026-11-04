from typing import Annotated, Literal

from pydantic import BaseModel, Field

# route → what it does (shown to the model). Keys are the only routes Aura can return.
ROUTES: dict[str, str] = {
    "sales.qualify_lead": "rate a sales lead hot, warm or cold (Lead Qualifier)",
    "hr.screen_candidates": "screen and rank candidates for a job opening (Resume Screener)",
    "support.investigate_ticket": "investigate a support ticket using order history",
    "procurement.compare_vendors": "compare and rank vendors for a purchase request",
    "finance.verify_invoice": "check a supplier invoice against its PO and approve payment "
    "(needs an uploaded invoice)",
    "none": "the request does not match any of the above",
}
Route = Literal[
    "sales.qualify_lead",
    "hr.screen_candidates",
    "support.investigate_ticket",
    "procurement.compare_vendors",
    "finance.verify_invoice",
    "none",
]
Outcome = Literal["done", "needs_input", "not_found", "not_allowed", "failed", "no_route"]


class AuraRequest(BaseModel):
    message: Annotated[str, Field(min_length=1, max_length=1000)]


class AuraDecision(BaseModel):
    route: Route
    target: Annotated[str, Field(max_length=120)] | None = Field(
        default=None,
        description="Words naming the record: company, job title, ticket subject or item",
    )
    reply: Annotated[str, Field(min_length=1, max_length=300)]


class AuraReply(BaseModel):
    route: Route
    agent: str | None = Field(description="The department agent the request went to")
    reply: str
    outcome: Outcome
    summary: str = Field(description="What actually happened, written by code")
    link: str | None = Field(description="App page to open for details")
