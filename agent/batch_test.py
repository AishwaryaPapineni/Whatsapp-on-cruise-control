#!/usr/bin/env python3
"""Session 3.2 -- exercise every reply-or-ignore gate in one readable dry run.

The session's 10 cases, plus cases taken from your own data and hard rules.
Runs the FULL pipeline (router -> decision -> context -> retrieval -> persona -> generation).
    python3 agent/batch_test.py            # uses Gemini
    LLM_PROVIDER=offline EMBEDDER=hash python3 agent/batch_test.py   # no keys / no downloads
"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent.context import ChatContext  # noqa: E402
from agent.pipeline import process_message  # noqa: E402

WIFE, FAMILY, WORK, FRIEND = ("919812345671", "919812345673", "919812345672", "919812345670")
J = lambda n: f"{n}@s.whatsapp.net"  # noqa: E731

TEST_CASES = [
    # --- the session's original cases (expected results noted) ---
    {"name": "group chat", "jid": "120363000000000000@g.us", "text": "What time are we meeting?"},
    {"name": "unknown number", "jid": J("919899999999"), "text": "Hello, are you available?"},
    {"name": "media only", "jid": J(FAMILY), "text": "", "message_type": "image"},
    {"name": "forwarded message", "jid": J(FRIEND), "text": "Please share this important update.", "is_forwarded": True},
    {"name": "one-word ack", "jid": J(FAMILY), "text": "thanks"},
    {"name": "money request", "jid": J(WORK), "text": "Can you send me 5000 rupees?"},
    {"name": "casual family (plan!)", "jid": J(FAMILY), "text": "Are you free for dinner tonight?"},
    {"name": "casual friend (plan!)", "jid": J(FRIEND), "text": "Want to catch a movie this weekend?"},
    {"name": "casual professional (plan!)", "jid": J(WORK), "text": "Can we sync tomorrow on the project update?"},
    # --- added: your hard rules + real-life cases ---
    {"name": "wife check-in", "jid": J(WIFE), "text": "Tumne kha liya khana?"},
    {"name": "wife pickup (plan)", "jid": J(WIFE), "text": "I am going to be late today, can you pick me up?"},
    {"name": "family diwali (plan)", "jid": J(FAMILY), "text": "diwali pe ghar aaoge kya?"},
    {"name": "family reached", "jid": J(FAMILY), "text": "Reached home safely"},
    {"name": "family serious", "jid": J(FAMILY), "text": "Papa hospital mein hai, call karo"},
    {"name": "Hindi money", "jid": J(FAMILY), "text": "Beta paise bhej do"},
    {"name": "OTP", "jid": J(WIFE), "text": "OTP aaya kya?"},
    {"name": "work celebration", "jid": J(WORK), "text": "We crossed 1000 registrations!! 🎉"},
    {"name": "emoji only", "jid": J(WIFE), "text": "😂😂"},
    {"name": "own message", "jid": J(FAMILY), "from_me": True, "text": "I already sent this update."},
    {"name": "family after you typed", "jid": J(FAMILY), "text": "Reached home safely"},
]


def compact(value, limit=42):
    value = " ".join(str(value or "").split())
    return value if len(value) <= limit else value[: limit - 3] + "..."


def main() -> None:
    ctx = ChatContext(Path(tempfile.mkdtemp()))  # isolated: don't pollute your real chat context
    print("Running decision-engine batch test...\n")
    rows = []
    for case in TEST_CASES:
        payload = {"message_type": "text", "is_forwarded": False, "from_me": False, **case}
        t = process_message(payload, context=ctx, log=False)
        rows.append(t)
        print(f"{case['name']}: {t['decision']} ({t['reason']})" + (f"\n  Reply: {compact(t['reply'], 100)}" if t["reply"] else ""))
    print("\n" + "=" * 128 + "\nSUMMARY\n" + "=" * 128)
    print(f"{'Message':<42} {'Relationship':<13} {'Decision':<8} {'Reason':<40} Reply")
    print("-" * 128)
    for t in rows:
        print(f"{compact(t['text']):<42} {t['relationship']:<13} {t['decision']:<8} {compact(t['reason'], 40):<40} {compact(t['reply'], 40)}")


if __name__ == "__main__":
    main()
