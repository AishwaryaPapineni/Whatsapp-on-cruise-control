#!/usr/bin/env python3
"""Create or update the conversation-to-relationship map."""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


PAIRS_PATH = ROOT / "data" / "processed_pairs.jsonl"
MAP_PATH = ROOT / "config" / "contact_relationship_map.json"
PLACEHOLDER = "REPLACE_ME"


def load_conversation_ids() -> list[str]:
    conversation_ids: set[str] = set()
    with PAIRS_PATH.open(encoding="utf-8") as pairs_file:
        for line in pairs_file:
            if line.strip():
                conversation_ids.add(json.loads(line)["conversation_id"])
    return sorted(conversation_ids)


def load_existing_map() -> dict[str, str]:
    if not MAP_PATH.exists():
        return {}
    with MAP_PATH.open(encoding="utf-8") as map_file:
        relationship_map = json.load(map_file)
    if not isinstance(relationship_map, dict):
        raise ValueError(f"Expected {MAP_PATH} to contain a JSON object")
    return relationship_map


def main() -> None:
    conversation_ids = load_conversation_ids()
    relationship_map = load_existing_map()
    new_ids = [conversation_id for conversation_id in conversation_ids if conversation_id not in relationship_map]

    for conversation_id in new_ids:
        relationship_map[conversation_id] = PLACEHOLDER
    relationship_map.setdefault("_default", "unknown")

    MAP_PATH.parent.mkdir(parents=True, exist_ok=True)
    with MAP_PATH.open("w", encoding="utf-8") as map_file:
        json.dump(dict(sorted(relationship_map.items())), map_file, indent=2)
        map_file.write("\n")

    placeholders = [
        key for key, value in sorted(relationship_map.items()) if value == PLACEHOLDER
    ]
    print(f"Total conversation_ids: {len(conversation_ids)}")
    print(f"New conversation_ids needing attention: {len(new_ids)}")
    print("conversation_ids still set to REPLACE_ME:")
    if placeholders:
        for conversation_id in placeholders:
            print(f"- {conversation_id}")
    else:
        print("- none")


if __name__ == "__main__":
    main()