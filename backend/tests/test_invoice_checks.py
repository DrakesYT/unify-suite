"""Deterministic invoice checks: the line-item arithmetic and the PO reference are decided by code,
never by the model (the AI only copies what is printed)."""

from collections.abc import Callable
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.invoice_checks import line_item_differences, parse_po_reference
from app.llm.fake import FakeLLMClient
from app.models import InvoiceAnomaly, User
from app.schemas.finance import InvoiceFields
from tests.test_finance import EXTRACTED, _upload, headers, po  # noqa: F401  (fixtures)
from tests.test_workflow_b import _start, people  # noqa: F401  (fixture)

# Two lines that really add up to the 4,250.00 total.
GOOD_LINES = [
    {
        "description": "Steel brackets",
        "quantity": "400",
        "unit_price": "10.00",
        "amount": "4000.00",
    },
    {"description": "Delivery", "quantity": "1", "unit_price": "250.00", "amount": "250.00"},
]
# The demo kit's trick: the stated total equals the PO, but the lines only add up to 4,050.00.
SHORT_LINES = [GOOD_LINES[0], GOOD_LINES[1] | {"unit_price": "50.00", "amount": "50.00"}]


@pytest.mark.parametrize(
    ("raw", "status", "number"),
    [
        ("PO-1007", "clear", "PO-1007"),
        ("po-1007", "clear", "PO-1007"),
        ("PO 1007", "clear", "PO-1007"),
        ("Reference PO#1007", "clear", "PO-1007"),
        ("PO 2001 / maybe 2002", "ambiguous", None),
        ("PO-2001 or PO-2002", "ambiguous", None),
        ("(not provided)", "missing", None),
        ("", "missing", None),
        (None, "missing", None),
    ],
)
def test_po_references_are_cleaned_up_but_never_guessed(
    raw: str | None, status: str, number: str | None
) -> None:
    ref = parse_po_reference(raw)
    assert (ref.status, ref.number) == (status, number)


def test_line_items_that_add_up_pass() -> None:
    fields = InvoiceFields.model_validate(EXTRACTED | {"line_items": GOOD_LINES})
    assert line_item_differences(fields) == []


def test_lines_that_do_not_add_up_to_the_total_are_caught() -> None:
    fields = InvoiceFields.model_validate(EXTRACTED | {"line_items": SHORT_LINES})

    [diff] = line_item_differences(fields)

    assert diff.field == "line_items_total"
    assert (diff.invoice, diff.po) == (425000, 405000)


def test_a_line_whose_quantity_times_price_is_wrong_is_caught() -> None:
    wrong = [GOOD_LINES[0] | {"amount": "4100.00"}, GOOD_LINES[1] | {"amount": "150.00"}]
    fields = InvoiceFields.model_validate(EXTRACTED | {"line_items": wrong})

    diffs = line_item_differences(fields)

    assert [d.field for d in diffs] == ["line_math", "line_math"]  # total 4,250 still adds up
    assert diffs[0].po == str(Decimal("4000.00"))


def test_no_lines_means_nothing_to_check() -> None:
    assert line_item_differences(InvoiceFields.model_validate(EXTRACTED)) == []


def test_an_invoice_whose_lines_do_not_add_up_is_not_matched(
    client: TestClient,
    headers: dict[str, str],  # noqa: F811
    fake_llm: FakeLLMClient,
    po: None,  # noqa: F811
    db: Session,
) -> None:
    fake_llm.replies.append(EXTRACTED | {"line_items": SHORT_LINES})

    body = _upload(client, headers).json()

    assert body["match"]["status"] == "mismatch"
    assert [d["field"] for d in body["match"]["differences"]] == ["line_items_total"]
    assert body["invoice"]["status"] == "needs_review"
    assert [a["kind"] for a in body["anomalies"]] == ["po_mismatch"]


def test_a_lower_case_po_reference_still_matches(
    client: TestClient,
    headers: dict[str, str],  # noqa: F811
    fake_llm: FakeLLMClient,
    po: None,  # noqa: F811
) -> None:
    fake_llm.replies.append(EXTRACTED | {"po_number": "po-1007", "line_items": GOOD_LINES})

    body = _upload(client, headers).json()

    assert body["match"]["status"] == "matched"
    assert body["invoice"]["po_number"] == "PO-1007"


@pytest.mark.parametrize(
    ("printed", "reason"),
    [("PO 1007 / maybe 2002", "ambiguous"), (None, "missing"), ("PO-9999", "not_found")],
)
def test_without_a_clear_known_po_a_person_reviews_it_and_sees_why(
    client: TestClient,
    headers: dict[str, str],  # noqa: F811
    fake_llm: FakeLLMClient,
    po: None,  # noqa: F811
    db: Session,
    printed: str | None,
    reason: str,
) -> None:
    fake_llm.replies.append(EXTRACTED | {"po_number": printed})

    body = _upload(client, headers).json()

    assert body["match"]["status"] == "no_po"
    assert body["invoice"]["status"] == "needs_review"
    anomaly = db.scalar(select(InvoiceAnomaly))
    assert anomaly is not None and anomaly.detail["reason"] == reason


def test_workflow_b_reports_an_invoice_that_names_another_po(
    client: TestClient,
    people: dict[str, dict[str, str]],  # noqa: F811
    fake_llm: FakeLLMClient,
    make_user: Callable[..., User],
) -> None:
    fake_llm.replies.append(EXTRACTED | {"po_number": "PO-2001", "line_items": GOOD_LINES})

    run = _start(client, people["clerk"])

    lines = run["approval"]["payload"]["discrepancies"]
    assert lines == ["the invoice refers to PO-2001, but this run is for PO-1007"]
    assert run["approval"]["payload"]["match_status"] == "mismatch"


def test_workflow_b_explains_line_items_that_do_not_add_up(
    client: TestClient,
    people: dict[str, dict[str, str]],  # noqa: F811
    fake_llm: FakeLLMClient,
) -> None:
    fake_llm.replies.append(EXTRACTED | {"line_items": SHORT_LINES})

    run = _start(client, people["clerk"])

    assert run["approval"]["payload"]["discrepancies"] == [
        "line items add up to 4,050.00 USD, but the total due says 4,250.00 USD"
    ]


@pytest.mark.parametrize("kind", ["credit_note", "quotation", "reminder", "other"])
def test_only_an_invoice_can_be_paid(
    client: TestClient,
    headers: dict[str, str],  # noqa: F811
    fake_llm: FakeLLMClient,
    po: None,  # noqa: F811
    db: Session,
    kind: str,
) -> None:
    fake_llm.replies.append(EXTRACTED | {"document_type": kind, "line_items": GOOD_LINES})

    body = _upload(client, headers).json()

    assert body["invoice"] is None  # never saved as something to pay
    assert [a["kind"] for a in body["anomalies"]] == ["not_an_invoice"]
    anomaly = db.scalar(select(InvoiceAnomaly))
    assert anomaly is not None and anomaly.detail["document_type"] == kind


def test_workflow_b_stops_a_quotation_before_any_approval(
    client: TestClient,
    people: dict[str, dict[str, str]],  # noqa: F811
    fake_llm: FakeLLMClient,
) -> None:
    fake_llm.replies.append(EXTRACTED | {"document_type": "quotation"})

    run = _start(client, people["clerk"])

    f2 = next(s for s in run["steps"] if s["key"] == "F2")
    assert f2["status"] == "failed"
    assert "is a quotation, not an invoice, so there is nothing to pay" in f2["error"]
    assert run["approval"] is None


@pytest.mark.parametrize(
    ("document_type", "total"), [("credit_note", "-4250.00"), ("invoice", "-10.00")]
)
def test_a_negative_total_is_never_payable(
    client: TestClient,
    headers: dict[str, str],  # noqa: F811
    fake_llm: FakeLLMClient,
    po: None,  # noqa: F811
    db: Session,
    document_type: str,
    total: str,
) -> None:
    fake_llm.replies.append(EXTRACTED | {"document_type": document_type, "total_amount": total})

    body = _upload(client, headers).json()

    assert body["invoice"] is None
    assert [a["kind"] for a in body["anomalies"]] == ["not_an_invoice"]


def test_a_discount_line_may_be_negative_and_still_add_up() -> None:
    lines = [*GOOD_LINES, {"description": "Loyalty discount", "quantity": "1",
                           "unit_price": "-50.00", "amount": "-50.00"}]  # fmt: skip
    fields = InvoiceFields.model_validate(
        EXTRACTED | {"total_amount": "4200.00", "line_items": lines}
    )
    assert line_item_differences(fields) == []
