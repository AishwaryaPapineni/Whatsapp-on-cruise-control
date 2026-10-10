#!/usr/bin/env bash
# Session 1.1 Part 0 + later-week dependencies, in one check. Nothing silently skipped.
cd "$(dirname "$0")/.."
ok(){ echo "✅ $1"; }; no(){ echo "❌ $1"; }
echo "== Core =="
if node -v >/dev/null 2>&1; then v=$(node -v); m=${v#v}; m=${m%%.*}; [ "$m" -ge 20 ] && ok "Node $v" || no "Node $v -- Baileys 7 needs Node 20+ (guide says 18+)"; else no "Node not found"; fi
python3 --version >/dev/null 2>&1 && ok "$(python3 --version)" || no "python3 not found"
python3 -m pip --version >/dev/null 2>&1 && ok "pip" || no "pip not found (try: python3 -m ensurepip)"
git --version >/dev/null 2>&1 && ok "$(git --version)" || no "Git not found"
if code --version >/dev/null 2>&1; then ok "VS Code CLI"
  code --list-extensions | grep -qi "github.copilot$" && ok "GitHub Copilot" || no "GitHub Copilot missing"
  code --list-extensions | grep -qi "github.copilot-chat" && ok "GitHub Copilot Chat" || no "GitHub Copilot Chat missing"
  code --list-extensions | grep -qi "ms-python.python" && ok "Python extension" || no "Python extension missing"
else no "'code' command not found (Cmd/Ctrl+Shift+P → Shell Command: Install 'code' command in PATH)"; fi
echo "== Python packages =="
for p in google-genai python-dotenv chromadb sentence-transformers flask streamlit; do python3 -m pip show "$p" >/dev/null 2>&1 && ok "$p" || no "$p (python3 -m pip install -r requirements.txt)"; done
echo "== Project =="
grep -qE "^GEMINI_API_KEY=.+" .env 2>/dev/null && ok "GEMINI_API_KEY set in .env" || no "GEMINI_API_KEY missing in .env (aistudio.google.com → Get API key)"
ls data/raw_export/*.txt >/dev/null 2>&1 && ok "exports in data/raw_export/" || no "no .txt in data/raw_export/ (chat → ⋮ → More → Export chat → Without media)"
curl -fs http://localhost:8000/api/v2/heartbeat >/dev/null && ok "Chroma server on :8000" || no "Chroma not running (./scripts/setup_session_2_2.sh)"
[ -d whatsapp/node_modules/@whiskeysockets/baileys ] && ok "Baileys installed" || no "Baileys (cd whatsapp && npm install)"
python3 -c "import json;print('✅ dry_run is ON' if json.load(open('config/settings.json')).get('dry_run',True) else '⚠️  dry_run is OFF -- the bot WILL send')"
[ -f kill_switch.flag ] && echo "⏸  kill_switch.flag present -- nothing will be processed"
echo "Reminder: link a DEDICATED/secondary WhatsApp number, never your primary."
