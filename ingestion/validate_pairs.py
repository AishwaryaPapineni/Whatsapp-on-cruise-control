#!/usr/bin/env python3
"""Session 2.1 Part 4 -- validate data/processed_pairs.jsonl before trusting it.

The guide's six checks, plus two that your real data needed:
  1 total + per-conversation counts (warn on zero)
  2 five random pairs printed readably
  3 leaked noise -- now uses the SAME list as the parser (config/constants.py), so
    "Video call" / "Missed group call" are caught. The original only looked for
    "omitted", "<media", "deleted" and reported your file as clean while 18 pairs leaked.
  4 my_reply > 100 words
  5 identical / near-identical pairs
  6 one-line summary
  + 7 sensitive content (money / OTP / IDs) still present
  + 8 unscrubbed phone numbers / emails
Exit code is 1 when issues are found, so it can gate embed_to_chroma.py.
"""
from __future__ import annotations

import collections
import json
import random
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from config.sensitive import is_sensitive  # noqa: E402
from ingestion.whatsapp_format import is_noise_line  # noqa: E402

INPUT_PATH = ROOT / "data" / "processed_pairs.jsonl"
SAMPLE_SIZE = 5
RED, RESET = "\033[91m", "\033[0m"
PII = re.compile(r"(?<!\d)\+?\d[\d\s-]{8,}\d(?!\d)|\b[\w.+-]+@[\w-]+\.[\w.]+\b")


def warn(msg: str) -> None:
    print(f"{RED}WARNING: {msg}{RESET}")


def words(text: str) -> set[str]:
    return {"".join(c for c in w if c.isalnum()) for w in text.casefold().split()} - {""}


def near_identical(a: str, b: str) -> bool:
    wa, wb = words(a), words(b)
    if not wa or not wb:
        return False
    return len(wa & wb) / len(wa | wb) >= 0.9 and min(len(wa), len(wb)) >= 2


def validate(pairs: list[dict], show_samples: bool = True) -> dict:
    flags = collections.Counter()
    counts = collections.Counter(p.get("conversation_id", "<missing>") for p in pairs)
    print(f"Pair validation report: {INPUT_PATH.relative_to(ROOT)}")
    print(f"Total pairs: {len(pairs)}\n\nPairs by conversation:")
    for cid, n in sorted(counts.items()):
        print(f"- {cid}: {n}")
    if not counts:
        warn("No conversation IDs found")
        flags["empty"] += 1

    for i, p in enumerate(pairs, 1):
        their, mine = p.get("their_message", ""), p.get("my_reply", "")
        for field, text in (("their_message", their), ("my_reply", mine)):
            if not text.strip():
                warn(f"Pair {i}: empty {field}")
                flags["noise/empty"] += 1
            elif any(is_noise_line(line) for line in text.split("\n")):
                warn(f"Pair {i}: noise line leaked into {field}: {text[:60]!r}")
                flags["noise/empty"] += 1
        if len(mine.split()) > 100:
            warn(f"Pair {i}: my_reply is {len(mine.split())} words")
            flags["long"] += 1
        if their.casefold() == mine.casefold() or near_identical(their, mine):
            warn(f"Pair {i}: their_message and my_reply are (near-)identical")
            flags["duplicate"] += 1
        reason = is_sensitive(their + "\n" + mine)
        if reason:
            warn(f"Pair {i}: sensitive ({reason}) content still in memory")
            flags["sensitive"] += 1
        if PII.search(their + " " + mine):
            warn(f"Pair {i}: unscrubbed phone/email")
            flags["pii"] += 1

    if show_samples and pairs:
        print(f"\nRandom samples ({min(SAMPLE_SIZE, len(pairs))}):")
        for n, p in enumerate(random.sample(pairs, min(SAMPLE_SIZE, len(pairs))), 1):
            print(f"\n--- Sample {n} [{p.get('conversation_id')}] ---")
            print(f"Their message:\n{p.get('their_message')}\n\nMy reply:\n{p.get('my_reply')}")
            print(f"\nTimestamp: {p.get('timestamp')}")

    print("\nFlag totals:")
    for name in ("noise/empty", "long", "duplicate", "sensitive", "pii"):
        print(f"- {name}: {flags.get(name, 0)}")
    total = sum(flags.values())
    print("\n" + ("✅ Looks good" if total == 0 else f"⚠\ufe0f {total} issues found — review above"))
    return dict(flags)


def main() -> int:
    if not INPUT_PATH.exists():
        warn(f"{INPUT_PATH} not found -- run ingestion/parse_export.py first")
        return 1
    pairs, bad = [], 0
    for n, line in enumerate(INPUT_PATH.read_text(encoding="utf-8").splitlines(), 1):
        if line.strip():
            try:
                pairs.append(json.loads(line))
            except json.JSONDecodeError as e:
                warn(f"Line {n} is not valid JSON: {e}")
                bad += 1
    flags = validate(pairs)
    return 1 if (bad or sum(flags.values())) else 0


if __name__ == "__main__":
    raise SystemExit(main())
