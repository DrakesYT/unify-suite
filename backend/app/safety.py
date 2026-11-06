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
    # Addressed to the AI ("P.S. for the assistant", "dear model"). Not "agent": call transcripts
    # name their human speakers "Agent".
    r"\b(for|to|dear|hey|attention)\s+(the\s+)?(ai|assistant|model|llm|chatbot|bot"
    r"|automated\s+(system|reviewer)|screening\s+system)\b",
    # Role tags in brackets: "[system]", "[assistant instruction]", "<ai>".
    r"[\[<(]\s*(system|assistant|ai|developer)\b[^\]>)\n]{0,30}[\]>)]",
    r"\b(just|simply)\s+(approve|pay|accept|sign\s+off)\b",
    r"\byou\s+are\s+(now\s+)?(an?\s+)?(\w+\s+){0,3}(ai|assistant|language\s+model|chatbot|bot)\b",
    r"\b(approve|authori[sz]e|release)\b.{0,30}\b(immediately|automatically|without\s+review)\b",
    # "Pay immediately" alone is ordinary wording in a reminder to a person; only an automatic or
    # unreviewed payment is an order to software.
    r"\bpay\b.{0,30}\b(automatically|without\s+review)\b",
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
