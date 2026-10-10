# Why each part exists — and how it connects to the problem statement

**The problem in one line:** reply to WhatsApp *as you* — your words, your Hinglish, your emojis, the right tone per person — and know when **not** to reply, using free tools only.

That breaks into five requirements. Every folder in this repo serves one or more of them:

| # | Requirement (problem statement) | Built in | Files |
|---|---|---|---|
| R1 | **Sounds like you**, not a generic assistant | Week 1 + 2 | `persona/`, `ingestion/`, `agent/generator.py` |
| R2 | **Right tone per relationship** | Week 2 + 3 | `config/*map.json`, `config/contact_profiles.json`, `ingestion/retrieval.py` |
| R3 | **Judgment**: when to reply, when to stay silent | Week 3 | `agent/decision_engine.py`, `agent/guardrail.py`, `config/sensitive.py` |
| R4 | **Live on real WhatsApp**, demoable, traceable | Week 4 | `whatsapp/`, `bridge/`, `console/` |
| R5 | **Free tier, personal data handled carefully** | All weeks | Gemini free tier, local Chroma, `.gitignore`, quarantine |

## The idea without jargon (Session 1.1's "done" bar)

> I gave a helper two notebooks. The first is one page about me: how I talk to my wife, my parents and my colleagues, the emojis I use, and two rules I never break (no money talk, never agree to plans without me). The second is a diary of real past chats: "when someone said this, I answered that", kept in separate sections for family, friends and work. When a message arrives, the helper checks who sent it and whether I'd even answer. If yes, it rereads the last few messages of that chat, finds the 3 most similar moments in the right diary section, rereads my page, writes a reply the way I would, waits a few seconds like someone typing, and sends it. Money, emergencies, strangers and group chats it leaves for me.

## Why retrieval, not fine-tuning (Session 1.1 Part 2)

| Guide's reason | How this build honours it |
|---|---|
| Cost / access | No model is trained. Gemini free tier + local Chroma + a free multilingual embedding model |
| Goes stale | Re-run `parse_export → embed_to_chroma` with a new export; `persona.json` is re-read on every message |
| Black box | Every message writes a trace to `logs/console_feed.jsonl`; the console shows the rule that decided, the 3 retrieved pairs with distance, the short-term context and the exact prompt |
| Identity ≠ memory | Persona brain = `persona/persona.json`; history brain = `history_<relationship>` collections. They only meet inside the prompt |

---

## Week 1 — The Ghostwriter (teach it your voice) → R1

**1.1 Two-brain architecture** · `docs/architecture_diagram.{png,excalidraw}`, Mermaid in the README.
*Why:* every later file builds one box of this diagram, so the diagram is the map of the code.

**1.2 Persona file**
- `persona/build_persona.py` **measures** your style. *Why:* "casual" means nothing to a model, while "31 % Hinglish, 3 words, 😘" is a target. It was fixed to read your iOS exports: the guide's pattern is Android-only and returned 0 messages.
- `persona/persona.json` is the **hand-authored** character sheet. Its example replies are your own real messages, picked from your chats. *Why:* the guide is explicit that more real examples beat more adjectives. It now has `wife` and `friends` sections, measured style per relationship, and holding replies.
- `persona/test_persona.py` is the moment of truth: 6 sample replies, each checked by the guardrail. *Why:* the v1 test produced 3 replies, and all 3 broke a hard rule unnoticed.

**What your real data showed:** with your wife, a median of 3 words and 31 % Hinglish; with family, 3 words and mostly English; at work, 6 words. The old persona told the model "47 words" for everyone. Measured signals are why the new replies stay short.

## Week 2 — The Curator (mine your history) → R1, R2, R5

**2.1 Mine your history**
- `ingestion/parse_export.py` turns a chat into "they said X → I replied Y" pairs. *Why pairs:* at reply time we search on what *they* said and read back what *you* said. Messages are merged into turns because people send bursts. File order is used instead of parsing dates (the DD/MM vs MM/DD ambiguity). The last 500 pairs are kept per chat.
- Noise is removed line by line. *Why:* your file had "Video call, 47 sec" lines hiding inside real messages, so filtering whole messages wasn't enough.
- Money, OTP and ID pairs are **quarantined**, never embedded. *Why:* if your memory contains money talk, the agent learns to talk money. That breaks hard rule #1 at its source.
- `validate_pairs.py` is the "don't trust that the script ran" step. It now uses the parser's own noise list. The old one reported "0 noise" on a file with call-log leaks.
- `clean_pairs.py` applies the same rules to an existing pairs file. On your data: 1,029 pairs in, 888 clean pairs out.

**2.2 Sort by relationship**
- `config/contact_relationship_map.json` maps chat → relationship, by hand. *Why not AI:* calling a stranger family is the mistake we can never let an algorithm make silently.
- `ingestion/embed_to_chroma.py` gives each relationship its own **separate box** (`history_family`, `history_friend`, `history_professional`, `history_unknown`). *Why separate:* a work message physically cannot retrieve a family reply. It embeds with the **multilingual** mpnet model because your chats mix Hindi, Hinglish and English. Stable ids make re-runs idempotent.
- `ingestion/retrieval.py` is the search the generator uses. *The fix that matters:* the course's 4 boxes put your wife in `family`, so your parents' messages retrieved replies like "Khaya motu ne". Now each contact's **own chat is searched first**, and private chats are excluded for everyone else in the box. Proven on your data: 5/5 → 0/5 wife examples for a family message.
- `retrieval_demo.py` is the Week 2 screenshot proof, run across all four boxes.

## Week 3 — The Router (teach it when to speak) → R2, R3

**3.1 Who's texting?** `agent/router.py` + `config/relationship_map.json`: phone number → relationship, with **no AI**. It keeps your session's `resolve_relationship` contract (and its tests). Added: device suffixes are handled, raw LIDs never match, and `resolve_contact()` adds the persona and own-chat details from `contact_profiles.json`.

**3.2 Reply or ignore?** `agent/decision_engine.py`, in the guide's layer order:

| Layer | What | Why here |
|---|---|---|
| L1 hard rules | kill switch, own message, group, not allowlisted, media-only, forwarded, **money**, **OTP/ID**, **serious topics** | Non-negotiable, free, and run before any AI |
| L2 signal rules | "ok/👍", **you typed here < 10 min ago**, rate limit, quiet hours | What a person would notice: don't talk over yourself, don't reply at 2 am |
| L3 intent check | regex: plan → HOLD; greeting / check-in / celebration / thanks / share → safe | Most messages are decided for free, so no Gemini quota is spent |
| L4 AI check | **one** Gemini call, only for unclear messages; fails closed | "cheap logic first, AI only when genuinely needed". Your log showed 503 errors |
| L5 reply policy | `settings.json → hold_intents` | Your judgment as data (e.g. work questions → HOLD) |

*Why HOLD exists:* "reply or ignore" isn't enough for your rule "never confirm plans without me". Ignoring "can you pick me up?" from your wife is wrong, and saying yes breaks the rule. HOLD sends "Ek min babu, check karke batata hu" and leaves the decision to you.

**Generation:** `agent/generator.py` builds one prompt: persona (this person's tone, measured style, your real replies, hard rules) + **short-term context** (the last N messages of this chat) + 2–3 retrieved past exchanges + the new message. *Why short-term context:* retrieval knows how you usually talk, but not what is being talked about right now. "Haan wahi wala" means nothing without the previous message.

**Guardrail:** `agent/guardrail.py` checks the reply before it can leave: money, OTP, a plan commitment, a time or date nobody mentioned, AI tells, and length. A bad draft gets one retry, then a safe holding reply. *Why:* the decision engine guards what comes *in*; this guards what goes *out*.

## Week 4 — The Puppetmaster (go live) → R4

**4.1 Wire up Baileys**
- `whatsapp/baileys_client.js` handles stage 1 (message in), stage 7 (wait + "typing…") and stage 8 (send). It's deliberately simple: every decision is made and logged in Python. It forwards your own typed messages so the agent knows you're there, and cancels a pending reply if you start typing. It re-checks the kill switch, dry-run and allowlist right before sending, and routes privacy-LID chats by phone number.
- `bridge/bridge.py` is a Flask server on **127.0.0.1**:5001 with a token. *Why a bridge:* Baileys is Node, while the RAG stack is Python.
- `agent/pipeline.py` runs all 8 stages in one place, so the bridge, console sandbox and batch test can't drift apart.

**4.2 Go live**
- `config/settings.json` + `kill_switch.flag` form **one** control plane that the bot, bridge and console all read.
- `console/app.py` (the Cruise Control Console) shows every message with the stages it reached, the deciding layer, short-term context, retrieval trace, prompt, guardrail attempts, delay and **sent** status. It also has the kill switch, a live/dry-run toggle and a sandbox. *Why:* this is the brief's traceability promise made visible.

---

## Understanding checkpoints (answers)

**Session 1.1**
1. *Why not fine-tune?* It costs money or a GPU, it freezes an old version of me, you can't see why it said something, and it blends who I am with what I said to whom.
2. *Persona vs history?* The persona knows **who I am** (identity, tone, rules). The history knows **what I actually said** to people like this.
3. *Why split by relationship?* So a search for my boss's message can only ever find my work replies. The isolation is structural.
4. *Brains vs plumbing?* Retrieval = history brain, Persona Injection = persona brain, Generation combines them. Router and Decision Engine are rules (plus one optional AI call). Message In, Delay and Send are plumbing.

**Session 1.2**
1. Measuring gives the model numbers to aim at, and corrects memory. Your real reply length is about 3 words, not 47.
2. A `--name` mismatch. Copy your exact label from the export (`अरूण`). The script now prints the labels it found.
3. Stats can't tell what tone fits your wife versus your boss. A human must vouch for the persona.
4. More **real verbatim example replies**, not better adjectives.
5. One less dependency; regex is good enough (plus variant normalisation).

**Session 2.1**
1. Date formats are ambiguous, and file order is already chronological.
2. A message is one bubble; a turn is consecutive bubbles from one person. You reply to turns.
3. System strings appear in that language and slip through. Search the export for "omitted" or "call" and add them to `config/constants.py`.
4. With 3+ senders, "their message → my reply" pairing is meaningless, and the agent never replies in groups anyway.
5. Read the sample pairs (do they make sense together?) and check that no noise leaked. The validator now enforces this and blocks embedding on failure.

**Session 2.2**
1. Exports know contact *names* (conversation_id), while live messages only carry *phone numbers*. Map 1 tags history, map 2 routes live messages.
2. At reply time we search on what *they* said; your reply is the payload we read back.
3. It would reload a ~1 GB model per pair, which turns minutes into hours.
4. Re-runs overwrite instead of duplicating. The id now hashes content, so cleaning doesn't shift ids.
5. The model wasn't trained on romanised Hinglish code-mixing, so it's "good enough", not perfect. The free fallback is real examples per contact; the paid route is a better embedding model.
