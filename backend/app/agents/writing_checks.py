"""Checks on text an agent writes for people outside the company (emails, ticket replies).

Two plain-code gates, run on every draft before it is saved:

- Style: phrases that make an email read like a bot ("I hope this email finds you well",
  "seamless", "circle back", a run of em dashes). A *hard* finding makes the draft invalid, so the
  runner retries; a *soft* one is shown to the person reviewing the draft as a suggestion.
- Facts: every amount, reference (PO-2001, SO-1101, INV-202611-077), date and "N days late"
  in the draft must match the facts code gave the writer. $450.00 may be written as "$450" or
  "450.00 USD", but never as $4,500, and a due date cannot move.

Quoted text ("...") is skipped by the style gate, so a reply may quote the customer's own words.
"""

import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Literal

from pydantic import BaseModel

from app.llm import LLMOutputError

Severity = Literal["hard", "soft"]


@dataclass(frozen=True)
class StyleRule:
    name: str
    severity: Severity
    pattern: re.Pattern[str]
    advice: str


def _rule(name: str, severity: Severity, pattern: str, advice: str) -> StyleRule:
    return StyleRule(name, severity, re.compile(pattern, re.IGNORECASE | re.MULTILINE), advice)


RULES: tuple[StyleRule, ...] = (
    # Chatbot residue: never right in a business email.
    _rule(
        "stock opener",
        "hard",
        r"\bI hope (?:this|my|the) (?:e-?mail|message|note|letter) finds you\b",
        "Start with the reason you are writing.",
    ),
    _rule(
        "chatbot phrase",
        "hard",
        r"\b(?:I hope this (?:helps|clarifies)|as an AI\b|great question|happy to help!)",
        "Remove it; it reads like a chatbot.",
    ),
    _rule(
        "chatbot opener",
        "hard",
        r"^\s*(?:certainly|absolutely|of course|sure)!",
        "Start with the point.",
    ),
    # Hype and buzzwords.
    _rule(
        "hype word",
        "hard",
        r"\b(?:game[- ]chang\w*|cutting[- ]edge|seamless(?:ly)?|revolutioni[sz]\w*|world[- ]class"
        r"|best[- ]in[- ]class|state[- ]of[- ]the[- ]art|synerg\w*|unlock(?:s|ing)? (?:the |your )?"
        r"(?:full )?potential)\b",
        "Say what it does, with a fact.",
    ),
    _rule(
        "stock phrase",
        "hard",
        r"\b(?:let'?s dive in|deep[- ]dive|circle back|move the needle|low[- ]hanging fruit"
        r"|in today'?s (?:fast[- ]paced|digital|ever[- ]changing) (?:world|landscape|market))\b",
        "Use plain words.",
    ),
    # Softer tells: the reviewer decides.
    _rule(
        "don't hesitate",
        "soft",
        r"\b(?:please )?(?:don'?t|do not) hesitate to\b",
        "Ask directly, e.g. “Reply to this email if anything is unclear.”",
    ),
    _rule("leverage", "soft", r"\bleverag(?:e|es|ing)\b", "Try “use”."),
    _rule("touch base", "soft", r"\btouch base\b", "Try “talk” or “check in”."),
    _rule("rest assured", "soft", r"\brest assured\b", "State the fact that should reassure them."),
    _rule(
        "not just X but Y",
        "soft",
        r"\bnot (?:just|only|merely)\b[^.!?\n]{1,60}\b(?:but|it'?s)\b",
        "Say the main point once, plainly.",
    ),
    _rule(
        "intensifier",
        "soft",
        r"\b(?:incredibly|truly|extremely|absolutely)\b",
        "Usually adds nothing; try deleting it.",
    ),
)

EM_DASH = "—"
HARD_EM_DASHES = 2  # two or more em dashes in one email: a strong machine-writing tell
_QUOTED = re.compile(r"\"[^\"\n]{1,300}\"|“[^”\n]{1,300}”")


@dataclass(frozen=True)
class Finding:
    rule: str
    severity: Severity
    text: str
    advice: str


def style_findings(text: str) -> list[Finding]:
    """Every style tell in `text`, quoted spans excluded. Deterministic, no model."""
    plain = _QUOTED.sub(lambda m: " " * len(m.group(0)), text)
    found: list[Finding] = []
    for rule in RULES:
        for match in rule.pattern.finditer(plain):
            found.append(Finding(rule.name, rule.severity, match.group(0).strip(), rule.advice))
    dashes = plain.count(EM_DASH)
    if dashes:
        found.append(
            Finding(
                "em dash",
                "hard" if dashes >= HARD_EM_DASHES else "soft",
                EM_DASH * min(dashes, 3),
                "Use a comma, a colon or a full stop instead.",
            )
        )
    if plain.count("!") >= 2:
        found.append(
            Finding("exclamation marks", "soft", "!", "One is plenty in a business email.")
        )
    return found


# --- facts --------------------------------------------------------------------------------

_MULTIPLIER = {"k": 1_000, "thousand": 1_000, "m": 1_000_000, "million": 1_000_000,
               "bn": 1_000_000_000, "billion": 1_000_000_000}  # fmt: skip
_NUMBER = r"\d[\d,]*(?:\.\d+)?"
_SCALE = r"(?:k|m|bn|thousand|million|billion)\b"
_CODES = r"(?:USD|PKR|EUR|GBP|AED)"
# "$4,250", "USD 4,250.00", "Rs 12k" ...
_MONEY_BEFORE = re.compile(
    rf"(?:{_CODES}|Rs\.?|\$|€|£)\s?({_NUMBER})(?:\s?({_SCALE}))?", re.IGNORECASE
)
# ... and "4,250.00 USD", "1.2 million dollars"
_MONEY_AFTER = re.compile(
    rf"({_NUMBER})(?:\s?({_SCALE}))?\s?(?:{_CODES}|dollars|rupees)\b", re.IGNORECASE
)
_REFERENCE = re.compile(r"\b[A-Z]{2,5}-\d{2,}(?:-\d+)*\b")
_DAYS = re.compile(r"\b(\d{1,4})\s+days?\s+(?:late|overdue|past due|behind)\b", re.IGNORECASE)
_MONTH_NAMES = ("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec")
_MONTHS = {m: i + 1 for i, m in enumerate(_MONTH_NAMES)}
_MONTH = (
    r"(?P<{0}>jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?"
    r"|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"
)
_DATES = re.compile(
    r"\b(?P<iy>\d{4})-(?P<im>\d{2})-(?P<id>\d{2})\b"
    rf"|\b{_MONTH.format('m1')}\.?\s+(?P<d1>\d{{1,2}})(?:st|nd|rd|th)?(?:,?\s+(?P<y1>\d{{4}}))?\b"
    rf"|\b(?P<d2>\d{{1,2}})(?:st|nd|rd|th)?\s+(?:of\s+)?{_MONTH.format('m2')}\.?(?:,?\s+(?P<y2>\d{{4}}))?\b",
    re.IGNORECASE,
)


def _decimal(raw: str) -> Decimal | None:
    try:
        return Decimal(raw.replace(",", "")).normalize()
    except InvalidOperation:
        return None


def amounts_in(text: str) -> set[Decimal]:
    """Money mentions: "$4,250", "4,250.00 USD", "Rs 12k" → their values (scale applied)."""
    found = set()
    matches = [*_MONEY_BEFORE.finditer(text), *_MONEY_AFTER.finditer(text)]
    for m in matches:
        raw, scale = m.group(1), m.group(2)
        value = _decimal(raw)
        if value is not None:
            multiplier = _MULTIPLIER.get((scale or "").strip().lower(), 1)
            found.add((value * multiplier).normalize())
    return found


def dates_in(text: str) -> set[tuple[int | None, int, int]]:
    """(year or None, month, day) for ISO dates and "October 28, 2026" / "28 Oct" styles."""
    found: set[tuple[int | None, int, int]] = set()
    for m in _DATES.finditer(text):
        if m.group("iy"):
            year, month, day = int(m.group("iy")), int(m.group("im")), int(m.group("id"))
        else:
            name, day_s, year_s = (
                (m.group("m1"), m.group("d1"), m.group("y1"))
                if m.group("m1")
                else (m.group("m2"), m.group("d2"), m.group("y2"))
            )
            month, day, year = (
                _MONTHS[name[:3].lower()],
                int(day_s),
                int(year_s) if year_s else None,
            )
        try:
            date(year or 2000, month, day)
        except ValueError:
            continue  # "May 45" is not a date
        found.add((year, month, day))
    return found


def fact_problems(text: str, facts: str) -> list[str]:
    """What the draft states that the facts do not support (empty when everything matches)."""
    problems = []
    for value in sorted(amounts_in(text) - amounts_in(facts)):
        problems.append(f"the amount {value:,f} is not in the facts")
    known_refs = {r.upper() for r in _REFERENCE.findall(facts)}
    for ref in sorted({r.upper() for r in _REFERENCE.findall(text)} - known_refs):
        problems.append(f"the reference {ref} is not in the facts")
    known_dates = dates_in(facts)
    for year, month, day in sorted(dates_in(text), key=lambda d: (d[0] or 0, d[1], d[2])):
        if not any(m == month and d == day and (year is None or y in (None, year))
                   for y, m, d in known_dates):  # fmt: skip
            problems.append(
                f"the date {month}/{day}{f'/{year}' if year else ''} is not in the facts"
            )
    numbers = {int(n) for n in re.findall(r"\b\d{1,4}\b", facts)}
    for days in sorted({int(d) for d in _DAYS.findall(text)} - numbers):
        problems.append(f"'{days} days late/overdue' is not in the facts")
    return problems


def check_style(text: str) -> None:
    """Any hard style finding makes the draft invalid (the runner retries it)."""
    hard = [f for f in style_findings(text) if f.severity == "hard"]
    if hard:
        raise LLMOutputError(f"draft uses a {hard[0].rule}: {hard[0].text!r}")


def check_writing(text: str, facts: BaseModel | str) -> None:
    """Gate for agent drafts: any hard style finding or unsupported fact makes the draft invalid
    (the runner retries it). Soft findings pass; they are shown to the reviewer instead."""
    check_style(text)
    facts_text = facts if isinstance(facts, str) else facts.model_dump_json()
    problems = fact_problems(text, facts_text)
    if problems:
        raise LLMOutputError(f"draft states facts it was not given: {problems[0]}")
