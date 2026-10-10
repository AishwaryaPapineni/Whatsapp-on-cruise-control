#!/usr/bin/env bash
# Starts Chroma (if needed), the bridge (:5001), the console (:8501) and the WhatsApp client. Ctrl+C stops all.
set -e
cd "$(dirname "$0")/.."
./scripts/setup_session_2_2.sh
python3 bridge/bridge.py & BR=$!
streamlit run console/app.py --server.headless true & CO=$!
sleep 4
( cd whatsapp && node baileys_client.js ) & WA=$!
trap 'kill $BR $CO $WA 2>/dev/null' EXIT INT TERM
wait
