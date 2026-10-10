"""Sensitive-content patterns, shared by ingestion (what goes INTO memory), the decision
engine (what gets a reply) and the output guardrail (what the model may SAY).

Why one module: the hard rule "Never discuss money over WhatsApp autonomously" must hold
at all three points. Your real processed_pairs.jsonl had 81 money-related pairs (tax
challan amounts, bank splits, PAN fragments); if those stay in memory, retrieval hands
them to the model as "how I usually reply", and the model learns to discuss money.
"""
import re

MONEY = re.compile(
    r"(₹|\bmoney\b|\bpaisa\w*\b|\bsend \d{3,}\b|\brs\.?\s?\d|\binr\b|\brupees?\b|\bpaise\b|\bpaisa\b|\bpayment\b|\bpay\b|\bpaid\b|\bupi\b|\bgpay\b|\bphonepe\b"
    r"|\bpaytm\b|\bloan\b|\bemi\b|\btransfer\b|\bbank\b|\bsbi\b|\bicici\b|\bhdfc\b|\baxis\b|\bifsc\b|\baccount (no|number)\b"
    r"|\bchallan\b|\btax\b|\bitr\b|\bfees?\b|\brent\b|\bbill\b|\bsalary\b|\brefund\b|\binvoice\b|\bprice\b|\bcost\b"
    r"|\budh?aa?r\b|\bkharcha\b|\blakh\b|\bcrore\b|\bmutual funds?\b|\bstocks?\b|\bholdings?\b|\binvest(ment|ments|ing|ed|or)?\b"
    r"|\bkitne ka\b|\bkitne ki\b|\bkitna (hua|laga|dena|dun|du|bhejna)\b|\$\s?\d"
    r"|\b\d+\s?k\b(?=.*\b(bhej|send|de|chahiye|need|transfer)\b))",
    re.I,
)
SECURITY = re.compile(
    r"\b(otp|password|passcode|atm pin|upi pin|pin (no|number|code)|cvv|verification code|login code|aadhaa?r|pan( card| no| number)?|pan/tan|kyc)\b", re.I
)
SERIOUS = re.compile(
    r"\b(hospital|accident|emergency|urgent|urgently|asap|ambulance|police|passed away|died|death|funeral|icu"
    r"|not well|unwell|bimar|tabiyat|surgery|sad news|bad news|condolence|breakup|divorce|lawyer|legal|court"
    r"|need to talk|call me now|are you (angry|upset|mad)|naraz|gussa|sorry for (your|the) loss"
    r"|sad|upset|crying|depressed|stressed|lonely|hurt|scared|worried|rona|dukhi|pareshan|tension)\b",
    re.I,
)

# PII scrubbing for text that is stored or sent to the model
_PII = [
    (re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.]+\b"), "<email>"),
    (re.compile(r"\b[\w.-]+@(?:ok\w+|ybl|paytm|upi|ibl|axl|apl)\b", re.I), "<upi>"),
    (re.compile(r"https?://\S+|www\.\S+"), "<link>"),
    (re.compile(r"\b[A-Z]{5}\d{4}[A-Z]\b|\b[A-Z]{2}X{3,}\d+[A-Z]?\b"), "<id>"),  # PAN, masked PAN
    (re.compile(r"(?<!\d)(?:\+?\d[\d\s-]{8,}\d)(?!\d)"), "<phone>"),
]


def scrub(text: str) -> str:
    for pat, repl in _PII:
        text = pat.sub(repl, text)
    return text


def is_sensitive(text: str) -> str | None:
    """Return the reason a text is sensitive, or None."""
    if MONEY.search(text):
        return "money"
    if SECURITY.search(text):
        return "security/ID"
    return None
