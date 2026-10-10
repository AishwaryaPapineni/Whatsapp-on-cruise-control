import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.update(EMBEDDER="hash", LLM_PROVIDER="offline", CHROMA_MODE="memory")

WIFE, FAMILY, WORK, FRIEND = ("919812345671", "919812345673", "919812345672", "919812345670")


def jid(n: str) -> str:
    return f"{n}@s.whatsapp.net"


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    """Every test gets its own settings, kill switch, logs and in-memory Chroma."""
    import chromadb

    import agent.context as cx
    import agent.decision_engine as de
    import agent.pipeline as pl
    import agent.settings as st
    import ingestion.embedder as em

    settings = tmp_path / "settings.json"
    settings.write_text('{"dry_run": true, "quiet_hours": ""}', encoding="utf-8")
    monkeypatch.setattr(st, "SETTINGS_PATH", settings)
    monkeypatch.setattr(st, "KILL_SWITCH_PATH", tmp_path / "kill_switch.flag")
    monkeypatch.setattr(st, "LOGS_DIR", tmp_path / "logs")
    monkeypatch.setattr(de, "LOGS_DIR", tmp_path / "logs")
    monkeypatch.setattr(cx, "LOGS_DIR", tmp_path / "logs")
    monkeypatch.setattr(de, "DECISION_LOG_PATH", tmp_path / "logs" / "decision_log.jsonl")
    monkeypatch.setattr(pl, "LOGS_DIR", tmp_path / "logs")
    monkeypatch.setattr(pl, "CONSOLE_FEED_PATH", tmp_path / "logs" / "console_feed.jsonl")
    client = chromadb.EphemeralClient()
    for c in client.list_collections():
        client.delete_collection(c.name if hasattr(c, "name") else c)
    em.set_client(client)
    yield tmp_path


@pytest.fixture
def ctx(tmp_path):
    from agent.context import ChatContext

    return ChatContext(tmp_path / "ctx")


@pytest.fixture
def memory():
    """A small history brain: wife + family share the family box, work is professional."""
    from ingestion.embed_to_chroma import embed

    pairs = [
        {"conversation_id": "wife", "their_message": "Khana kha liya?", "my_reply": "Haan babu kha liya 😘", "timestamp": "1"},
        {"conversation_id": "wife", "their_message": "Kahan ho?", "my_reply": "Walking walking babu", "timestamp": "2"},
        {"conversation_id": "family", "their_message": "Khana khaya beta?", "my_reply": "Haan mummy kha liya 😊", "timestamp": "3"},
        {"conversation_id": "family", "their_message": "Reached home?", "my_reply": "Yes reached 😊", "timestamp": "4"},
        {"conversation_id": "professional-work", "their_message": "Uploaded the final video", "my_reply": "Bro loved the editing ❤\ufe0f", "timestamp": "5"},
    ]
    rel_map = {"_default": "unknown", "wife": "family", "family": "family", "professional-work": "professional"}
    embed(pairs, rel_map, reset=True)
    return pairs
