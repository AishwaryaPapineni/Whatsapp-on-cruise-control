"""Session 4.2 -- the Cruise Control Console (Streamlit).

The session console showed decision, reason, reply and the retrieval trace. This version
keeps that layout and adds what the brief promises ("shows every step live"):
  * the 8 pipeline stages per message, incl. the NEW short-term context step
  * which layer of the decision engine decided, and why
  * retrieval trace with distance and scope (this contact vs relationship box)
  * the exact prompt, guardrail attempts, the delay, and whether it was really SENT
  * mode read from config/settings.json -- the SAME file the Baileys client reads
    (the old console read config/mode.txt and could show DRY_RUN while the bot was LIVE)
  * controls: kill switch, dry-run toggle, sandbox to test any contact

Run:  streamlit run console/app.py
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from agent.settings import is_kill_switch_active, load_settings, save_settings, set_kill_switch  # noqa: E402

try:
    from streamlit_autorefresh import st_autorefresh
except ImportError:  # pragma: no cover
    st_autorefresh = None

LOG_PATH = ROOT / "logs" / "console_feed.jsonl"
RELATIONSHIP_COLORS = {"family": "#2e7d32", "friend": "#1565c0", "professional": "#6a1b9a", "unknown": "#6b7280", "group": "#6b7280"}
DECISION_STYLE = {"reply": ("#16a34a", "REPLY"), "hold": ("#d97706", "HOLD · non-committal"), "ignore": ("#6b7280", "IGNORE · left for you")}
STAGES = ["Message In", "Router", "Decision Engine", "Short-term Context", "Retrieval", "Persona Injection", "Generation", "Human-like Delay", "Send"]


def load_logs(limit: int = 30) -> list[dict]:
    if not LOG_PATH.exists():
        return []
    traces, acks = {}, set()
    for line in LOG_PATH.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(row, dict):
            continue
        if row.get("sent_ack"):
            acks.add(row.get("id"))
        elif row.get("id"):
            traces[row["id"]] = row
    out = list(traces.values())[-limit:][::-1]
    for t in out:
        t["sent"] = t["id"] in acks
    return out


def badge(text: str, color: str) -> str:
    return (f"<span style='display:inline-block;background:{color};color:white;border-radius:999px;"
            f"padding:0.15rem 0.6rem;font-size:0.78rem;font-weight:600;margin-right:0.4rem'>{text}</span>")


def stage_line(t: dict) -> str:
    reached = 3 if t.get("decision") == "ignore" else (9 if t.get("sent") else 8)
    return " → ".join(f"**{s}**" if i < reached else f"<span style='color:#9ca3af'>{s}</span>" for i, s in enumerate(STAGES))


def render(t: dict) -> None:
    rel = str(t.get("relationship", "unknown"))
    color, label = DECISION_STYLE.get(t.get("decision", "ignore"), DECISION_STYLE["ignore"])
    status = "📤 sent" if t.get("sent") else ("🧪 dry run" if t.get("reply") and t.get("dry_run") else "")
    st.markdown("---")
    st.markdown(badge(rel, RELATIONSHIP_COLORS.get(rel, "#6b7280")) + badge(label, color) +
                f"<b>{t.get('contact_name', t.get('jid', ''))}</b> · “{t.get('text', '')[:90]}” {status}", unsafe_allow_html=True)
    st.caption(f"{t.get('timestamp', '')[:19]} · persona `{t.get('persona', '')}` · {t.get('model', '')}")
    st.markdown(stage_line(t), unsafe_allow_html=True)
    st.write(f"**Reason:** {t.get('reason', '')}  _( {t.get('layer', '')} )_")
    if t.get("reply"):
        st.info(f"{t['reply']}   ⏱ {t.get('delay_seconds', 0)}s")
    with st.expander("decision layers · short-term context · retrieval trace · prompt"):
        if t.get("checks"):
            st.table([{"layer": c["layer"], "result": c["result"], "why": c["reason"]} for c in t["checks"]])
        if t.get("short_term_context") is not None and t.get("decision") != "ignore":
            st.markdown("**Short-term context (this chat, most recent last)**")
            st.code("\n".join(f"{r['role']}: {r['text']}" for r in t["short_term_context"]) or "(no earlier messages)", language="text")
        if t.get("retrieval_trace") is not None and t.get("decision") != "ignore":
            st.markdown("**Retrieval trace (history brain)**")
            if t["retrieval_trace"]:
                st.table([{"distance": r.get("distance"), "scope": r.get("scope"), "they said": r.get("their_message"),
                           "I replied": r.get("my_reply")} for r in t["retrieval_trace"]])
            else:
                st.write("No similar past exchange -- persona only.")
        for a in t.get("attempts", []):
            st.write(f"attempt {a['attempt']}: “{a.get('draft')}” — " + ("✅" if not a["problems"] else "⛔ " + "; ".join(a["problems"])))
        if t.get("prompt"):
            st.code(t["prompt"], language="markdown")


st.set_page_config(page_title="Cruise Control Console", page_icon="💬", layout="wide")
if st_autorefresh is not None:
    st_autorefresh(interval=3000, key="console_live_feed")

settings = load_settings()
with st.sidebar:
    st.title("🚗 Cruise Control")
    killed = is_kill_switch_active()
    st.metric("Mode", "⏸ KILL SWITCH" if killed else ("🧪 DRY_RUN" if settings.get("dry_run", True) else "🟢 LIVE"))
    if killed:
        if st.button("▶\ufe0f Release kill switch", use_container_width=True):
            set_kill_switch(False); st.rerun()
    elif st.button("⏸ KILL SWITCH", type="primary", use_container_width=True):
        set_kill_switch(True); st.rerun()
    live = st.toggle("Live sending (dry_run off)", value=not settings.get("dry_run", True))
    if live == settings.get("dry_run", True):
        save_settings({"dry_run": not live}); st.rerun()
    st.caption("Both read config/settings.json and kill_switch.flag -- the same files the Baileys client checks before every send.")
    entries = load_logs(500)
    st.subheader("Metrics")
    st.metric("Messages processed", len(entries))
    st.metric("Replies actually sent", sum(1 for e in entries if e.get("sent")))
    st.metric("Holding replies", sum(1 for e in entries if e.get("decision") == "hold"))
    st.metric("Left for you", sum(1 for e in entries if e.get("decision") == "ignore"))

feed, sandbox, stats = st.tabs(["📡 Live decision feed", "🧪 Sandbox", "📊 Why not replied"])
with feed:
    rows = load_logs()
    if not rows:
        st.info("waiting for first message...")
    for t in rows:
        render(t)
with sandbox:
    st.write("Run the real pipeline as if a contact texted you. Nothing is sent to WhatsApp.")
    rel_map = json.loads((ROOT / "config" / "relationship_map.json").read_text(encoding="utf-8"))
    numbers = [k for k in rel_map if k != "_default"] + ["919899999999 (unknown)"]
    who = st.selectbox("From", numbers)
    text = st.text_input("Message", "Tumne kha liya khana?")
    if st.button("Run pipeline", type="primary"):
        from agent.pipeline import process_message

        render(process_message({"jid": who.split()[0] + "@s.whatsapp.net", "text": text}))
with stats:
    entries = load_logs(5000)
    st.table(Counter(e.get("reason", "") for e in entries if e.get("decision") == "ignore").most_common(12))
