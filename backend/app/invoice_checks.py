"""Deterministic invoice checks. The Invoice Processor only reads the invoice; these rules decide.

- The PO reference is cleaned up by code: "po-1007", "PO 1007" and "PO#1007" all mean PO-1007, but a
  reference that names more than one number ("PO 2001 / maybe 2002") is ambiguous and never guessed.
- The arithmetic is checked by code: each line's quantity x unit price, and the lines against the
  total due. A total that matches the PO while the lines add up to something else is a mismatch.
"""

import re
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Literal

from app.money import minor_unit_exponent, to_minor
from app.schemas.finance import FieldDifference, InvoiceFields

_NUMBER = re.compile(r"\d{3,}")

PoReferenceStatus = Literal["missing", "clear", "ambiguous"]


@dataclass(frozen=True)
class PoReference:
    raw: str | None
    status: PoReferenceStatus
    number: str | None  # PO-<digits> when the reference is clear


def parse_po_reference(raw: str | None) -> PoReference:
    text = (raw or "").strip()
    numbers = {n.lstrip("0") or "0" for n in _NUMBER.findall(text)}
    if not numbers:
        return PoReference(raw=raw, status="missing", number=None)
    if len(numbers) > 1:
        return PoReference(raw=raw, status="ambiguous", number=None)
    return PoReference(raw=raw, status="clear", number=f"PO-{numbers.pop()}")


def _round(value: Decimal, currency: str) -> Decimal:
    """Round to the currency's smallest unit (cents for USD)."""
    return value.quantize(Decimal(1).scaleb(-minor_unit_exponent(currency)), rounding=ROUND_HALF_UP)


def line_item_differences(fields: InvoiceFields) -> list[FieldDifference]:
    """Lines whose quantity x price is not their amount, and lines that don't add up to the total.
    Nothing to check when the invoice lists no lines."""
    if not fields.line_items:
        return []
    cur = fields.currency
    differences = [
        FieldDifference(
            field="line_math",
            invoice={
                "description": line.description,
                "quantity": str(line.quantity),
                "unit_price": str(line.unit_price),
                "amount": str(line.amount),
            },
            po=str(_round(line.quantity * line.unit_price, cur)),
        )
        for line in fields.line_items
        if _round(line.quantity * line.unit_price, cur) != _round(line.amount, cur)
    ]
    lines_total = sum((_round(line.amount, cur) for line in fields.line_items), Decimal(0))
    if lines_total != _round(fields.total_amount, cur):
        differences.append(
            FieldDifference(
                field="line_items_total",
                invoice=fields.amount_minor,
                po=to_minor(lines_total, cur),
            )
        )
    return differences
