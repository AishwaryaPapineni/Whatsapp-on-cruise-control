"""Pipeline stage 4 -- retrieve_similar(): the history brain's search function.

The Week 3 generator imports `from ingestion.retrieval import retrieve_similar`, but that
file wasn't in the session code -- this is it.

Search order:
  1. If the sender has their OWN past chat (config/contact_profiles.json -> conversation_id),
     search only that conversation first: "what I said to THIS person".
  2. Fill the rest from the relationship box, EXCLUDING conversations marked private.
     That keeps your replies to your wife (mapped to "family" per the course's 4 boxes)
     out of the results when your mum or papa text you.
  3. Drop weak matches (distance > MAX_DISTANCE). A wrong example teaches the wrong voice;
     the persona alone handles first-of-its-kind messages (Session 1.1 Part 3).
"""
from __future__ import annotations

import os

from ingestion.embedder import collection, get_embedder

MAX_DISTANCE = float(os.getenv("MAX_DISTANCE", "0.6"))


def _query(col, vector, k: int, where: dict | None) -> list[dict]:
    try:
        res = col.query(query_embeddings=[vector], n_results=k, where=where,
                        include=["documents", "metadatas", "distances"])
    except Exception:  # empty filter result / old collection without the field
        return []
    out = []
    for doc, meta, dist in zip(res["documents"][0], res["metadatas"][0], res["distances"][0]):
        out.append({"their_message": doc, "my_reply": meta.get("my_reply", ""), "distance": round(float(dist), 4),
                    "conversation_id": meta.get("conversation_id", ""), "timestamp": meta.get("timestamp", "")})
    return out


def retrieve_similar(relationship: str, incoming_text: str, k: int = 3, conversation_id: str | None = None,
                     private_conversations: tuple[str, ...] = (), max_distance: float | None = None) -> list[dict]:
    if relationship not in ("family", "friend", "professional", "unknown") or not incoming_text.strip():
        return []
    try:
        col = collection(relationship, create=False)
    except Exception:
        return []
    if col.count() == 0:
        return []
    limit = MAX_DISTANCE if max_distance is None else max_distance
    vector = get_embedder().encode([incoming_text])[0]
    vector = list(vector)

    results: list[dict] = []
    if conversation_id:
        for r in _query(col, vector, k, {"conversation_id": conversation_id}):
            r["scope"] = "this contact"
            results.append(r)
    if len(results) < k:
        blocked = [c for c in private_conversations if c and c != conversation_id]
        where = {"conversation_id": {"$nin": blocked}} if blocked else None
        seen = {(r["their_message"], r["my_reply"]) for r in results}
        for r in _query(col, vector, k + len(results), where):
            if (r["their_message"], r["my_reply"]) not in seen and len(results) < k:
                r["scope"] = f"{relationship} box"
                results.append(r)
    return [r for r in results if r["distance"] <= limit]
