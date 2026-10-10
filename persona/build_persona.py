#!/usr/bin/env python3
"""Session 1.2 Part 3 -- measure your real texting habits from a WhatsApp export.

Spec from the guide: --file, --name, utf-8 with errors="ignore", filter to your messages,
compute Hinglish ratio / average length / top-15 emojis (regex, no emoji package) /
sample size, print a summary and write JSON. Warn loudly on zero matches.

Run once per chat so each relationship gets its own numbers:
    python3 persona/build_persona.py --file "data/raw_export/WhatsApp Chat with Wife.txt"  --name "अरूण" --output persona/style_signals_wife.json
    python3 persona/build_persona.py --file "data/raw_export/WhatsApp Chat with Family.txt" --name "अरूण" --output persona/style_signals_family.json

Fixes vs the guide's fallback snippet (see docs/AUDIT.md):
  * understands the iOS "[date, time] name:" export as well as Android "date, time - name:"
    (the guide's LINE_PATTERN is Android-only; your exports are iOS -> 0 matches)
  * drops media/system/call lines before counting (they are not your voice)
  * a larger Roman-Hindi word list + Devanagari detection (the 10-word list missed
    "Tumne kha liya khana", "babu", "jaan"...)
  * emoji regex merges variation selectors / skin tones so ❤ and ❤\ufe0f count once
  * also reports the MEDIAN length -- one long forward drags the average up
"""
from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ingestion.whatsapp_format import parse_messages, sender_counts, strip_noise  # noqa: E402

# Guide's markers first, then common Roman-Hindi words seen in real chats
HINGLISH_MARKERS = {
    "hai", "kya", "nahi", "yaar", "matlab", "acha", "theek", "bhai", "kar", "raha", "rha", "haan", "toh", "bhi",
    "hain", "ho", "hoga", "tha", "thi", "hu", "hun", "hoon", "nhi", "na", "mat", "kyu", "kyun", "kaise", "kab",
    "kahan", "kaha", "kaun", "kitna", "accha", "achha", "thik", "ji", "arre", "yar", "bas", "abhi", "kal", "aaj",
    "jaldi", "thoda", "bahut", "bohot", "sahi", "pakka", "chalo", "dekho", "karo", "karna", "kiya", "krna", "jao",
    "gaya", "gayi", "aao", "aaoge", "aaya", "lena", "lene", "liya", "diya", "dena", "kha", "khana", "khaya", "so",
    "bol", "bolo", "batao", "bata", "suno", "pata", "chahiye", "rahi", "rahe", "rhi", "wala", "wali", "ghar", "sab",
    "kuch", "koi", "mast", "badhiya", "main", "mujhe", "mera", "meri", "tum", "tumne", "tumhe", "aap", "hum",
    "babu", "jaan", "beta", "karke", "karta", "karti", "jaa", "aa", "ke", "ki", "ka", "ko", "se", "mein", "pe",
}
# words that are also English -> only count when another Hindi word is present
AMBIGUOUS = {"so", "na", "ho", "to", "main", "aa", "ke", "ki", "ka", "ko", "se", "pe", "kal", "mat", "bas", "hu"}
DEVANAGARI = re.compile(r"[ऀ-ॿ]")
EMOJI = re.compile(
    "[\U0001F1E6-\U0001F1FF]{2}"
    "|[\U0001F300-\U0001FAFF☀-➿⌀-⏿⬀-⯿][\ufe0f\U0001F3FB-\U0001F3FF]?"
    "(?:\u200d[\U0001F300-\U0001FAFF☀-➿]\ufe0f?)*"
)
_STRIP = re.compile("[\ufe0f\U0001F3FB-\U0001F3FF]")


def is_hinglish(text: str) -> bool:
    if DEVANAGARI.search(text):
        return True
    words = re.findall(r"[a-z]+", text.lower())
    strong = sum(1 for w in words if w in HINGLISH_MARKERS and w not in AMBIGUOUS)
    weak = sum(1 for w in words if w in AMBIGUOUS)
    return strong >= 1 or (weak >= 2 and len(words) <= 5)


def emojis_in(text: str) -> list[str]:
    return [_STRIP.sub("", e) for e in EMOJI.findall(text)]


def compute_style_signals(my_messages: list[str]) -> dict:
    total = len(my_messages)
    if total == 0:
        return {"error": "No messages matched --name. Re-check the exact sender label in your raw export file."}
    lengths = [len(m.split()) for m in my_messages]
    emoji_counter = Counter(e for m in my_messages for e in emojis_in(m))
    return {
        "hinglish_ratio": round(sum(map(is_hinglish, my_messages)) / total, 3),
        "avg_message_length_words": round(sum(lengths) / total, 1),
        "median_message_length_words": statistics.median(lengths),
        "messages_with_emoji_ratio": round(sum(1 for m in my_messages if emojis_in(m)) / total, 3),
        "top_emojis": emoji_counter.most_common(15),
        "sample_size": total,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Extract persona style signals from a WhatsApp .txt export.")
    ap.add_argument("--file", required=True, type=Path)
    ap.add_argument("--name", required=True, help="your exact sender label in this export")
    ap.add_argument("--output", type=Path, default=ROOT / "persona" / "style_signals.json")
    args = ap.parse_args()

    messages = parse_messages(args.file)
    mine = [t for t in (strip_noise(m.text) for m in messages if m.sender.strip() == args.name.strip().rstrip(":")) if t]
    signals = compute_style_signals(mine)
    if "error" in signals:
        print(f'⚠\ufe0f  WARNING: 0 messages from "{args.name}" in {args.file.name}.')
        print(f"   Sender labels found in this file: {sender_counts(messages)}")
        print("   Copy your label exactly (Session 1.2 Part 2.4). Nothing was written.")
        return 1

    print(json.dumps(signals, indent=2, ensure_ascii=False))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(signals, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"✅ {signals['sample_size']} messages · Hinglish {signals['hinglish_ratio']:.0%} · "
          f"median {signals['median_message_length_words']} words · written to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
