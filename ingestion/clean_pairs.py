#!/usr/bin/env python3
"""Re-clean an EXISTING data/processed_pairs.jsonl with the current noise + sensitivity rules.

Why: Session 2.1 Part 4 says "tell me the bad replies, remove them, rerun validation".
Re-exporting from the phone is the cleanest fix, but if you only have the pairs file
(as in this rebuild), this applies exactly the same rules parse_export.py now uses:
  * strip system/call/media lines inside each field ("Video call, 47 sec" ...)
  * drop pairs that become empty or ack-only
  * scrub phones / emails / links / PAN-like IDs
  * quarantine money / OTP / ID pairs (never embedded)

    python3 ingestion/clean_pairs.py --input data/processed_pairs.original.jsonl
"""
from __future__ import annotations

import argparse
import collections
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ingestion.parse_export import OUTPUT_PATH, QUARANTINE_PATH, _rel, finalize, write_jsonl  # noqa: E402
from ingestion.whatsapp_format import is_ack, is_noise_line, strip_noise  # noqa: E402


def clean(rows: list[dict], keep_sensitive: bool = False) -> tuple[list[dict], list[dict], dict]:
    stats = collections.Counter()
    stripped = []
    for r in rows:
        their, mine = strip_noise(r.get("their_message", "")), strip_noise(r.get("my_reply", ""))
        removed = sum(1 for f in ("their_message", "my_reply") for ln in r.get(f, "").split("\n") if ln.strip() and is_noise_line(ln))
        if removed:
            stats["pairs_with_noise_lines"] += 1
            stats["noise_lines_removed"] += removed
        if not their or not mine or is_ack(mine) or is_ack(their):
            stats["dropped_empty_or_ack"] += 1
            continue
        stripped.append(dict(r, their_message=their, my_reply=mine))
    kept, quarantined = finalize(stripped, keep_sensitive)
    stats["quarantined_sensitive"] = len(quarantined)
    stats["kept"] = len(kept)
    return kept, quarantined, dict(stats)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", type=Path, default=OUTPUT_PATH)
    ap.add_argument("--output", type=Path, default=OUTPUT_PATH)
    ap.add_argument("--keep-sensitive", action="store_true")
    args = ap.parse_args(argv)
    rows = [json.loads(l) for l in args.input.read_text(encoding="utf-8").splitlines() if l.strip()]
    kept, quarantined, stats = clean(rows, args.keep_sensitive)
    write_jsonl(args.output, kept)
    write_jsonl(QUARANTINE_PATH, quarantined)
    by_conv = collections.Counter(r["conversation_id"] for r in kept)
    print(f"Input {len(rows)} pairs -> {stats}")
    print(f"Per conversation: {dict(by_conv)}")
    print(f"Wrote {_rel(args.output)} and {_rel(QUARANTINE_PATH)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
