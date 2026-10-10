#!/usr/bin/env python3
"""Session 2.1 Part 3 -- parse, clean and pair WhatsApp exports.

Implements the guide's 11-point spec:
  1  loop data/raw_export/*.txt, conversation_id = slug of "WhatsApp Chat with <X>"
  2  "DATE, TIME - SENDER: MESSAGE" (+ iOS brackets), 12h/24h, continuation lines appended
  3  drop system/media lines (config/constants.py -- easy to extend)
  4  drop standalone one-word acks
  5  --name matched exactly (repeatable: your label can differ per file)
  6  merge consecutive same-sender messages into one turn
  7  pair: their turn immediately followed by my turn
  8  keep the last 500 pairs per conversation by FILE ORDER (dates never parsed)
  9  write data/processed_pairs.jsonl (+ data/processed_pairs/<id>.jsonl)
 10  per-conversation summary, warn on zero pairs

Additions (each closes a gap found in your real data, see docs/AUDIT.md):
  * noise is removed line-by-line INSIDE multi-line turns -- "Video call, 47 sec" lines
    were hiding inside otherwise-real messages (18 leaked pairs)
  * call-log lines (Video/Group/Missed group call) are matched as whole lines
  * group chats (3+ senders) are skipped with a warning (guide Part 0 item 3)
  * money / OTP / ID pairs are moved to data/quarantine_pairs.jsonl instead of memory
    (hard rule: never discuss money autonomously). Use --keep-sensitive to disable.
  * phone numbers, emails, links, PAN-like IDs are scrubbed from stored text
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from config.sensitive import is_sensitive, scrub  # noqa: E402
from ingestion.whatsapp_format import is_ack, parse_messages, strip_noise  # noqa: E402

RAW_EXPORT_DIR = ROOT / "data" / "raw_export"
OUTPUT_PATH = ROOT / "data" / "processed_pairs.jsonl"
PER_CONVERSATION_DIR = ROOT / "data" / "processed_pairs"
QUARANTINE_PATH = ROOT / "data" / "quarantine_pairs.jsonl"
MAX_PAIRS_PER_CONVERSATION = 500


def conversation_id_from_path(path: Path) -> str:
    name = path.stem
    prefix = "whatsapp chat with "
    if name.lower().startswith(prefix):
        name = name[len(prefix):]
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "chat"


def build_turns(messages) -> list[dict]:
    turns: list[dict] = []
    for m in messages:
        text = strip_noise(m.text)
        if not text or is_ack(text):
            continue
        if turns and turns[-1]["sender"] == m.sender:
            turns[-1]["text"] += "\n" + text
        else:
            turns.append({"sender": m.sender, "text": text, "timestamp": m.timestamp})
    return turns


def make_pairs(conversation_id: str, turns: list[dict], my_names: set[str]) -> list[dict]:
    pairs = []
    for theirs, mine in zip(turns, turns[1:]):
        if theirs["sender"] not in my_names and mine["sender"] in my_names:
            pairs.append({
                "conversation_id": conversation_id,
                "their_message": theirs["text"],
                "my_reply": mine["text"],
                "timestamp": mine["timestamp"],
            })
    return pairs[-MAX_PAIRS_PER_CONVERSATION:]


def finalize(pairs: list[dict], keep_sensitive: bool) -> tuple[list[dict], list[dict]]:
    """Scrub PII and split off sensitive pairs."""
    kept, quarantined = [], []
    for p in pairs:
        reason = None if keep_sensitive else is_sensitive(p["their_message"] + "\n" + p["my_reply"])
        q = dict(p, their_message=scrub(p["their_message"]), my_reply=scrub(p["my_reply"]))
        if reason:
            quarantined.append(dict(q, quarantine_reason=reason))
        elif q["their_message"].strip() and q["my_reply"].strip():
            kept.append(q)
    return kept, quarantined


def _rel(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Parse WhatsApp exports into (their_message -> my_reply) pairs.")
    ap.add_argument("--name", required=True, action="append", help="your exact sender label (repeat if it differs per file)")
    ap.add_argument("--input-dir", type=Path, default=RAW_EXPORT_DIR)
    ap.add_argument("--keep-sensitive", action="store_true", help="do NOT quarantine money/OTP pairs (not recommended)")
    args = ap.parse_args(argv)
    my_names = {n.strip().rstrip(":") for n in args.name}

    files = sorted(args.input_dir.glob("*.txt"))
    if not files:
        print(f"⚠\ufe0f  No .txt exports in {args.input_dir} -- see Session 1.2 Part 2.")
        return 1
    all_pairs, all_quarantine = [], []
    for path in files:
        cid = conversation_id_from_path(path)
        messages = parse_messages(path)
        senders = {m.sender for m in messages}
        if len(senders - my_names) > 1:
            print(f"⏭  {path.name}: {len(senders)} senders -> group chat, skipped (agent never replies in groups)")
            continue
        pairs, quarantined = finalize(make_pairs(cid, build_turns(messages), my_names), args.keep_sensitive)
        all_pairs += pairs
        all_quarantine += quarantined
        write_jsonl(PER_CONVERSATION_DIR / f"{cid}.jsonl", pairs)
        print(f"{path.name}: {len(pairs)} pairs kept, {len(quarantined)} quarantined (conversation_id={cid})")
        if not pairs:
            print(f'⚠\ufe0f  "{cid}" produced zero pairs -- likely a --name mismatch. Senders here: {sorted(senders)}')
    write_jsonl(OUTPUT_PATH, all_pairs)
    write_jsonl(QUARANTINE_PATH, all_quarantine)
    print(f"Wrote {len(all_pairs)} pairs to {_rel(OUTPUT_PATH)}; "
          f"{len(all_quarantine)} sensitive pairs to {_rel(QUARANTINE_PATH)} (git-ignored, never embedded)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
