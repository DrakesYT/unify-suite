"""Finds text in untrusted documents that is addressed to the AI instead of to a human reader.

Plain code, no model: the result is shown to the person who approves, so they know a document
tried to give orders. The agents never obey such text anyway (see agents/base.py); this makes
the attempt visible.
"""

import re

from app.config import SUSPICIOUS_LINE_MAX_CHARS, SUSPICIOUS_MAX_FINDINGS

_PATTERNS = [
    r"\b(ignore|disregard|forget|override)\b.{0,40}\b(previous|prior|above|earlier|all|your)\b"
    r".{0,20}\b(instructions?|rules?|prompts?)\b",
    r"^\W*(system|assistant|developer)\b[^:\n]{0,30}:",
    r"\b(note|message|instructions?)\s+(to|for)\s+(the\s+)?(ai|assistant|model|llm|agent|bot)\b",
    r"\byou\s+are\s+(now\s+)?(an?\s+)?(\w+\s+){0,3}(ai|assistant|language\s+model|chatbot|bot)\b",
    r"\b(approve|authori[sz]e|release|pay)\b.{0,30}\b(immediately|automatically|without\s+review)\b",
    r"\b(mark|set|flag|treat)\b.{0,40}\bas\s+(matched|approved|paid|verified|safe)\b",
    r"</?\s*document\b",
]
_REGEX = re.compile("|".join(f"(?:{p})" for p in _PATTERNS), re.IGNORECASE | re.MULTILINE)


def find_instruction_text(text: str) -> list[str]:
    """Lines of `text` that look like instructions to an AI (at most 5, each trimmed)."""
    found: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped and _REGEX.search(stripped):
            found.append(stripped[:SUSPICIOUS_LINE_MAX_CHARS])
            if len(found) == SUSPICIOUS_MAX_FINDINGS:
                break
    return found
