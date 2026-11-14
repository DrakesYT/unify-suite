"""Workflow templates: steps, dependencies and run conditions as plain data."""

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from app.models.enums import Department, StepStatus

# step key -> (status, output) of the steps that already finished
Finished = dict[str, tuple[StepStatus, dict[str, Any] | None]]


def _always(_: Finished) -> bool:
    return True


@dataclass(frozen=True)
class StepSpec:
    key: str
    title: str
    department: Department | None
    after: tuple[str, ...] = ()
    # Evaluated once every `after` step has finished. False → the step is skipped.
    when: Callable[[Finished], bool] = field(default=_always)


@dataclass(frozen=True)
class Template:
    name: str  # URL slug, also workflow_definitions.name
    description: str
    steps: tuple[StepSpec, ...]

    def spec(self, key: str) -> StepSpec:
        return next(s for s in self.steps if s.key == key)

    def as_json(self) -> list[dict[str, Any]]:
        return [
            {"key": s.key, "title": s.title, "department": s.department, "after": list(s.after)}
            for s in self.steps
        ]


def _f2_mismatch(done: Finished) -> bool:
    return (done["F2"][1] or {}).get("match_status") == "mismatch"


def _a1_approved(done: Finished) -> bool:
    return done["A1"][0] == StepStatus.succeeded


SUPPLIER_PAYMENT = Template(
    name="supplier-payment",
    description="Workflow B: verify a supplier invoice against its PO, get approval, then pay.",
    steps=(
        StepSpec("F1", "Extract invoice fields", Department.finance),
        # After F1: when nobody typed a PO number, the one the invoice names is used.
        StepSpec("P1", "Load purchase order", Department.procurement, after=("F1",)),
        StepSpec("F2", "Match invoice to PO", Department.finance, after=("P1", "F1")),
        StepSpec(
            "F3", "Write discrepancy report", Department.finance, after=("F2",), when=_f2_mismatch
        ),
        StepSpec("A1", "Manager approval to pay", Department.finance, after=("F2", "F3")),
        StepSpec("F4", "Submit payment", Department.finance, after=("A1",), when=_a1_approved),
        StepSpec("V1", "Verify records are linked", None, after=("A1", "F4")),
    ),
)

TEMPLATES = {SUPPLIER_PAYMENT.name: SUPPLIER_PAYMENT}
