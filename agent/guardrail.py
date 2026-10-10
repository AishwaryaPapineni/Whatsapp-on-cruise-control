"""Output guardrail -- the last check between the model and a real person's phone.

The decision engine guards what comes IN; this guards what goes OUT. Your Week 1
sample outputs show why it's needed: the model promised a pickup ("main lene aa jaunga!"),
invented "Flight tickets booked, coming home on 10th Nov" and proposed "4 PM today".
On a violation the generator retries once with the reason, then falls back to a safe
holding reply from persona.json.
"""
from __future__ import annotations

import re

from config.sensitive import MONEY, SECURITY

MONTHS = r"(jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*"
TIME_OR_DATE = re.compile(
    rf"(\b\d{{1,2}}(:\d{{2}})?\s?(am|pm)\b|\b\d{{1,2}}:\d{{2}}\b|\b\d{{1,2}}(st|nd|rd|th)?\s+{MONTHS}\b|\b{MONTHS}\s+\d{{1,2}}\b"
    r"|\b(today|tonight|tomorrow|kal|parso|this weekend|next week|monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b)",
    re.I,
)
COMMITMENT = re.compile(
    r"(\b(i'?ll|i will|i'?m|i am)\s+(definitely\s+)?(come|coming|be there|pick|drop|join|reach|bring)\b"
    r"|\bsee you (at|tomorrow|tonight|then|there)\b|\b(booked|confirmed|done deal|it'?s a date)\b"
    r"|\blet'?s (connect|meet|do it|go) (at|on|today|tomorrow|tonight)\b"
    r"|\b(aa jaunga|aa jaungi|aa jayenge|aaunga|aa raha hu|aa rha hu|lene aa|le aaunga|le jaunga|pakka|chalenge|milte hai)\b"
    r"|\b(yes|haan|ha|sure|ok|bilkul)\b[^.?!]{0,25}\b(come|aa|pick|lene|join|chalo|aaunga)\b)",
    re.I,
)
AI_TELL = re.compile(r"(as an ai|language model|i'?m an ai|i am an ai|chatbot|\bAI assistant\b|persona|retrieved)", re.I)


def check(reply: str, incoming: str, context_text: str, mode: str, max_words: int) -> list[str]:
    problems = []
    if not reply.strip():
        return ["empty reply"]
    if MONEY.search(reply):
        problems.append("mentions money")
    if SECURITY.search(reply):
        problems.append("mentions OTP/password/ID")
    if AI_TELL.search(reply):
        problems.append("sounds like an AI / leaks the prompt")
    if COMMITMENT.search(reply):
        problems.append("commits to a plan")
    known = (incoming + "\n" + context_text).lower()
    for m in TIME_OR_DATE.finditer(reply):
        if m.group(0).lower() not in known:  # a time/date nobody mentioned = invented fact
            problems.append(f"invents a time/date ('{m.group(0)}')")
            break
    if len(reply.split()) > max_words:
        problems.append(f"too long (> {max_words} words)")
    return problems


def clean(reply: str) -> str:
    r = (reply or "").strip()
    r = re.sub(r"^(reply|me|arun|अरूण|response)\s*:\s*", "", r, flags=re.I)
    if len(r) >= 2 and r[0] in "\"'“" and r[-1] in "\"'”":
        r = r[1:-1].strip()
    return r.split("\n\n")[0].strip()
