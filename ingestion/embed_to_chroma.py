#!/usr/bin/env python3
"""Session 2.2 Part 4 -- embed reply pairs into one ChromaDB collection per relationship.

Guide spec: load pairs + config/contact_relationship_map.json, tag each pair (default
"unknown"), embed `their_message` with the multilingual model loaded ONCE, connect to
the local Chroma server, one collection per class (history_family / _friend /
_professional / _unknown), upsert with my_reply + timestamp metadata and a stable id,
print per-collection counts, warn on empty collections, progress every 50 pairs.

Changes vs the session code (docs/AUDIT.md):
  * stable id = hash(conversation_id, timestamp, their_message, my_reply). The old
    id used the pair's INDEX in the file, so after cleaning removed a pair every later
    id shifted and re-running left stale duplicates in Chroma.
  * sync: ids no longer in processed_pairs.jsonl are deleted (e.g. quarantined pairs).
  * conversation_id stored as metadata -- lets retrieval keep private chats (your wife)
    out of other family members' searches while still using the 4 boxes.
  * refuses to run if validate_relationship_map / validate_pairs would fail
    ("REPLACE_ME" left in the map, leaked noise or money in the pairs).
  * cosine distance space; refuses to mix vectors from a different embedding model.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from config.constants import RELATIONSHIPS  # noqa: E402
from ingestion.embedder import collection, get_client, get_embedder  # noqa: E402

PAIRS_PATH = ROOT / "data" / "processed_pairs.jsonl"
MAP_PATH = ROOT / "config" / "contact_relationship_map.json"
PLACEHOLDER = "REPLACE_ME"
BATCH_SIZE = 50


def load_pairs(path: Path = PAIRS_PATH) -> list[dict]:
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def relationship_for(pair: dict, rel_map: dict) -> str:
    rel = rel_map.get(pair.get("conversation_id", ""), rel_map.get("_default", "unknown"))
    return rel if rel in RELATIONSHIPS else "unknown"


def stable_id(pair: dict) -> str:
    key = "\x1f".join(pair.get(k, "") for k in ("conversation_id", "timestamp", "their_message", "my_reply"))
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:32]


def embed(pairs: list[dict], rel_map: dict, reset: bool = False) -> dict[str, int]:
    embedder = get_embedder()
    client = get_client()
    if reset:
        for rel in RELATIONSHIPS:
            try:
                client.delete_collection(f"history_{rel}")
            except Exception:
                pass
    cols = {rel: collection(rel) for rel in RELATIONSHIPS}
    for rel, col in cols.items():
        used = (col.metadata or {}).get("embedder")
        if used and used != embedder.name:
            raise SystemExit(f"history_{rel} was built with {used!r}, current model is {embedder.name!r}. Re-run with --reset.")

    wanted: dict[str, set[str]] = defaultdict(set)
    for start in range(0, len(pairs), BATCH_SIZE):
        batch = pairs[start:start + BATCH_SIZE]
        vectors = embedder.encode([p["their_message"] for p in batch], show_progress_bar=False)
        grouped = defaultdict(list)
        for p, v in zip(batch, vectors):
            grouped[relationship_for(p, rel_map)].append((stable_id(p), p, list(v)))
        for rel, records in grouped.items():
            ids = [r[0] for r in records]
            wanted[rel].update(ids)
            for other in RELATIONSHIPS:  # a conversation re-classified moves boxes cleanly
                if other != rel:
                    cols[other].delete(ids=ids)
            cols[rel].upsert(
                ids=ids,
                embeddings=[r[2] for r in records],
                documents=[r[1]["their_message"] for r in records],
                metadatas=[{"my_reply": r[1]["my_reply"], "timestamp": r[1].get("timestamp", ""),
                            "conversation_id": r[1].get("conversation_id", "")} for r in records],
            )
        done = min(start + BATCH_SIZE, len(pairs))
        print(f"Processed {done}/{len(pairs)} pairs")

    # sync: drop anything that is no longer in the cleaned pairs file
    for rel, col in cols.items():
        existing = set(col.get(include=[])["ids"])
        stale = sorted(existing - wanted[rel])
        if stale:
            col.delete(ids=stale)
            print(f"Removed {len(stale)} stale entries from history_{rel}")

    counts = {rel: cols[rel].count() for rel in RELATIONSHIPS}
    print("\nChroma embedding summary:")
    for rel, n in counts.items():
        print(f"- history_{rel}: {n} pairs")
        if n == 0:
            print(f"  WARNING: history_{rel} is completely empty")
    return counts


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--reset", action="store_true", help="drop and rebuild all four collections")
    ap.add_argument("--skip-checks", action="store_true")
    args = ap.parse_args(argv)
    rel_map = json.loads(MAP_PATH.read_text(encoding="utf-8"))
    pairs = load_pairs()
    if not args.skip_checks:
        missing = sorted({p["conversation_id"] for p in pairs if rel_map.get(p["conversation_id"]) in (None, PLACEHOLDER)})
        if missing:
            print(f"❌ Unclassified conversation_ids in {MAP_PATH.name}: {missing}. Run ingestion/build_relationship_map.py and fill them in.")
            return 1
        from ingestion.validate_pairs import validate

        flags = validate(pairs, show_samples=False)
        if sum(flags.values()):
            print("❌ processed_pairs.jsonl failed validation -- fix (ingestion/clean_pairs.py) before embedding.")
            return 1
    print(f"Embedding with {get_embedder().name}")
    embed(pairs, rel_map, reset=args.reset)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
