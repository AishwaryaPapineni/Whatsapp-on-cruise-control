#!/usr/bin/env python3
"""Validate that every processed conversation has a classified relationship."""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


PAIRS_PATH = ROOT / "data" / "processed_pairs.jsonl"
MAP_PATH = ROOT / "config" / "contact_relationship_map.json"
PLACEHOLDER = "REPLACE_ME"
VALID = {"family", "friend", "professional", "unknown"}


def load_conversation_ids() -> list[str]:
    conversation_ids: set[str] = set()
    with PAIRS_PATH.open(encoding="utf-8") as pairs_file:
        for line in pairs_file:
            if line.strip():
                conversation_ids.add(json.loads(line)["conversation_id"])
    return sorted(conversation_ids)


def main() -> int:
    conversation_ids = load_conversation_ids()
    try:
        with MAP_PATH.open(encoding="utf-8") as map_file:
            relationship_map = json.load(map_file)
    except FileNotFoundError:
        print(f"ERROR: relationship map not found: {MAP_PATH}", file=sys.stderr)
        return 1

    missing = [
        conversation_id
        for conversation_id in conversation_ids
        if relationship_map.get(conversation_id) in (None, PLACEHOLDER)
    ]
    # typo guard: "friends"/"work" would silently fall back to history_unknown at embed time
    invalid = sorted(f"{k}={v!r}" for k, v in relationship_map.items() if v not in VALID and v != PLACEHOLDER)
    if invalid:
        print(f"Invalid relationship values (must be one of {sorted(VALID)}): {invalid}", file=sys.stderr)
        return 1
    if missing:
        print("Relationship map validation failed.", file=sys.stderr)
        print("Missing classifications:", file=sys.stderr)
        for conversation_id in missing:
            print(f"- {conversation_id}", file=sys.stderr)
        return 1

    print(f"Relationship map validation passed for {len(conversation_ids)} conversation_ids.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())