#!/usr/bin/env bash
# Session 2.2 Part 0.5 -- install Chroma + embeddings if missing, start `chroma run` once, wait for heartbeat.
set -u
cd "$(dirname "$0")/.."
PORT="${CHROMA_PORT:-8000}"
# 1. install only what's missing
for pkg in chromadb sentence-transformers; do
  if python3 -m pip show "$pkg" >/dev/null 2>&1; then echo "✅ $pkg already installed"
  else echo "📦 installing $pkg"; python3 -m pip install "$pkg" || exit 1; fi
done
# 2. is the port free / already a healthy chroma?
if lsof -i :"$PORT" >/dev/null 2>&1; then
  if curl -fs "http://localhost:$PORT/api/v2/heartbeat" >/dev/null; then echo "✅ Chroma already running on :$PORT"; exit 0
  else echo "❌ Port $PORT is used by another process. Free it or set CHROMA_PORT=8001 (and use it everywhere)."; exit 1; fi
fi
nohup chroma run --path ./chroma_data --port "$PORT" > logs/chroma.log 2>&1 &
echo $! > .chroma_server.pid
# 3. poll heartbeat
for i in $(seq 1 10); do
  if curl -fs "http://localhost:$PORT/api/v2/heartbeat" >/dev/null; then
    echo "✅ Chroma running on :$PORT (pid $(cat .chroma_server.pid)). Use port $PORT in every script."; exit 0; fi
  sleep 2
done
echo "❌ Chroma did not answer the heartbeat -- see logs/chroma.log"; exit 1
