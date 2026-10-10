#!/usr/bin/env python3
"""Runtime settings, kill switch and allowlist (Session 4.2) -- ONE source of truth.

config/settings.json is read by this module, by the Baileys client and by the console.
Before, the console read config/mode.txt while the bot read settings.json, so the
console could show DRY_RUN while the bot was LIVE (your settings.json had dry_run=false).
"""
from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SETTINGS_PATH = REPO_ROOT / "config" / "settings.json"
RELATIONSHIP_MAP_PATH = REPO_ROOT / "config" / "relationship_map.json"
CONTACT_PROFILES_PATH = REPO_ROOT / "config" / "contact_profiles.json"
KILL_SWITCH_PATH = REPO_ROOT / "kill_switch.flag"
LOGS_DIR = REPO_ROOT / "logs"

DEFAULT_SETTINGS = {
    "dry_run": True,  # fail safe: if the file is missing or broken we never send
    "min_delay_seconds": 3,
    "max_delay_seconds": 12,
    "typing_chars_per_second": 6,
    "short_term_context_messages": 8,
    "retrieval_k": 3,
    "owner_active_window_minutes": 10,
    "max_auto_replies_per_hour": 6,
    "quiet_hours": "23-7",
    "timezone": "Asia/Kolkata",
    "hold_intents": {"professional": ["question"]},
}


def _read_json(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError, TypeError):
        return {}


def load_settings() -> dict:
    raw = _read_json(SETTINGS_PATH)
    if not raw:
        return DEFAULT_SETTINGS.copy()
    return {**DEFAULT_SETTINGS, **raw}


def save_settings(updates: dict) -> dict:
    s = {**load_settings(), **updates}
    SETTINGS_PATH.write_text(json.dumps(s, indent=2) + "\n", encoding="utf-8")
    return s


def is_dry_run() -> bool:
    return bool(load_settings().get("dry_run", True))


def is_kill_switch_active() -> bool:
    return KILL_SWITCH_PATH.exists()


def set_kill_switch(active: bool) -> None:
    if active:
        KILL_SWITCH_PATH.write_text("paused\n", encoding="utf-8")
    else:
        KILL_SWITCH_PATH.unlink(missing_ok=True)


def get_allowlist() -> set[str]:
    rel_map = _read_json(RELATIONSHIP_MAP_PATH)
    return {k for k, v in rel_map.items() if k != "_default" and v not in ("unknown", "group")}


def enforce_allowlist(jid: str) -> bool:
    if not isinstance(jid, str):
        return False
    number = jid.strip().split("@", 1)[0].split(":", 1)[0]
    return bool(number) and number in get_allowlist()


def load_contact_profiles() -> dict:
    return _read_json(CONTACT_PROFILES_PATH)
