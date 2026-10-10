"""Shared constants used across ingestion, agent and bridge.

Keeping these in one place means the noise list used when *mining history* (Week 2) is
the same list used when *deciding live* (Week 3). Before this, parse_export.py and
validate_pairs.py each had their own list, and the validator could not catch what the
parser missed ("Video call", "Missed group call" leaked into 18 real pairs).
"""

# Session 3.2 Layer 2 -- standalone low-signal acknowledgements (from the course notes)
ONE_WORD_ACKS = {
    "ok", "okay", "k", "kk", "haan", "hmm", "thanks", "thank you", "cool", "nice",
    # added after reviewing real data
    "okk", "okie", "ji", "ha", "haa", "hm", "ty", "thx", "done", "👍", "🙏", "👌",
}

# Session 2.1 Part 0.2 -- system / media placeholders. Case-insensitive substrings.
# Extend this when your phone's language or WhatsApp version shows other wording.
SYSTEM_OR_MEDIA_SUBSTRINGS = (
    "Messages and calls are end-to-end encrypted",
    "<Media omitted>",
    "image omitted",
    "video omitted",
    "audio omitted",
    "sticker omitted",
    "GIF omitted",
    "document omitted",
    "Contact card omitted",
    "This message was deleted",
    "You deleted this message",
    "<This message was edited>",
    "Answered on other device",
    "Silenced unknown caller",
    "created group",
    "changed the subject",
    "added you",
    "changed this group's icon",
    "<attached:",
    "Waiting for this message",
    "This message can't be displayed here",
    "Tap to learn more",
    "This message was edited",
    "Location: https://maps",
    "live location shared",
    "POLL:",
)

# Call-log lines ("Video call, 47 sec", "Missed group call, 2 invited", "Voice call, No answer").
# Anchored to the WHOLE line so a real message like "video call kar lein?" is NOT dropped.
# (A plain "Voice call" substring -- the course's fix -- would delete real messages too.)
CALL_LOG_LINE = r"^(missed\s+)?(voice|video|group)\s+call\b\s*(,.*)?$"

# Invisible characters WhatsApp inserts (LRM etc.). They break "^[" regexes and
# hide noise lines from substring matching, so they are stripped first.
INVISIBLE_CHARS = "\u200e\u200f\u202a\u202b\u202c\u202d\u202e\ufeff"

# The four history boxes from Session 1.1 / 2.2 ("group" is a router-only label).
RELATIONSHIPS = ("family", "friend", "professional", "unknown")
