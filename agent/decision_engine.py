#!/usr/bin/env python3
"""Session 3.2 "Reply or ignore?" -- pipeline stage 3. Cheap rules first, one AI call last.

Layers (the guide's order: hard rules -> signal rules -> intent check -> reply policy):
  L1 hard rules   kill switch · own message · group · not in allowlist · media-only ·
                  forwarded · MONEY · OTP/ID · serious topics            -> leave for you
  L2 signal rules one-word ack / emoji-only · you typed here recently ·
                  rate limit · quiet hours                                -> stay silent
  L3 intent check regex: plan/commitment -> HOLD · greeting/check-in/celebration/
                  thanks/share -> safe (no AI call needed) · else unclear
  L4 AI check     ONE Gemini classification, only when L3 is unclear; fails CLOSED
  L5 reply policy settings.json "hold_intents" (e.g. professional questions -> HOLD)

Modes for a positive decision:
  reply -> normal in-character reply
  hold  -> in-character but NON-committal ("let me check and get back").
           Your session log shows "Are you free for dinner tonight?" -> reply, "passed all
           gates": the model would have said yes and broken "Never confirm plans without me".

`should_reply(message, relationship) -> (bool, reason)` is unchanged, so batch_test.py and
the bridge keep working; `decide()` returns the full Decision used by the console.
"""
from __future__ import annotations

import json
import os
import re
import string
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

from agent.context import ChatContext
from agent.settings import LOGS_DIR, is_kill_switch_active, load_settings
from config.constants import ONE_WORD_ACKS
from config.sensitive import MONEY, SECURITY, SERIOUS

load_dotenv()
MODEL_NAME = os.getenv("GEMINI_MODEL", "gemini-3.5-flash")
DECISION_LOG_PATH = LOGS_DIR / "decision_log.jsonl"
LABELS = {"safe_to_auto_reply", "needs_human_money_or_serious", "plan_or_commitment"}

PLAN = re.compile(
    r"(\b(can|could|will|would) (you|u|we)\b.*\b(come|pick|meet|join|call|drop|send|make it|connect|sync|book|bring|attend|go|have)\b"
    r"|\bare (you|u) (coming|free|available|joining|around)\b|\b(r u|ru) free\b|\bfree (tonight|tomorrow|today|this)\b"
    r"|\blet'?s (meet|go|catch up|connect|plan|do|grab|have|sync)\b|\bwhen can we\b|\bshall we\b|\bwant to (catch|go|meet|grab)\b"
    r"|\bpick me up\b|\bdrop me\b|\bsee (you|u)\b|\bmeet (up|tomorrow|today|tonight|at)\b"
    r"|\b(lunch|dinner|movie|party|trip) (plan|tonight|tomorrow|kal)\b|\bat \d{1,2}(:\d{2})? ?(am|pm)\b"
    r"|\b(confirm|reschedule|rsvp)\b|\bbook (the|a|tickets?)\b"
    r"|\baaoge\b|\baaogi\b|\baa rahe\b|\baa rahi\b|\bchaloge\b|\bchalogi\b|\bchalein\b|\bmilte\b|\bmilna\b|\bmiloge\b"
    r"|\bkab aa|\blene aa|\ble aana\b|\bchhod (do|dena)\b|\bplan (hai|banao|kya)\b|\bfree ho\b|\bfree hai\b)",
    re.I,
)
SAFE_INTENTS = [
    ("celebration", re.compile(r"(congrat|happy (birthday|anniversary|diwali|holi|new year|journey)|\bcleared\b|\bpromot|\bpassed\b|🎉|🥳|🎂)", re.I)),
    ("thanks", re.compile(r"(\bthanks? (for|a lot|so)\b|\bthank you (for|so)\b|\bloved\b|\bgreat (job|work)\b|\bwell done\b|\bshukriya\b)", re.I)),
    ("checkin", re.compile(r"(\bkaha(n)? ho\b|\bkya kar rahe?\b|\bkya kar rahi\b|\bkhana kha|\bkha liya\b|\bkhaya\b|\breached\b|\bpahuch|\bpahunch"
                           r"|\bhow are you\b|\bkaise ho\b|\bwhat'?s up\b|\bkya haal\b|\buth gaye\b|\bso gaye\b|\bslept\b|\bhow was\b|\bkaisa (raha|tha)\b)", re.I)),
    ("greeting", re.compile(r"^\W*(hi+|hello+|hey+|namaste|good (morning|night|evening|afternoon)|gm|gn)\b", re.I)),
    ("share", re.compile(r"(\bsending\b|\buploaded\b|\bcheck (this|out)\b|\bsee this\b|\bdekh(o|a)?\b|\bpics?\b|\bphotos?\b|\bvideo\b|\bnews\b|\ble liya\b|\bgot (a|my|the) new\b)", re.I)),
]
QUESTION = re.compile(r"(\?\s*$|^\s*(kya|kaise|kab|kahan|kaun|kyu|kyun|how|what|where|when|why|who|did|do|are|is|can|should)\b)", re.I)
EMOJI_ONLY = re.compile(r"^[\W\d_\s]+$", re.UNICODE)


@dataclass
class Decision:
    should_reply: bool
    reason: str
    layer: str
    mode: str = "reply"  # reply | hold
    intent: str | None = None
    checks: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def _log_decision(text: str, relationship: str, d: Decision, raw_response: str | None = None) -> None:
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    entry = {"timestamp": datetime.now(timezone.utc).isoformat(), "message": text, "relationship": relationship,
             "decision": ("hold" if d.mode == "hold" else "reply") if d.should_reply else "ignore",
             "reason": d.reason, "layer": d.layer}
    if raw_response is not None:
        entry["raw_response"] = raw_response
    with DECISION_LOG_PATH.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _classify_with_llm(text: str) -> tuple[str, str | None]:
    """The ONE AI call. Any error, quota or unexpected answer -> fail closed."""
    if os.getenv("LLM_PROVIDER", "gemini").lower() == "offline":
        return "needs_human_money_or_serious", "offline mode: no classifier"
    try:
        from google import genai

        client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
        prompt = (
            "Classify this incoming WhatsApp message with exactly one label:\n"
            "safe_to_auto_reply - casual chat a friend could answer for me\n"
            "plan_or_commitment - asks me to meet, come, pick up, schedule, agree to or decide something\n"
            "needs_human_money_or_serious - money, payments, medical, legal, serious personal matters, or genuinely ambiguous\n"
            "Return only the label.\n\n"
            f"Message: {text}"
        )
        response = client.models.generate_content(model=MODEL_NAME, contents=prompt)
        raw = (response.text or "").strip()
    except Exception as error:  # noqa: BLE001 -- 503s and quota errors seen in the session log
        return "needs_human_money_or_serious", f"LLM error: {error}"
    label = raw.strip().strip("`'\". ").lower()
    return (label, None) if label in LABELS else ("needs_human_money_or_serious", raw)


def _in_quiet_hours(now: datetime, spec: str) -> bool:
    if not spec:
        return False
    start, end = (int(x) for x in spec.split("-"))
    return (now.hour >= start or now.hour < end) if start > end else (start <= now.hour < end)


def decide(message: dict, relationship: str, context: ChatContext | None = None, now: datetime | None = None,
           classifier=None, log: bool = True) -> Decision:
    s = load_settings()
    context = context or ChatContext()
    tz = ZoneInfo(s.get("timezone", "Asia/Kolkata"))
    now = now or datetime.now(tz)
    jid = message.get("jid", "")
    text = message.get("text", "") if isinstance(message.get("text"), str) else ""
    checks: list[dict] = []
    raw_response = None

    def done(ok: bool, reason: str, layer: str, mode: str = "reply", intent: str | None = None) -> Decision:
        checks.append({"layer": layer, "result": ("hold" if mode == "hold" else "reply") if ok else "ignore", "reason": reason})
        d = Decision(ok, reason, layer, mode, intent, checks)
        if log:
            _log_decision(text, relationship, d, raw_response)
        return d

    def passed(layer: str) -> None:
        checks.append({"layer": layer, "result": "pass", "reason": "no rule triggered"})

    # ---- L1 hard rules ---------------------------------------------------
    if is_kill_switch_active():
        return done(False, "kill switch active", "L1 hard rule")
    if message.get("from_me") is True:
        return done(False, "own message", "L1 hard rule")
    if relationship == "group":
        return done(False, "group chat, not allowlisted", "L1 hard rule")
    if relationship == "unknown":
        return done(False, "sender not in allowlist", "L1 hard rule")
    if message.get("message_type", "text") in ("image", "audio", "video", "sticker", "document", "other") and not text.strip():
        return done(False, "media-only, no text to ground a reply", "L1 hard rule")
    if message.get("is_forwarded") is True:
        return done(False, "forwarded content, not a real question", "L1 hard rule")
    if not text.strip():
        return done(False, "empty message", "L1 hard rule")
    if MONEY.search(text):
        return done(False, "money -- hard rule: never discuss money autonomously", "L1 hard rule", intent="money")
    if SECURITY.search(text):
        return done(False, "OTP / password / ID -- never handled automatically", "L1 hard rule", intent="security")
    if SERIOUS.search(text):
        return done(False, "serious / emotional topic -- needs the real you", "L1 hard rule", intent="serious")
    passed("L1 hard rule")

    # ---- L2 signal rules -------------------------------------------------
    normalized = text.strip().lower().translate(str.maketrans("", "", string.punctuation)).strip()
    if normalized in ONE_WORD_ACKS or (EMOJI_ONLY.match(text) and len(text.strip()) <= 8):
        return done(False, "low-signal ack, no reply needed", "L2 signal rule", intent="ack")
    mins = context.minutes_since_owner(jid, now) if jid else None
    if mins is not None and mins < s["owner_active_window_minutes"]:
        return done(False, f"you typed in this chat {mins:.0f} min ago -- the real you is here", "L2 signal rule")
    if jid and context.auto_replies_last_hour(jid, now) >= s["max_auto_replies_per_hour"]:
        return done(False, f"rate limit: {s['max_auto_replies_per_hour']} auto-replies in the last hour", "L2 signal rule")
    if _in_quiet_hours(now, s.get("quiet_hours", "")):
        return done(False, f"quiet hours ({s['quiet_hours']})", "L2 signal rule")
    passed("L2 signal rule")

    # ---- L3 intent check (regex, free) ------------------------------------
    intent = None
    if PLAN.search(text):
        intent = "plan"
    else:
        for name, pat in SAFE_INTENTS:
            if pat.search(text):
                intent = name
                break
        if intent is None and QUESTION.search(text):
            intent = "question"
    checks.append({"layer": "L3 intent check", "result": intent or "unclear", "reason": "regex/keywords"})

    # ---- L4 one AI call, only if unclear ------------------------------------
    if intent in (None, "question"):
        label, raw_response = (classifier or _classify_with_llm)(text)
        checks.append({"layer": "L4 AI check", "result": label, "reason": raw_response or f"model={MODEL_NAME}"})
        if label == "needs_human_money_or_serious":
            reason = "intent check failed closed" if raw_response else "needs human review: money or serious/ambiguous intent"
            return done(False, reason, "L4 AI check", intent=intent or "unclear")
        if label == "plan_or_commitment":
            intent = "plan"
        intent = intent or "chat"

    # ---- L5 reply policy -----------------------------------------------------
    if intent == "plan":
        return done(True, "plan/commitment -> non-committal holding reply (hard rule: never confirm plans without me)",
                    "L5 reply policy", mode="hold", intent=intent)
    if intent in s.get("hold_intents", {}).get(relationship, []):
        return done(True, f"{relationship} {intent} -> holding reply (policy)", "L5 reply policy", mode="hold", intent=intent)
    return done(True, "passed all gates", "L5 reply policy", intent=intent)


def should_reply(message: dict, relationship: str) -> tuple[bool, str]:
    d = decide(message, relationship)
    return d.should_reply, d.reason
