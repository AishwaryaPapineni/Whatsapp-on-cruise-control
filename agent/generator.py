#!/usr/bin/env python3
"""Pipeline stages 4-6: retrieval -> persona injection -> generation (+ guardrail).

Prompt = persona brain (identity, this person's tone, measured style, hard rules)
       + short-term context (last N messages of THIS chat)
       + history brain (2-3 most similar past exchanges from the right box)
       + the incoming message and the mode (reply | hold).

Fixes vs the session generator (docs/AUDIT.md):
  * router says "friend" but persona.json says "friends" -> tone was silently empty for
    every friend; now mapped (agent.router.PERSONA_KEY_FOR) or taken from contact_profiles
  * wife gets the "wife" persona even though her chat lives in the family box
  * the bridge retrieved once for the trace and the generator again for the prompt;
    now one retrieval, returned in the trace
  * uses per-relationship measured style instead of the single global average
  * guardrail + one retry + safe fallback; an empty model answer is never sent
"""
from __future__ import annotations

import json
import os
import random
from pathlib import Path

from dotenv import load_dotenv

from agent import guardrail
from agent.context import format_for_prompt
from ingestion.retrieval import retrieve_similar

load_dotenv()
MODEL_NAME = os.getenv("GEMINI_MODEL", "gemini-3.5-flash")
PERSONA_PATH = Path(__file__).resolve().parents[1] / "persona" / "persona.json"
_client = None


def _load_persona() -> dict:
    return json.loads(PERSONA_PATH.read_text(encoding="utf-8"))  # re-read every time: edits apply instantly


def _llm(prompt: str) -> str:
    global _client
    if os.getenv("LLM_PROVIDER", "gemini").lower() == "offline":
        raise RuntimeError("offline")
    from google import genai

    if _client is None:
        _client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
    response = _client.models.generate_content(model=MODEL_NAME, contents=prompt)
    return (response.text or "").strip()


def build_prompt(persona: dict, persona_key: str, incoming: str, retrieved: list[dict], context_rows: list[dict],
                 mode: str = "reply") -> str:
    rel = persona.get("relationships", {}).get(persona_key) or persona.get("relationships", {}).get("friends", {})
    style = rel.get("style", {})
    length = style.get("median_message_length_words") or persona.get("avg_message_length_words", "")
    hinglish = style.get("hinglish_ratio", persona.get("hinglish_ratio", ""))
    emojis = " ".join(style.get("top_emojis", persona.get("top_emojis", []))[:6])
    shots = "\n".join(f"- {r}" for r in rel.get("example_replies", []))
    rules = "\n".join(f"- {r}" for r in persona.get("hard_rules", []))

    parts = [
        "You are texting on WhatsApp AS this person. Reply exactly the way they would. Never sound like an assistant.",
        f"WHO I AM: {persona.get('identity', '')}",
        f"WHO I'M TALKING TO: {persona_key}. My tone with them: {rel.get('tone', 'warm and natural')}",
        f"My measured style with them: Hinglish in about {hinglish if isinstance(hinglish, str) else f'{float(hinglish):.0%}'} of messages, "
        f"typically {length} words, emojis I use: {emojis}",
        f"Real replies I have sent them (copy this voice):\n{shots}",
        f"HARD RULES (never break):\n{rules}",
    ]
    if context_rows:
        parts.append("THE CONVERSATION SO FAR (most recent last):\n" + format_for_prompt(context_rows))
    if retrieved:
        parts.append("Past exchanges that resemble this one -- copy my VOICE, not the facts:\n" + "\n".join(
            f"They: {r['their_message']}\nMe: {r['my_reply']}" for r in retrieved))
    parts.append(f'NEW MESSAGE FROM THEM: "{incoming}"')
    if mode == "hold":
        parts.append("This asks for a plan or commitment that I must confirm myself. Reply in my voice WITHOUT agreeing, "
                     "declining or giving any time/date -- just say I'll check and get back.")
    parts.append("Return only the reply text: one short WhatsApp message, no quotes.")
    return "\n\n".join(parts)


def generate_with_trace(incoming_text: str, contact: dict, context_rows: list[dict] | None = None,
                        mode: str = "reply", k: int = 3, llm=None) -> dict:
    persona = _load_persona()
    persona_key = contact.get("persona", "friends")
    retrieved = retrieve_similar(contact["relationship"], incoming_text, k=k,
                                 conversation_id=contact.get("conversation_id"),
                                 private_conversations=contact.get("private_conversations", ()))
    context_rows = context_rows or []
    prompt = build_prompt(persona, persona_key, incoming_text, retrieved, context_rows, mode)
    holds = persona.get("holding_replies", {}).get(persona_key) or ["Let me check and get back"]
    style = persona.get("relationships", {}).get(persona_key, {}).get("style", {})
    max_words = int(max(20, 4 * (style.get("median_message_length_words") or 6)))
    ctx_text = "\n".join(r["text"] for r in context_rows)
    model = llm or _llm
    if llm is None and os.getenv("LLM_PROVIDER", "gemini").lower() == "offline":
        # deterministic stand-in for demos/tests: reuse my closest real reply (labelled in the trace)
        shots = persona.get("relationships", {}).get(persona_key, {}).get("example_replies", ["😊"])
        model = lambda _p: holds[0] if mode == "hold" else (retrieved[0]["my_reply"] if retrieved else shots[0])  # noqa: E731
    attempts, reply = [], None
    for attempt in range(2):
        try:
            draft = guardrail.clean(model(prompt))
        except Exception as error:  # noqa: BLE001
            attempts.append({"attempt": attempt + 1, "draft": None, "problems": [f"model error: {error}"]})
            break
        problems = guardrail.check(draft, incoming_text, ctx_text, mode, max_words)
        attempts.append({"attempt": attempt + 1, "draft": draft, "problems": problems})
        if not problems:
            reply = draft
            break
        prompt += f"\n\nYour previous draft was rejected because it {'; '.join(problems)}. Rewrite it."
    fallback = reply is None
    if fallback:
        reply = random.choice(holds)
        attempts.append({"attempt": "fallback", "draft": reply, "problems": []})
    return {"reply": reply, "mode": "hold" if (fallback or mode == "hold") else "reply", "persona": persona_key,
            "retrieved": retrieved, "context": context_rows, "prompt": prompt, "attempts": attempts,
            "model": "offline (no LLM)" if os.getenv("LLM_PROVIDER", "").lower() == "offline" else MODEL_NAME,
            "used_fallback": fallback}


def generate_reply(incoming_text: str, relationship: str) -> str:
    """Session-compatible wrapper: generate_reply(text, relationship) -> str."""
    from agent.router import PERSONA_KEY_FOR

    contact = {"relationship": relationship if relationship != "wife" else "family",
               "persona": "wife" if relationship == "wife" else PERSONA_KEY_FOR.get(relationship, "friends")}
    return generate_with_trace(incoming_text, contact)["reply"]


if __name__ == "__main__":
    for text, rel in (("Can we have dinner tonight?", "family"), ("Could you share an update on the project?", "professional"),
                      ("Tumne kha liya khana?", "wife")):
        print(f"[{rel}] {text}\n{generate_reply(text, rel)}\n---")
