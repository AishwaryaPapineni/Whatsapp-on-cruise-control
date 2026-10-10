#!/usr/bin/env python3
"""Session 4.1 -- the bridge between the Baileys client (Node) and the brain (Python).

Same contract as the session code: POST /process {jid, text, message_type, is_forwarded,
from_me} -> {should_reply, reply, relationship, reason}. Added fields: mode, delay_seconds,
trace_id, dry_run. Added endpoints: POST /sent (delivery ack), GET /health.

Security changes (docs/AUDIT.md):
  * binds 127.0.0.1, not 0.0.0.0 -- the session bridge accepted requests from anyone on
    your Wi-Fi, who could then have generated replies in your voice
  * optional shared secret: set BRIDGE_TOKEN in .env, the client sends it as X-Bridge-Token
  * one retrieval per message (it ran twice before), full trace in logs/console_feed.jsonl
"""
from __future__ import annotations

import hmac
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, jsonify, request

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
load_dotenv(REPO_ROOT / ".env")

from agent.pipeline import process_message, record_sent  # noqa: E402
from agent.settings import is_dry_run, is_kill_switch_active  # noqa: E402

app = Flask(__name__)
TOKEN = os.getenv("BRIDGE_TOKEN", "")


@app.before_request
def _auth():
    if request.path != "/health" and TOKEN and not hmac.compare_digest(request.headers.get("X-Bridge-Token", ""), TOKEN):
        return jsonify({"error": "bad bridge token"}), 401
    return None


@app.post("/process")
def process():
    payload = request.get_json(silent=True)
    payload = payload if isinstance(payload, dict) else {}
    t = process_message(payload)
    return jsonify({
        "should_reply": t["decision"] in ("reply", "hold") and bool(t.get("should_send")),
        "reply": t.get("reply"),
        "relationship": t.get("relationship"),
        "reason": t.get("reason"),
        "mode": t.get("mode", "reply"),
        "delay_seconds": t.get("delay_seconds", 0),
        "trace_id": t["id"],
        "dry_run": is_dry_run(),
    })


@app.post("/sent")
def sent():
    body = request.get_json(silent=True) or {}
    if body.get("jid") and body.get("reply") and body.get("trace_id"):
        record_sent(str(body["jid"]), str(body["reply"]), str(body["trace_id"]))
    return jsonify({"ok": True})


@app.get("/health")
def health():
    return jsonify({"ok": True, "dry_run": is_dry_run(), "kill_switch": is_kill_switch_active()})


if __name__ == "__main__":
    app.run(host=os.getenv("BRIDGE_HOST", "127.0.0.1"), port=int(os.getenv("BRIDGE_PORT", "5001")), debug=False)
