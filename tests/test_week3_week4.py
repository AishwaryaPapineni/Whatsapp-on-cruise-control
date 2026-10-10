"""Week 3 (router, decision engine, generator, guardrail) + Week 4 (pipeline, bridge, settings)."""
import json
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from conftest import FAMILY, FRIEND, WIFE, WORK, jid

NOON = datetime(2026, 10, 10, 12, 0, tzinfo=ZoneInfo("Asia/Kolkata"))


# ---------------- router (session tests kept verbatim in spirit) ----------------
@pytest.fixture
def temp_map(tmp_path):
    p = tmp_path / "relationship_map.json"
    p.write_text(json.dumps({"_default": "unknown", "919812345670": "friend", "919812345671": "family", "919812345672": "professional"}))
    return str(p)


def test_router_session_contract(temp_map):
    from agent.router import resolve_relationship as r

    assert r("919812345671@s.whatsapp.net", temp_map) == ("family", "history_family")
    assert r("999999999999@s.whatsapp.net", temp_map) == ("unknown", "history_unknown")
    assert r("1234567890-123456@g.us", temp_map) == ("group", None)
    assert r("", temp_map) == r("@", temp_map) == r("   ", temp_map) == ("unknown", "history_unknown")


def test_router_device_suffix_lid_and_broken_map(temp_map, tmp_path):
    from agent.router import resolve_relationship as r

    assert r("919812345671:12@s.whatsapp.net", temp_map) == ("family", "history_family")
    assert r("161234567890@lid", temp_map) == ("unknown", "history_unknown")  # the client must resolve LIDs first
    bad = tmp_path / "bad.json"
    bad.write_text("{not json")
    assert r("919812345671@s.whatsapp.net", str(bad)) == ("unknown", "history_unknown")


def test_contact_profile_gives_wife_her_persona():
    from agent.router import resolve_contact

    c = resolve_contact(jid(WIFE))
    assert (c["relationship"], c["persona"], c["conversation_id"]) == ("family", "wife", "wife")
    assert resolve_contact(jid(FRIEND))["persona"] == "friends"  # "friend" -> persona key "friends"


# ---------------- decision engine ----------------
def d(text, who=FAMILY, rel="family", ctx=None, now=NOON, classifier=None, **kw):
    from agent.decision_engine import decide

    return decide({"jid": jid(who), "text": text, **kw}, rel, context=ctx, now=now,
                  classifier=classifier or (lambda t: ("safe_to_auto_reply", None)))


@pytest.mark.parametrize("text,rel,kw,ok", [
    ("I already sent this update.", "family", {"from_me": True}, False),
    ("What time are we meeting?", "group", {}, False),
    ("Hello, are you available?", "unknown", {}, False),
    ("", "family", {"message_type": "image"}, False),
    ("Please share this important update.", "friend", {"is_forwarded": True}, False),
    ("thanks", "family", {}, False),
    ("Okay!!!", "family", {}, False),
    ("Can you send me 5000 rupees?", "professional", {}, False),
    ("Beta paise bhej do", "family", {}, False),
    ("OTP aaya kya?", "family", {}, False),
    ("Papa hospital mein hai", "family", {}, False),
    ("😂😂", "family", {}, False),
    ("Tumne kha liya khana?", "family", {}, True),
    ("Reached home safely", "family", {}, True),
])
def test_session_gates(ctx, text, rel, kw, ok):
    assert d(text, rel=rel, ctx=ctx, **kw).should_reply is ok


@pytest.mark.parametrize("text", ["Are you free for dinner tonight?", "Want to catch a movie this weekend?",
                                  "Can we sync tomorrow on the project update?", "I am going to be late today, can you pick me up?",
                                  "diwali pe ghar aaoge kya?", "I have a new video ready when can we connect?"])
def test_plans_are_held_never_confirmed(ctx, text):
    r = d(text, ctx=ctx)
    assert r.should_reply and r.mode == "hold"


def test_ai_called_only_when_unclear_and_fails_closed(ctx):
    calls = []

    def clf(t):
        calls.append(t)
        return ("needs_human_money_or_serious", "LLM error: 503 UNAVAILABLE")

    assert d("Good morning", ctx=ctx, classifier=clf).should_reply and calls == []  # regex was enough
    r = d("haan wahi wala", ctx=ctx, classifier=clf)
    assert not r.should_reply and r.reason == "intent check failed closed" and calls == ["haan wahi wala"]
    assert d("sab theek?", ctx=ctx, classifier=lambda t: ("plan_or_commitment", None)).mode == "hold"


def test_owner_active_rate_limit_quiet_hours_kill_switch(ctx, isolated):
    import agent.settings as st

    ctx.add(jid(WIFE), "me", "aa raha hu", when=NOON)
    assert "real you" in d("Kahan ho?", WIFE, ctx=ctx).reason
    for _ in range(6):
        ctx.add(jid(FAMILY), "agent", "😊", when=NOON)
    assert "rate limit" in d("Good morning", ctx=ctx).reason
    st.save_settings({"quiet_hours": "23-7"})
    assert "quiet hours" in d("Good morning", WORK, "professional", ctx=ctx, now=NOON.replace(hour=2)).reason
    st.set_kill_switch(True)
    assert d("Good morning", WORK, "professional", ctx=ctx).reason == "kill switch active"


def test_professional_question_held_by_policy(ctx):
    assert d("Feedback on the deck?", WORK, "professional", ctx=ctx).mode == "hold"


# ---------------- guardrail ----------------
@pytest.mark.parametrize("incoming,reply", [  # persona/sample_outputs.v1.md
    ("I am going to be late today, can you pick me up?", "Haan pintlu, main lene aa jaunga! Bas office se nikalte hi mujhe call kar dena 😘🚗"),
    ("diwali pe ghar aaoge kya?", "Haan bilkul! Flight tickets booked hain, coming home on 10th Nov 🪔✨ Can't wait to celebrate together! 😊"),
    ("I have a new video ready when can we connect?", "Awesome! Let's connect at 4 PM today? Link send karo, looking forward to it! 🔥"),
])
def test_guardrail_blocks_v1_sample_outputs(incoming, reply):
    from agent.guardrail import check

    assert check(reply, incoming, "", "hold", 40)


@pytest.mark.parametrize("reply", ["Ek min babu, check karke batata hu", "Let me check and get back", "Good take rest 😊", "Haan babu kha liya 😘"])
def test_guardrail_allows_safe(reply):
    from agent.guardrail import check

    assert check(reply, "x", "", "reply", 40) == []


def test_guardrail_allows_time_mentioned_in_context():
    from agent.guardrail import check

    assert check("Okay 10:00 tak", "kab tak?", "Them: meeting 10:00 tak hai", "reply", 40) == []
    assert check("Okay 11:30 tak", "kab tak?", "", "reply", 40)


# ---------------- pipeline (stages 1-8) ----------------
def test_pipeline_reply_uses_both_brains_and_context(memory, ctx):
    from agent.pipeline import process_message

    process_message({"jid": jid(WIFE), "text": "Good morning baby"}, context=ctx, now=NOON)
    t = process_message({"jid": jid(WIFE), "text": "Khana kha liya?"}, context=ctx, now=NOON)
    assert t["decision"] == "reply" and t["persona"] == "wife"
    assert [r["role"] for r in t["short_term_context"]] == ["them"]  # last N messages of THIS chat
    assert t["retrieval_trace"][0]["conversation_id"] == "wife"
    assert "pintlu" in t["prompt"] and "THE CONVERSATION SO FAR" in t["prompt"]
    assert 3 <= t["delay_seconds"] <= 12 and t["should_send"]


def test_pipeline_family_prompt_has_no_wife_content(memory, ctx):
    from agent.pipeline import process_message

    t = process_message({"jid": jid(FAMILY), "text": "Khana khaya beta?"}, context=ctx, now=NOON)
    assert "babu" not in t["prompt"] and "pintlu" not in t["prompt"]


def test_reckless_model_falls_back_to_holding_reply(memory, ctx):
    from agent.pipeline import process_message

    t = process_message({"jid": jid(WIFE), "text": "Khana kha liya?"}, context=ctx, now=NOON,
                        llm=lambda p: "Haan pakka, I'll come at 5 pm and send ₹2000")
    assert [a["attempt"] for a in t["attempts"]] == [1, 2, "fallback"] and t["decision"] == "hold"
    assert "₹" not in t["reply"]


def test_model_crash_is_safe(memory, ctx):
    from agent.pipeline import process_message

    def boom(p):
        raise TimeoutError("quota exceeded")

    t = process_message({"jid": jid(WIFE), "text": "Khana kha liya?"}, context=ctx, now=NOON, llm=boom)
    assert t["attempts"][-1]["attempt"] == "fallback" and t["reply"]
    assert "quota" in t["attempts"][0]["problems"][0]


# ---------------- settings + bridge ----------------
def test_settings_fail_safe_to_dry_run(isolated):
    import agent.settings as st

    st.SETTINGS_PATH.write_text("{broken")
    assert st.is_dry_run() is True


def test_bridge_contract_token_and_ack(memory, monkeypatch, isolated):
    import bridge.bridge as br
    from agent.context import ChatContext

    monkeypatch.setattr(br, "TOKEN", "t0k")
    c = br.app.test_client()
    assert c.post("/process", json={"jid": jid(WIFE), "text": "hi"}).status_code == 401
    h = {"X-Bridge-Token": "t0k"}
    r = c.post("/process", json={"jid": jid(WIFE), "text": "Good morning", "message_type": "text"}, headers=h).get_json()
    assert set(r) >= {"should_reply", "reply", "relationship", "reason", "mode", "delay_seconds", "trace_id", "dry_run"}
    assert r["should_reply"] and r["relationship"] == "family"
    c.post("/sent", json={"jid": jid(WIFE), "reply": r["reply"], "trace_id": r["trace_id"]}, headers=h)
    assert ChatContext().last(jid(WIFE), 5)[-1]["role"] == "agent"
    assert c.get("/health").get_json()["dry_run"] is True
