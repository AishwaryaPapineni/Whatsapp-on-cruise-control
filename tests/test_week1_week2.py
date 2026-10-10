"""Week 1 (persona) + Week 2 (parse, clean, validate, embed, retrieve)."""
import json

import pytest
from conftest import ROOT

LRM = "\u200e"
IOS_EXPORT = (
    f"{LRM}[10/02/25, 1:30:00\u202fPM] Papaji: {LRM}Messages and calls are end-to-end encrypted.\n"
    "[10/02/25, 1:30:58 PM] Papaji: Beta pahunch gaye?\n"
    "[10/02/25, 1:31:10 PM] Papaji: call karna\n"
    "[10/02/25, 1:32:00 PM] अरूण: Landed 😊\n"
    "abhi hotel ja raha\n"
    f"{LRM}[10/02/25, 1:33:00 PM] अरूण: {LRM}Video call, {LRM}47 sec\n"
    "[10/02/25, 1:40:00 PM] Papaji: ok\n"
    "[10/02/25, 1:41:00 PM] Papaji: video call kar lein?\n"
    "[10/02/25, 1:42:00 PM] अरूण: Haan 10 min mein\n"
    "[10/02/25, 1:50:00 PM] Papaji: Beta 5000 rupees bhej do\n"
    "[10/02/25, 1:51:00 PM] अरूण: Okay sending\n"
)
ANDROID_EXPORT = (
    "12/08/25, 14:32 - Priya: yaar kal free hai kya\n"
    "12/08/25, 14:33 - Arun Nandewal: Haan bol\n"
    "12/08/25, 14:34 - Priya: image omitted\n"
)


@pytest.fixture
def raw_dir(tmp_path):
    d = tmp_path / "raw_export"
    d.mkdir()
    (d / "WhatsApp Chat with Papaji.txt").write_text(IOS_EXPORT, encoding="utf-8")
    (d / "WhatsApp Chat with Priya.txt").write_text(ANDROID_EXPORT, encoding="utf-8")
    return d


def test_parser_handles_ios_lrm_and_android(raw_dir):
    from ingestion.whatsapp_format import parse_messages

    ios = parse_messages(raw_dir / "WhatsApp Chat with Papaji.txt")
    mine = [m for m in ios if m.sender == "अरूण"]
    assert mine[0].text == "Landed 😊\nabhi hotel ja raha"  # continuation line kept, not dropped
    assert any("Video call" in m.text for m in ios)  # parsed as a message (then removed as noise)
    android = parse_messages(raw_dir / "WhatsApp Chat with Priya.txt")
    assert [m.sender for m in android] == ["Priya", "Arun Nandewal", "Priya"]


def test_noise_rules_whole_line_only():
    from ingestion.whatsapp_format import is_noise_line

    for noise in ["Video call, 47 sec", "Missed group call, 2 invited", "Group call, Answered on other device",
                  "<Media omitted>", "image omitted", "This message can't be displayed here. Please open WhatsApp", "null"]:
        assert is_noise_line(noise), noise
    for real in ["video call kar lein?", "Let us do a video call tomorrow", "nullah ke paas", "I edited the deck"]:
        assert not is_noise_line(real), real


def test_parse_export_end_to_end(raw_dir, tmp_path, monkeypatch):
    import ingestion.parse_export as pe

    monkeypatch.setattr(pe, "OUTPUT_PATH", tmp_path / "out.jsonl")
    monkeypatch.setattr(pe, "PER_CONVERSATION_DIR", tmp_path / "per")
    monkeypatch.setattr(pe, "QUARANTINE_PATH", tmp_path / "q.jsonl")
    assert pe.main(["--name", "अरूण", "--name", "Arun Nandewal", "--input-dir", str(raw_dir)]) == 0
    pairs = [json.loads(l) for l in (tmp_path / "out.jsonl").read_text(encoding="utf-8").splitlines()]
    by = {p["their_message"]: p["my_reply"] for p in pairs}
    assert by["Beta pahunch gaye?\ncall karna"] == "Landed 😊\nabhi hotel ja raha"  # burst merged, call line gone
    assert by["video call kar lein?"] == "Haan 10 min mein"  # real "video call" message kept
    assert by["yaar kal free hai kya"] == "Haan bol"
    q = [json.loads(l) for l in (tmp_path / "q.jsonl").read_text(encoding="utf-8").splitlines()]
    assert q and q[0]["quarantine_reason"] == "money"  # never reaches memory
    assert {p["conversation_id"] for p in pairs} == {"papaji", "priya"}


def test_group_export_skipped(tmp_path, monkeypatch):
    import ingestion.parse_export as pe

    d = tmp_path / "raw"
    d.mkdir()
    (d / "WhatsApp Chat with Gang.txt").write_text(
        "[1/1/25, 1:00:00 PM] A: hi\n[1/1/25, 1:01:00 PM] B: yo\n[1/1/25, 1:02:00 PM] Me: hey\n", encoding="utf-8")
    monkeypatch.setattr(pe, "OUTPUT_PATH", tmp_path / "o.jsonl")
    monkeypatch.setattr(pe, "PER_CONVERSATION_DIR", tmp_path / "p")
    monkeypatch.setattr(pe, "QUARANTINE_PATH", tmp_path / "q.jsonl")
    pe.main(["--name", "Me", "--input-dir", str(d)])
    assert (tmp_path / "o.jsonl").read_text() == ""


def test_clean_pairs_on_real_leak_shapes():
    from ingestion.clean_pairs import clean

    rows = [
        {"conversation_id": "family", "their_message": f"{LRM}Video call, {LRM}Answered on other device", "my_reply": "Send me the ticket", "timestamp": "1"},
        {"conversation_id": "wife", "their_message": f"Good morning baby 🥰\n{LRM}Video call, {LRM}33 min", "my_reply": "Good morning 😘", "timestamp": "2"},
        {"conversation_id": "family", "their_message": "Deposit Tax of Rs. 29810", "my_reply": "Done 8955703625", "timestamp": "3"},
        {"conversation_id": "family", "their_message": "Kaise ho", "my_reply": "ok", "timestamp": "4"},
    ]
    kept, quarantined, stats = clean(rows)
    assert [k["their_message"] for k in kept] == ["Good morning baby 🥰"]
    assert len(quarantined) == 1 and "8955703625" not in quarantined[0]["my_reply"]  # scrubbed even in quarantine


def test_validator_catches_what_v1_missed():
    from ingestion.validate_pairs import validate

    flags = validate([{"conversation_id": "w", "their_message": "Hi\nMissed group call, 2 invited", "my_reply": "Hello"},
                      {"conversation_id": "w", "their_message": "salary aayi?", "my_reply": "haan"}], show_samples=False)
    assert flags["noise/empty"] == 1 and flags["sensitive"] == 1


@pytest.mark.parametrize("text,expected", [("Tumne kha liya khana", True), ("Walking walking babu", True), ("विवाह बढ़िया", True),
                                           ("Good take rest", False), ("Boarded for Seattle on time", False), ("So I will go to the main gate", False)])
def test_hinglish_detection(text, expected):
    from persona.build_persona import is_hinglish

    assert is_hinglish(text) is expected


def test_build_persona_cli(raw_dir, tmp_path, monkeypatch):
    import persona.build_persona as bp

    out = tmp_path / "sig.json"
    monkeypatch.setattr("sys.argv", ["x", "--file", str(raw_dir / "WhatsApp Chat with Papaji.txt"), "--name", "अरूण:", "--output", str(out)])
    assert bp.main() == 0
    sig = json.loads(out.read_text(encoding="utf-8"))
    assert sig["sample_size"] == 3 and ["😊", 1] in sig["top_emojis"]  # call-log line not counted as a message
    monkeypatch.setattr("sys.argv", ["x", "--file", str(raw_dir / "WhatsApp Chat with Papaji.txt"), "--name", "Arun"])
    assert bp.main() == 1  # zero matches -> loud warning, nothing written


def test_persona_json_valid_and_complete():
    p = json.loads((ROOT / "persona" / "persona.json").read_text(encoding="utf-8"))
    for key in ("family", "friends", "professional", "wife"):
        assert p["relationships"][key]["example_replies"], key
    assert "Never discuss money over WhatsApp autonomously" in p["hard_rules"]
    assert "Never confirm plans without me" in p["hard_rules"]


def test_embed_is_idempotent_and_syncs(memory):
    from ingestion.embed_to_chroma import embed

    rel_map = {"_default": "unknown", "wife": "family", "family": "family", "professional-work": "professional"}
    assert embed(memory, rel_map)["family"] == 4  # re-run: no duplicates
    assert embed(memory[:3], rel_map)["family"] == 3  # removed pair is synced out


def test_private_conversation_never_leaks(memory):
    from ingestion.retrieval import retrieve_similar

    leaky = retrieve_similar("family", "Khana kha liya beta?", k=4, max_distance=2)
    assert "wife" in {r["conversation_id"] for r in leaky}  # the old behaviour
    safe = retrieve_similar("family", "Khana kha liya beta?", k=4, conversation_id="family", private_conversations=("wife",), max_distance=2)
    assert safe and {r["conversation_id"] for r in safe} == {"family"}
    own = retrieve_similar("family", "Khana kha liya?", k=2, conversation_id="wife", private_conversations=("wife",), max_distance=2)
    assert own[0]["conversation_id"] == "wife" and own[0]["scope"] == "this contact"


def test_boxes_are_isolated(memory):
    from ingestion.retrieval import retrieve_similar

    for r in retrieve_similar("professional", "Khana kha liya babu?", k=5, max_distance=2):
        assert r["conversation_id"] == "professional-work"
    assert retrieve_similar("friend", "hi") == []  # empty box -> persona only, no crash
