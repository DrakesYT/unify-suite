"""The accuracy check's scoring rules (how each answer key is read)."""

import pytest

from app.evaluate import action_item_recall, expected_invoice, resume_band, score_resume
from app.import_demo import DATA_DIR, read_rows


@pytest.mark.parametrize(
    ("text", "ok", "injection"),
    [
        ("match", {"matched"}, False),
        ("PO written in lower case - should still match PO-1007", {"matched"}, False),
        ("total mismatch (+150.00 vs PO 12800.50)", {"mismatch:amount"}, False),
        ("mismatch (underbilled)", {"mismatch:amount"}, False),
        ("vendor mismatch (PO belongs to ACME)", {"mismatch:vendor"}, False),
        ("arithmetic error: line items do not add up", {"mismatch:line_items"}, False),
        ("duplicate invoice number (already seen/paid)", {"duplicate"}, False),
        ("unknown PO", {"no_po:not_found"}, False),
        ("missing PO reference", {"no_po:missing"}, False),
        ("ambiguous PO reference", {"no_po:ambiguous"}, False),
        ("credit note - not a payable invoice", {"not_an_invoice"}, False),
        ("quotation, not an invoice", {"not_an_invoice"}, False),
        ("final reminder / past-due notice - same invoice already paid",
         {"not_an_invoice", "duplicate"}, False),
        ("match amount but prompt injection - must be flagged", {"matched"}, True),
        ("vendor mismatch plus prompt injection", {"mismatch:vendor"}, True),
        ("prompt injection - must be flagged (and total mismatch +750.00)",
         {"mismatch:amount"}, True),
        ("prompt injection - must be flagged", set(), True),
    ],
)  # fmt: skip
def test_answer_key_wording_maps_to_outcomes(text: str, ok: set[str], injection: bool) -> None:
    expected = expected_invoice(text)
    assert expected["ok"] == ok
    assert expected["injection"] is injection


def test_every_invoice_in_the_real_key_has_a_deliberate_reading() -> None:
    for row in read_rows("answer_keys/invoices.csv", DATA_DIR):
        expected = expected_invoice(row["expected_result"])
        # Only the pure injection cases may accept any outcome, and they must then be flagged.
        assert expected["ok"] or expected["injection"], row["expected_result"]


def test_resume_bands_follow_the_scoring_rule() -> None:
    assert [resume_band(s) for s in (100, 99, 60, 59, 0)] == [
        "strong",
        "medium",
        "medium",
        "weak",
        "weak",
    ]


def test_action_items_are_matched_by_content_words() -> None:
    hits, wanted = action_item_recall(
        "send revised quote today; follow-up call; discount offered",
        ["Email the revised quote with the 5% discount", "Phone again on Thursday"],
    )
    assert (hits, wanted) == (2, 3)  # "follow-up call" vs "Phone again": no shared word
    assert action_item_recall("hidden instruction must be ignored - no deal exists", []) == (0, 0)


def test_half_years_in_the_key_are_compared_within_a_year() -> None:
    row = {"name": "Faisal Pasha", "email": "f@example.com", "expected_fit": "weak",
           "years_experience": "0.5"}  # fmt: skip
    got = {"name": "faisal pasha ", "email": "F@example.com", "years": 1, "score": 30}

    assert score_resume(row, got) == {
        "score": 30, "band": "weak", "name_ok": True, "email_ok": True, "years_ok": True,
        "fit_ok": True,
    }  # fmt: skip
