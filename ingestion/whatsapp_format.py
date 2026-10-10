"""One WhatsApp export parser shared by persona/build_persona.py and ingestion/parse_export.py.

Handles what the course docs warn about (Session 2.1 Part 2) plus what the real export showed:
  * iOS bracketed  : [10/02/25, 1:30:58 PM] अरूण: text
  * Android dashed : 10/02/25, 1:30 pm - अरूण: text
  * 12h and 24h clocks, narrow no-break spaces before AM/PM
  * leading invisible LRM marks (\u200e) on system/call lines
  * multi-line messages -> continuation lines are appended, never dropped
Dates are kept as strings and never parsed (file order is chronological -- Session 2.1 Part 2.2).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from config.constants import CALL_LOG_LINE, INVISIBLE_CHARS, ONE_WORD_ACKS, SYSTEM_OR_MEDIA_SUBSTRINGS

_INVISIBLE = dict.fromkeys(map(ord, INVISIBLE_CHARS), None)

MESSAGE_START = re.compile(
    r"^(?:\[(?P<b_date>\d{1,4}[/.-]\d{1,2}[/.-]\d{1,4}),\s*(?P<b_time>[^\]]+)\]\s*"
    r"|(?P<p_date>\d{1,4}[/.-]\d{1,2}[/.-]\d{1,4}),?\s+(?P<p_time>\d{1,2}:\d{2}(?::\d{2})?(?:\s?[APap]\.?[Mm]\.?)?)\s*[-–]\s*)"
    r"(?P<sender>[^:]{1,80}?):\s?(?P<text>.*)$"
)
# A dated line WITHOUT "sender:" is a system event ("X added Y") -> boundary, not continuation
SYSTEM_START = re.compile(
    r"^(?:\[\d{1,4}[/.-]\d{1,2}[/.-]\d{1,4},[^\]]+\]|\d{1,4}[/.-]\d{1,2}[/.-]\d{1,4},?\s+\d{1,2}:\d{2}[^-–]*[-–])\s"
)
_NOISE_LOWER = tuple(s.casefold() for s in SYSTEM_OR_MEDIA_SUBSTRINGS)
_CALL = re.compile(CALL_LOG_LINE, re.I)


@dataclass
class Message:
    sender: str
    text: str
    timestamp: str


def clean_line(line: str) -> str:
    return line.translate(_INVISIBLE).replace("\u202f", " ").replace("\u00a0", " ").rstrip("\r\n")


def is_noise_line(text: str) -> bool:
    low = text.translate(_INVISIBLE).casefold().strip()
    return not low or low == "null" or bool(_CALL.match(low)) or any(s in low for s in _NOISE_LOWER)


def strip_noise(text: str) -> str:
    """Remove noise LINES inside a (possibly multi-line) message, keep the real lines."""
    kept = [ln for ln in text.translate(_INVISIBLE).split("\n") if ln.strip() and not is_noise_line(ln)]
    return "\n".join(kept).strip()


def is_ack(text: str) -> bool:
    norm = re.sub(r"[\s.!?,;:]+$", "", text.strip().casefold())
    return norm in ONE_WORD_ACKS


def parse_messages(path: str | Path) -> list[Message]:
    messages: list[Message] = []
    current: Message | None = None
    with Path(path).open(encoding="utf-8-sig", errors="ignore") as fh:
        for raw in fh:
            line = clean_line(raw)
            m = MESSAGE_START.match(line)
            if m:
                if current:
                    messages.append(current)
                date = m.group("b_date") or m.group("p_date")
                time = (m.group("b_time") or m.group("p_time")).strip()
                current = Message(m.group("sender").strip(), m.group("text"), f"{date}, {time}")
            elif SYSTEM_START.match(line):
                if current:
                    messages.append(current)
                current = None
            elif current is not None:
                current.text += "\n" + line
    if current:
        messages.append(current)
    return messages


def sender_counts(messages: list[Message]) -> dict[str, int]:
    out: dict[str, int] = {}
    for m in messages:
        out[m.sender] = out.get(m.sender, 0) + 1
    return dict(sorted(out.items(), key=lambda kv: -kv[1]))
