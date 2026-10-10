#!/usr/bin/env bash
# Stop only the Chroma process we started (never whatever else is on :8000).
cd "$(dirname "$0")/.."
[ -f .chroma_server.pid ] || { echo "No .chroma_server.pid -- nothing to stop"; exit 0; }
PID=$(cat .chroma_server.pid)
kill "$PID" 2>/dev/null && echo "Stopped Chroma (pid $PID)" || echo "Process $PID not running"
rm -f .chroma_server.pid
