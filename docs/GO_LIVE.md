# Go-live runbook

## 1. Things only you can do (couldn't be run in the build sandbox)
1. `cp .env.example .env`, add `GEMINI_API_KEY`, set `BRIDGE_TOKEN` to a random string, then run `python3 quick_key_test.py`.
2. Put your raw exports in `data/raw_export/`, then run `python3 ingestion/parse_export.py --name "अरूण"`. This replaces the pairs I re-cleaned from your old file and gives message-level stats.
3. **Export one friend chat** so `history_friend` isn't empty, and add it to `config/contact_relationship_map.json` as `friend`.
4. Put **real numbers** in `config/relationship_map.json` and `config/contact_profiles.json` (the current ones are the course placeholders), then run `python3 ingestion/validate_phone_relationship_map.py`.
5. Run `python3 ingestion/embed_to_chroma.py --reset` with the real model (`EMBEDDER=st`; the first run downloads ~1 GB).
6. Run `python3 ingestion/retrieval_demo.py` and look at the distances. Set `MAX_DISTANCE` in `.env` just above where good matches end (start around 0.5–0.6).
7. Run `python3 persona/test_persona.py`. If replies sound generic, add more real lines to `persona.json` → `example_replies`.
8. Skim `data/quarantine_pairs.jsonl` once to see what was kept out of memory.

## 2. Dry-run week
1. Run `./scripts/run_all.sh`. On the **dedicated** phone, go to Linked devices → Link a device → scan the QR.
2. Keep `config/settings.json → "dry_run": true`. Message the dedicated number from your main phone (temporarily map your main number to each relationship in turn).
3. Review every trace in the console at http://localhost:8501. For each miss, add a test in `tests/`, then fix `agent/decision_engine.py`, `persona.json` or `settings.json`.

## 3. Live
Flip the console toggle "Live sending", or set `"dry_run": false`. The **KILL SWITCH** button (or `touch kill_switch.flag`) stops everything immediately, including replies already waiting out their delay.

## 4. Record the demo (public proof)
Record the console next to the phone. Script:
1. Wife: "Tumne kha liya khana?" → 🟢 reply in her tone. Open the trace: it shows her own chat retrieved and the short-term context.
2. Family: "diwali pe ghar aaoge kya?" → 🟡 holding reply (hard rule).
3. Family: "Beta paise bhej do" → ⚪ left for you (money).
4. Unknown number, then a group message → ⚪ ignored.
5. You type in a chat → the agent stays quiet there.
6. Press the KILL SWITCH → nothing more is processed.

Use demo or consenting contacts on screen. Traces show real chat text.

## 5. Publish
`git status --ignored` must list `data/`, `logs/`, `private/`, `auth_info_baileys/`, `.env` and `chroma_data/` as ignored before you push. The Week 2 checklist asks you to push `processed_pairs.jsonl`. **Don't**, because it contains your family's and colleagues' messages. Push the code, the maps (with placeholder numbers) and screenshots of consenting or demo chats instead.
