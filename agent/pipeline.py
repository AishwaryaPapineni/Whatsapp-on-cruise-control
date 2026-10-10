"""The whole live pipeline in one function, one step per box of docs/architecture_diagram.png:

  1 message in -> 2 router -> 3 decision engine -> (short-term context) -> 4 retrieval
  -> 5 persona injection -> 6 generation + guardrail -> 7 human-like delay -> 8 send (Baileys)

Every call returns (and logs to logs/console_feed.jsonl) a full trace, which is what the
Cruise Control Console shows: "why did it say that?" always has a real answer.
"""
from __future__ import annotations

import json
import random
import uuid
from datetime import datetime, timezone

from agent.context import ChatContext
from agent.decision_engine import decide
from agent.generator import generate_with_trace
from agent.router import resolve_contact
from agent.settings import LOGS_DIR, enforce_allowlist, is_dry_run, is_kill_switch_active, load_settings

CONSOLE_FEED_PATH = LOGS_DIR / "console_feed.jsonl"


def human_delay_seconds(reply: str, s: dict, rng=random) -> float:
    """Stage 7: a read pause + typing time for this length + jitter, clamped to the settings range."""
    typing = len(reply) / max(float(s.get("typing_chars_per_second", 6)), 0.1)
    raw = rng.uniform(1.0, 3.0) + typing * rng.uniform(0.85, 1.25)
    return round(min(max(raw, float(s["min_delay_seconds"])), float(s["max_delay_seconds"])), 1)


def process_message(payload: dict, context: ChatContext | None = None, now: datetime | None = None,
                    llm=None, classifier=None, log: bool = True) -> dict:
    s = load_settings()
    context = context or ChatContext()
    jid = str(payload.get("jid", ""))
    text = str(payload.get("text", "") or "")
    trace = {"id": uuid.uuid4().hex[:12], "timestamp": datetime.now(timezone.utc).isoformat(), "jid": jid, "text": text,
             "decision": "ignore", "reply": None, "delay_seconds": 0, "dry_run": is_dry_run(), "sent": False}

    # 1 + 2: message in, router
    contact = resolve_contact(jid)
    trace.update(relationship=contact["relationship"], contact_name=contact["name"], persona=contact["persona"])

    # the real you typed -> remember it (short-term context + "owner active" signal), never reply
    if payload.get("from_me"):
        context.add(jid, "me", text)
        trace.update(reason="own message (recorded as context)", layer="L1 hard rule", checks=[])
        return _finish(trace, log)

    # 3: decision engine (sees context signals before this message is added)
    msg = {"jid": jid, "text": text, "message_type": payload.get("message_type", "text"),
           "is_forwarded": bool(payload.get("is_forwarded")), "from_me": False}
    d = decide(msg, contact["relationship"], context=context, now=now, classifier=classifier, log=log)
    short_term = context.last(jid, int(s["short_term_context_messages"])) if contact["relationship"] not in ("group", "unknown") else []
    if contact["relationship"] not in ("group", "unknown"):
        context.add(jid, "them", text)
    trace.update(reason=d.reason, layer=d.layer, checks=d.checks, intent=d.intent, mode=d.mode)
    if not d.should_reply:
        return _finish(trace, log)

    # 4-6: retrieval, persona injection, generation + guardrail
    try:
        g = generate_with_trace(text, contact, short_term, mode=d.mode, k=int(s["retrieval_k"]), llm=llm)
    except Exception as error:  # noqa: BLE001 -- a crash must never become a sent message
        trace.update(reason=f"{d.reason}; generation error: {error}", decision="ignore")
        return _finish(trace, log)
    trace.update(short_term_context=g["context"], retrieval_trace=g["retrieved"], prompt=g["prompt"],
                 attempts=g["attempts"], model=g["model"], mode=g["mode"], reply=g["reply"],
                 decision="hold" if g["mode"] == "hold" else "reply")

    # 7: human-like delay (the Baileys client actually waits)
    trace["delay_seconds"] = human_delay_seconds(g["reply"], s)
    # independent re-check right before handing a reply to the sender (defence in depth)
    trace["should_send"] = bool(g["reply"]) and enforce_allowlist(jid) and not is_kill_switch_active()
    return _finish(trace, log)


def record_sent(jid: str, reply: str, trace_id: str) -> None:
    """Stage 8 acknowledgement from the Baileys client: feeds context + rate limit + console."""
    ChatContext().add(jid, "agent", reply)
    _append({"id": trace_id, "sent_ack": True, "jid": jid, "timestamp": datetime.now(timezone.utc).isoformat()})


def _finish(trace: dict, log: bool) -> dict:
    if log:
        _append(trace)
    return trace


def _append(row: dict) -> None:
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    with CONSOLE_FEED_PATH.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")
