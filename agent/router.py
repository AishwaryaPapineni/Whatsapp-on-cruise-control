#!/usr/bin/env python3
"""Session 3.1 "Who's texting?" -- pipeline stage 2. A lookup table, no AI.

resolve_relationship(jid) keeps the session's exact contract (and its tests):
    "919812345671@s.whatsapp.net" -> ("family", "history_family")
    "...@g.us"                    -> ("group", None)
    unknown / malformed           -> ("unknown", "history_unknown")

Added:
  * device suffixes ("919812345671:12@s.whatsapp.net") are stripped
  * "@lid" privacy ids never match a phone key -> unknown. The Baileys client resolves
    LIDs to phone numbers BEFORE calling the bridge (Baileys 7 addresses many chats by LID,
    which otherwise makes every known contact look like a stranger).
  * resolve_contact() also returns the persona profile + own conversation_id from
    config/contact_profiles.json, used by retrieval and persona injection.
"""
from __future__ import annotations

import json
from pathlib import Path

PERSONA_KEY_FOR = {"family": "family", "friend": "friends", "professional": "professional", "unknown": "friends"}
DEFAULT_MAP_PATH = str(Path(__file__).resolve().parents[1] / "config" / "relationship_map.json")


def _number(jid: str) -> str:
    return jid.strip().split("@", 1)[0].split(":", 1)[0]


def resolve_relationship(jid: str, map_path: str = DEFAULT_MAP_PATH) -> tuple[str, str | None]:
    if not jid or not isinstance(jid, str) or not jid.strip():
        return ("unknown", "history_unknown")
    normalized = jid.strip()
    if normalized.endswith("@g.us") or normalized == "status@broadcast" or normalized.endswith("@broadcast"):
        return ("group", None)
    if normalized.endswith("@lid") or normalized.endswith("@newsletter"):
        return ("unknown", "history_unknown")
    number = _number(normalized)
    if not number:
        return ("unknown", "history_unknown")
    path = Path(map_path)
    try:
        rel_map = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    except json.JSONDecodeError:
        rel_map = {}  # a broken map must never route a stranger as family
    if not isinstance(rel_map, dict):
        rel_map = {}
    relationship = rel_map.get(number) or rel_map.get("_default", "unknown") or "unknown"
    if relationship == "group":
        return ("group", None)
    if relationship not in ("family", "friend", "professional", "unknown"):
        relationship = "unknown"
    return (relationship, f"history_{relationship}")


def resolve_contact(jid: str, map_path: str = DEFAULT_MAP_PATH, profiles: dict | None = None) -> dict:
    from agent.settings import load_contact_profiles

    relationship, collection = resolve_relationship(jid, map_path)
    profiles = load_contact_profiles() if profiles is None else profiles
    number = _number(jid or "")
    prof = profiles.get(number, {}) if isinstance(profiles.get(number), dict) else {}
    return {
        "jid": jid,
        "number": number,
        "relationship": relationship,
        "collection": collection,
        "name": prof.get("name", number),
        "persona": prof.get("persona", PERSONA_KEY_FOR.get(relationship, "friends")),
        "conversation_id": prof.get("conversation_id"),
        "private_conversations": tuple(profiles.get("_private_conversations", [])),
    }
