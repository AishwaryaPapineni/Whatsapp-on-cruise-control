"""Short-term context: the last N messages of THIS chat (both sides).

From the live-session brief: "...the last N messages of the current chat are pulled in
as short-term context -> RAG retrieves your most similar past replies as long-term style".

Why both: RAG answers "how do I usually reply to messages like this?" (style), but it
knows nothing about the conversation happening right now. Without short-term context,
"haan wahi" or "kitne baje?" have no referent and the model guesses. With it, the model
sees what was just said -- including what YOU typed by hand a minute ago.

Also tracks two signals the decision engine needs:
  * when you (the real you) last typed in a chat -> stay silent while you're active
  * when the agent last auto-replied -> per-chat rate limit
Stored as small JSONL/JSON files in logs/ (git-ignored) so a bridge restart keeps them.
"""
from __future__ import annotations

import json
import re
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

from agent.settings import LOGS_DIR

_LOCK = threading.Lock()


def _key(jid: str) -> str:
    return re.sub(r"[^0-9A-Za-z]", "_", jid.split("@", 1)[0].split(":", 1)[0]) or "unknown"


class ChatContext:
    def __init__(self, root: Path | None = None):
        self.root = (root or LOGS_DIR) / "context"
        self.state_path = self.root / "_state.json"

    # ---- messages -------------------------------------------------------
    def add(self, jid: str, role: str, text: str, when: datetime | None = None) -> None:
        """role: 'them' | 'me' (typed by you) | 'agent' (auto-reply sent)"""
        if not text or not text.strip():
            return
        self.root.mkdir(parents=True, exist_ok=True)
        row = {"at": (when or datetime.now(timezone.utc)).isoformat(), "role": role, "text": text.strip()}
        with _LOCK, (self.root / f"{_key(jid)}.jsonl").open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
        if role == "me":
            self._set("owner_active", jid, row["at"])
        if role == "agent":
            self._push("auto_replies", jid, row["at"])

    def last(self, jid: str, n: int) -> list[dict]:
        path = self.root / f"{_key(jid)}.jsonl"
        if not path.exists() or n <= 0:
            return []
        lines = path.read_text(encoding="utf-8").splitlines()[-n:]
        return [json.loads(l) for l in lines if l.strip()]

    # ---- signals --------------------------------------------------------
    def _state(self) -> dict:
        try:
            return json.loads(self.state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}

    def _write(self, state: dict) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(json.dumps(state, indent=1), encoding="utf-8")

    def _set(self, field: str, jid: str, value: str) -> None:
        with _LOCK:
            st = self._state()
            st.setdefault(field, {})[_key(jid)] = value
            self._write(st)

    def _push(self, field: str, jid: str, value: str) -> None:
        with _LOCK:
            st = self._state()
            lst = st.setdefault(field, {}).setdefault(_key(jid), [])
            lst.append(value)
            st[field][_key(jid)] = lst[-50:]
            self._write(st)

    def minutes_since_owner(self, jid: str, now: datetime) -> float | None:
        v = self._state().get("owner_active", {}).get(_key(jid))
        return None if not v else (now - datetime.fromisoformat(v)).total_seconds() / 60

    def auto_replies_last_hour(self, jid: str, now: datetime) -> int:
        since = now - timedelta(hours=1)
        return sum(1 for t in self._state().get("auto_replies", {}).get(_key(jid), []) if datetime.fromisoformat(t) >= since)


def format_for_prompt(rows: list[dict]) -> str:
    label = {"them": "Them", "me": "Me", "agent": "Me"}
    return "\n".join(f"{label.get(r['role'], r['role'])}: {r['text']}" for r in rows)
