"""Email quality gate: bot-like phrasing and facts that were not given are caught by code.
Every rule has a sentence it must catch and a normal sentence it must leave alone."""

from datetime import date

import pytest

from app.agents.payment_reminder import PaymentReminderWriter
from app.agents.writing_checks import (
    amounts_in,
    check_writing,
    dates_in,
    fact_problems,
    style_findings,
)
from app.llm import LLMOutputError
from app.llm.fake import FakeLLMClient
from app.schemas.outreach import PaymentReminderInput

FACTS = PaymentReminderInput(
    order_number="SO-1101",
    customer_company="Zahra Boutique",
    amount="450.00 USD",
    ordered_on=date(2026, 9, 28),
    due_on=date(2026, 10, 28),
    days_overdue=10,
    billing_terms="net_30",
    seller_company="UNIFY Demo Corp",
)
GOOD_REMINDER = {
    "subject": "Payment reminder for order SO-1101",
    "body": (
        "Our records show that order SO-1101 for $450.00 was due on October 28, 2026 and is now "
        "10 days overdue.\n\nIt may simply have been missed. Could you arrange the payment, or "
        "reply if anything about the order or the amount looks wrong?"
    ),
}


def _rules(text: str) -> dict[str, str]:
    return {f.rule: f.severity for f in style_findings(text)}


@pytest.mark.parametrize(
    ("text", "rule", "severity"),
    [
        ("I hope this email finds you well. Your order shipped.", "stock opener", "hard"),
        ("Certainly! Here is the update.", "chatbot opener", "hard"),
        ("I hope this helps with your planning.", "chatbot phrase", "hard"),
        ("Our seamless platform connects every team.", "hype word", "hard"),
        ("It is a game-changer for finance teams.", "hype word", "hard"),
        ("Let's circle back after the pilot.", "stock phrase", "hard"),
        ("The rollout went well — the team — liked it.", "em dash", "hard"),
        ("The rollout went well — the team liked it.", "em dash", "soft"),
        ("Please don't hesitate to contact us.", "don't hesitate", "soft"),
        ("We can leverage your existing data.", "leverage", "soft"),
        ("It is not just a tool, it's a partner.", "not just X but Y", "soft"),
        ("We are truly grateful for your order.", "intensifier", "soft"),
        ("Thanks! See you then!", "exclamation marks", "soft"),
    ],
)
def test_each_rule_catches_its_tell(text: str, rule: str, severity: str) -> None:
    assert _rules(text).get(rule) == severity


@pytest.mark.parametrize(
    "text",
    [
        "I hope you can confirm the delivery date by Friday.",  # "I hope" alone is fine
        "Of course, the amount includes tax.",  # "of course" without "!"
        "Our state of the order tracking shows PO-2001 is late.",  # not "state-of-the-art"
        "The two systems are connected without manual steps.",
        "Please reply within two business days.",
        "The invoice was the leverage point in the dispute? No: just a typo, nothing more.",
        'The customer wrote "I hope this email finds you well" in the ticket.',  # quoted
        "The pilot covers one warehouse, not three.",
    ],
)
def test_normal_business_sentences_get_no_hard_finding(text: str) -> None:
    assert "hard" not in _rules(text).values()


def test_money_is_compared_by_value_and_scale() -> None:
    assert amounts_in("$450, 450.00 USD and USD 450") == {amounts_in("$450").pop()}
    assert amounts_in("Rs 12k and 1.2 million dollars") == amounts_in("$12,000 and $1,200,000")


def test_dates_in_any_common_style_are_found() -> None:
    assert dates_in("2026-10-28, October 28, 2026, 28 Oct and Oct. 28th") == {
        (2026, 10, 28),
        (None, 10, 28),
    }
    assert dates_in("May 45") == set()


def test_a_correct_reminder_passes() -> None:
    check_writing(f"{GOOD_REMINDER['subject']}\n{GOOD_REMINDER['body']}", FACTS)


@pytest.mark.parametrize(
    ("change", "problem"),
    [
        (("$450.00", "$4,500.00"), "amount 4,500"),
        (("$450.00", "$450 thousand"), "amount 450,000"),
        (("October 28", "October 30"), "date 10/30/2026"),
        (("10 days overdue", "12 days overdue"), "'12 days late/overdue'"),
        (("order SO-1101 for", "order SO-1110 for"), "reference SO-1110"),
    ],
)
def test_a_changed_fact_is_caught(change: tuple[str, str], problem: str) -> None:
    body = GOOD_REMINDER["body"].replace(*change)
    problems = fact_problems(body, FACTS.model_dump_json())
    assert any(problem in p for p in problems), problems


def test_the_writer_retries_a_wrong_amount_then_saves_the_right_one() -> None:
    wrong = GOOD_REMINDER | {"body": GOOD_REMINDER["body"].replace("$450.00", "$4,500.00")}
    llm = FakeLLMClient(replies=[wrong])
    with pytest.raises(LLMOutputError, match="amount 4,500"):
        PaymentReminderWriter().run(FACTS, llm)

    llm = FakeLLMClient(replies=[GOOD_REMINDER])
    assert PaymentReminderWriter().run(FACTS, llm).subject == GOOD_REMINDER["subject"]
