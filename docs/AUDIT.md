# Audit report — WhatsApp Cruise Control (rebuild)

**Scope:** the full project document (3 PDFs), your session code (Week 2.1 `parse_export` / `validate_pairs`, Week 2.2, 3.1, 3.2, 4.1/4.2 zips), your real `processed_pairs.jsonl` (1,029 pairs), `persona.json`, style signals and the Week 1 sample outputs. The rebuild in this repo was checked against all of it.
**Date:** 10 Oct 2026

## 1. What was actually verified

| Check | Evidence |
|---|---|
| Python test suite | `pytest` → **57 passed** (parsing, noise, quarantine, validator, persona builder, embed idempotency, retrieval isolation, router contract, every decision layer, guardrail vs v1 outputs, full pipeline, bridge contract) |
| Node test suite | `cd whatsapp && npm test` → **6 passed** (text/type/forwarded extraction, LID → phone routing, echo detection, delay clamp) |
| Real data cleaning | `clean_pairs.py` on your 1,029 pairs → **888 kept**, 53 noise lines removed from 41 pairs, 19 empty/ack pairs dropped, **122 sensitive pairs quarantined**. `validate_pairs.py` → ✅ |
| Real Chroma server | `chroma run` on :8000 → `history_family` 684, `history_professional` 204, re-run idempotent |
| Wife/family leak | family query before fix: **5 / 5** results from your wife's chat; after: **5 / 5** from the family chat (`private/` evidence, test `test_private_conversation_never_leaks`) |
| Bridge over HTTP | Flask on 127.0.0.1:5001: 401 without token; 12-message simulated conversation incl. your own typed message and `/sent` acks |
| Baileys client | boots on Baileys 7.0.0-rc14 (Node 22); the connection attempt fails only because this build sandbox has no route to WhatsApp |
| Console | renders all 9 stages for a real message (`private/console_screenshot_REAL_DATA.png`, kept private: it shows your chats) |

**Not verifiable from the build sandbox (your first steps, see GO_LIVE.md):** a real Gemini call (no network; your session `decision_log.jsonl` shows `gemini-3.5-flash` did answer for you); the multilingual mpnet model (HuggingFace unreachable, so retrieval quality was tested with an offline stand-in embedder that matches spelling, not meaning); a live WhatsApp link (needs your phone).

## 2. Findings in the session code and data

| # | Sev. | Finding | Evidence | Fix in rebuild |
|---|---|---|---|---|
| F1 | 🔴 | **Plans get confirmed.** The decision engine has no plan rule. Your `decision_log.jsonl` shows "Are you free for dinner tonight?" and "Want to catch a movie this weekend?" → `reply · passed all gates`. Combined with the v1 sample outputs ("main lene aa jaunga!", "Flight tickets booked… 10th Nov", "connect at 4 PM today"), this breaks **"Never confirm plans without me"**. | decision_log.jsonl, sample_outputs.v1.md | Plan intent → **HOLD** (non-committal reply) + LLM label `plan_or_commitment` + output **guardrail** (blocks all 3 v1 replies) |
| F2 | 🔴 | **Wife → `family` box leaks into parents' replies.** `contact_relationship_map.json` maps `wife` to `family` (correct for the 4 boxes), but nothing separates conversations inside a box, so a parent's "Khana kha liya?" retrieved 5/5 examples like "Khaya motu ne" and the generator used the generic family tone. | retrieval run on real data | `config/contact_profiles.json`: per-number persona (`wife`) + own `conversation_id` searched first + `_private_conversations` excluded for everyone else. The 4 boxes are unchanged |
| F3 | 🔴 | **Money and IDs in memory.** 81 pairs matched money terms in the guide's own sense (tax challan Rs 29,810, "50 from sbi and 50 from icici", holdings, PAN fragments, a phone number). Retrieval would hand these to the model as "how I reply", and Week 2's checklist says to push this file to a public repo. | processed_pairs.jsonl | `config/sensitive.py`: money/OTP/ID pairs → `data/quarantine_pairs.jsonl` (never embedded); phones/emails/links/PAN scrubbed; pair files **git-ignored** |
| F4 | 🔴 | **Console shows the wrong mode.** `settings.json` has `"dry_run": false` (bot LIVE) while `console/app.py` reads `config/mode.txt` → shows **DRY_RUN**. | Files.zip | One source of truth: `config/settings.json` for bot, bridge and console; shipped with `dry_run: true`; console toggles write the same file |
| F5 | 🟠 | **Call-log noise leaked; validator blind to it.** 18+ pairs contained "Video call, 47 sec", "Missed group call, 2 invited", "Answered on other device" (LRM-prefixed). `validate_pairs.py` only checks "omitted/<media/deleted" → reported **0 noise**. | v1 validator run | Shared noise list (`config/constants.py`) used by parser *and* validator; call lines matched as whole lines; noise removed line-by-line inside turns |
| F6 | 🟠 | **The guide's "Voice call" substring fix would delete real messages** ("video call kar lein?"). | test | Whole-line regex `CALL_LOG_LINE` |
| F7 | 🟠 | **Bridge open to the network.** Flask binds `0.0.0.0:5001` with no auth: anyone on your Wi-Fi could POST `/process` and get replies in your voice. | bridge.py | Binds 127.0.0.1, optional `BRIDGE_TOKEN` header |
| F8 | 🟠 | **LID chats route as strangers.** Baileys 7 addresses many 1:1 chats as `…@lid`; the router splits the LID digits and finds no phone key → `unknown` → silence; the allowlist check fails the same way. `resolveSendJid` only fixed the *send* side. | baileys_client.js | Client resolves LID → phone (`remoteJidAlt`, then `lidMapping.getPNForLID`) *before* routing; router treats raw LIDs as unknown |
| F9 | 🟠 | **Only the first message of each batch is processed** (`event.messages[0]`). | baileys_client.js | Loops every message; dedupes ids; skips post-reconnect backlog |
| F10 | 🟠 | **Your own typed messages are dropped** (`[SKIP] own message`), so the agent can't see that you're in the chat and can talk over you. No short-term context exists at all, although the live-session brief requires "the last N messages of the current chat". | baileys_client.js, brief | Client forwards `from_me`; `agent/context.py` keeps last-N per chat + "owner active" + rate-limit signals; pending reply cancelled if you type during the delay |
| F11 | 🟠 | **Kill switch / dry_run checked only before the 3–12 s delay.** Pressing the kill switch while a reply is waiting still sends it. | baileys_client.js | Re-checked after the delay, right before `sendMessage` |
| F12 | 🟠 | **Every message costs a Gemini call; 503s silence the bot.** The decision engine calls the LLM for all messages that pass the cheap gates; your log shows three `503 UNAVAILABLE` fail-closed ignores in one run. | decision_log.jsonl | Regex intent first; AI only for unclear messages (guide: "one AI call only if truly ambiguous"); money/serious caught before AI |
| F13 | 🟡 | **"friend" vs "friends".** Router/collections say `friend`, persona.json says `friends` → tone silently empty for every friend. Your persona has no `friends` section at all. | generator.py | Mapping in `agent/router.py`; persona v2 has `friends` + `wife` |
| F14 | 🟡 | **`ingestion/retrieval.py` missing** — `generator.py` imports `retrieve_similar` from it; the bridge also retrieved twice per message. | zips | Written; one retrieval per message, returned in the trace |
| F15 | 🟡 | **Unstable Chroma ids.** `stable_id` used the pair's index in the file; after any cleaning every later id shifts → stale duplicates. | embed_to_chroma.py | id = hash(conversation, timestamp, texts) + sync deletes stale ids |
| F16 | 🟡 | **Baileys 7 is ESM-only;** the CommonJS client works on Node 22.12+ only (guide says Node 18+). `makeInMemoryStore` no longer exists in v7. | npm metadata, import test | ES-module client, Node 20+ in `engines` and healthcheck |
| F17 | 🟡 | **Style numbers mismatch reality.** persona.json uses one global "avg 47 words"; your real reply medians are **3 (wife), 3 (family), 6 (work)** words. Hinglish: **31 %** with your wife vs 2–3 % elsewhere. Guide's LINE_PATTERN is Android-only → 0 matches on your iOS exports. | from_pairs signals | Per-relationship `style` blocks; build_persona handles iOS + LRM |
| F18 | 🟡 | Week 1 deliverable needs **5** sample outputs; v1 has 3, and all 3 break a hard rule. | sample_outputs.v1.md | `persona/test_persona.py` generates 6 with guardrail verdicts |
| F19 | 🟡 | `history_friend` and `history_unknown` are empty — no friend chat exported (Week 2 checklist wants all four populated). | embed summary | Export one friend chat and add it to the map |
| F20 | ℹ️ | `validate_pairs.py` prints mojibake (`âœ…`) — file saved with the wrong encoding. | attachment | Rewritten UTF-8 |

## 3. Residual risks (open)

1. **Regex intent misses phrasing.** Mitigated by AI for unclear messages, HOLD for plans, guardrail on output, conservative defaults. Run a dry-run week and add misses as tests.
2. **The money filter is deliberately broad** ("cost", "bill", "tax" in non-money talk) → some silence or over-quarantine (122 pairs). Review `data/quarantine_pairs.jsonl` once.
3. **`MAX_DISTANCE=0.6` is a starting point.** Check real mpnet distances in `retrieval_demo.py` and tune.
4. **Data to Google.** Retrieved pairs + recent context go to the Gemini API. Check the current free-tier terms (free-tier content may be used to improve Google products).
5. **Account risk.** Baileys is unofficial; use the dedicated number (the guide insists), keep the rate limit low.
6. **Consent.** Contacts don't know an agent is replying. Consider telling close contacts.
7. **Short-term context is local JSONL** in `logs/context/` — personal data, git-ignored; delete when done.

## 4. Scorecard against the problem statement

| Goal | Status |
|---|---|
| Live agent on real WhatsApp | 🟡 Built + boot-tested; needs your QR scan and key |
| Sounds like you | 🟡 Real verbatim replies + measured per-relationship style + own-chat retrieval; judge with `test_persona.py` |
| Knows when to stay silent | ✅ 5 layers + guardrail; all session cases + hard rules tested |
| Public repo, live console, demo | ✅ repo (private data ignored), console, batch test · 🟡 recording is yours |
| Free tier only | ✅ Gemini free, local Chroma + mpnet, Baileys, Streamlit |
