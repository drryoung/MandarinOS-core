<!-- MANDARINOS-DOCUMENT-STATUS:BEGIN -->
> **MandarinOS document authority notice — Class B: Current supporting documentation**
>
> - **Current use:** Provides supporting orientation for developers entering the MandarinOS repository.
> - **May guide current implementation:** Yes, but only when read through the approved R2 document hierarchy.
> - **Current authority:** The nine-document R2 architecture-governance package, beginning with `docs/DOCUMENT_AUTHORITY_INDEX.md`, `docs/ARCHITECTURE.md`, and the relevant detailed contracts.
> - **Principal caution:** This onboarding document is not a complete or primary architecture contract. Where it conflicts with verified code or a class-A R2 document, the verified code and class-A document govern.
> - **Classification source:** `docs/DOCUMENT_AUTHORITY_INDEX.md`
> - **Classification date:** `2026-07-13`
> - **Notice added:** `2026-07-14`
> - **Original content:** Preserved below without reinterpretation.
<!-- MANDARINOS-DOCUMENT-STATUS:END -->

# MandarinOS — Developer Onboarding & Hosting Guide

> **Audience:** A professional developer joining the project to help with hosting, deployment, and beta-feedback refinement.
> **Updated:** 2026-05-11

---

## Documentation authority and safe starting path

This section complements the class-B notice above. It does **not** elevate this document to class-A authority. For the canonical classification register, see `docs/DOCUMENT_AUTHORITY_INDEX.md`.

### Starting sequence

Begin with the **nine-document approved R2 governance package** (class A), in this order:

1. `docs/DOCUMENT_AUTHORITY_INDEX.md` — how to classify every document before relying on it.
2. `docs/ARCHITECTURE.md` — system orientation map.
3. `docs/CONVERSATION_ARCHITECTURE.md` — conversation behavioural contract.
4. The detailed behavioural contracts applicable to your change:
   - `docs/STATE_CONTRACT.md`
   - `docs/ANSWER_SOURCE_CONTRACT.md`
   - `docs/ASR_PIPELINE.md`
5. `docs/TEST_STRATEGY.md` — evidence requirements for behavioural claims.
6. `docs/CHANGE_CHECKLIST.md` — operational change workflow.
7. `docs/ARCHITECTURAL_DECISIONS.md` — architectural decision record.

Only after that sequence, use class-B supporting material (including this document), family guides, and lower-authority documents for context.

### How to use lower-authority documents

| Class | Role | Safe use |
| ----- | ---- | -------- |
| **B** | Current supporting guidance | May guide implementation **only** when consistent with class-A contracts and verified code. |
| **C** | Historical / contextual | Explains history and rationale; does **not** independently authorise changes. |
| **D** | Superseded operational instructions | Must **not** guide current implementation. |
| **E** | Dated evidence | Records what was true at a review date; not present authority. |
| **F** | Proposals / unimplemented specs | Implementation must be verified against code and contracts. |
| **G** | Generated or procedural artefacts | Regenerate captured outputs; treat authored templates as workflow aids only. |

### Safe maintenance workflow

Before modifying the application:

1. Identify the relevant subsystem.
2. Identify its class-A governing document (see decision table in `docs/DOCUMENT_AUTHORITY_INDEX.md` §13).
3. Inspect current code and tests.
4. Check relevant ADRs in `docs/ARCHITECTURAL_DECISIONS.md`.
5. Inspect lower-authority documents only for context.
6. Follow `docs/CHANGE_CHECKLIST.md`.
7. Run the relevant regression tests.
8. Update documentation only when verified behaviour changes.

### Family guidance

Historical document families have approved entry guides (Phase B5B). Use these before opening individual files in those directories:

- [`docs/directives/README.md`](directives/README.md) — Phase 2–7 implementation directives (17 files).
- [`docs/phases/README.md`](phases/README.md) — phase milestones and locks (9 files).
- [`integration_kit/README.md`](../integration_kit/README.md) — trace-export kit (5 files).

These guides control entry into those families without reclassifying the underlying documents.

### Generated guidance

Files flagged `generated-guidance-added` in `docs/DOCUMENT_AUTHORITY_INDEX.md` §17 are **outputs**, not sources. Regenerate them through their producing workflow (see Phase B5C). Do not edit captured dumps as if they were authoritative specifications.

### The 46-document integration set (Phase B5D)

Forty-six previously unnotified supporting documents are mapped into the authority path via onboarding and this index — **not** via individual notices. Inclusion here does **not** grant class-A or class-B authority. The complete path list is in `docs/PHASE_B5_SCOPE_ASSESSMENT.md` §13.2 and `docs/DOCUMENT_AUTHORITY_INDEX.md` §13.1.

| Subsystem / family | Count | Class | Governing authority | Normal use |
| ------------------ | ----- | ----- | ------------------- | ---------- |
| Repo entry, Cursor rules, conformance, runtime indexes, option style, extensibility/flow specs, design constitution | 11 | B | Nine-document R2 package and applicable contracts (see index §13.1) | Supporting reference when aligned with contracts and code |
| `docs/briefings/` strategist and phase briefings | 28 | C | Nine-document R2 governance package | Historical context only; class-E audits in the same directory are separately noticed (Phase B4C) |
| `docs/design/` early design artefacts | 5 | C | `docs/ARCHITECTURE.md` | Historical context only |
| `docs/project/` procedural templates | 2 | G | Authorship workflow | Templates and commit instructions; not behavioural authority |

---

## 1. What MandarinOS Is

MandarinOS is a **conversation-first Mandarin Chinese learning app**. It teaches spoken competence through structured dialogue — not flashcards, not grammar drills. The learner has a conversation with a Chinese-speaking persona (a virtual partner), guided by a frame-based engine that selects questions, manages topic flow, and adapts to the learner's responses.

**Core loop:**
1. The app speaks a question in Chinese (a "frame")
2. The learner responds — by voice (Web Speech API) or by tapping a response option
3. The app reacts, follows up, and selects the next question based on conversational context
4. Optional: the learner can ask the persona questions (blue "discovery" panel)

**Not a chatbot.** The conversation is structured — there is no LLM generating freeform text at runtime. All partner sentences come from curated JSON content and persona data. An AI hybrid layer is planned for the future but is not active.

---

## 2. Tech Stack

| Layer | Technology | Notes |
|-------|-----------|-------|
| **Server** | Python 3.10+ (stdlib `http.server`) | Single file: `scripts/ui_server.py` (~7200 lines). No framework (no Flask/Django). Threaded HTTP server on port 8765. |
| **Client** | Vanilla JS + HTML + CSS | `ui/app.js` (~7200 lines), `ui/index.html`, `ui/styles.css`. No React/Vue/build step for the core UI. |
| **Speech** | Web Speech API (browser-native) | ASR (recognition) + TTS (synthesis). Requires HTTPS in production for microphone access. |
| **Data** | JSON files (no database) | All content, personas, frames, recovery phrases, response patterns — flat JSON in the repo. |
| **Tests** | Python (`tests/test_golden_regression.py`) | 327 assertions (303 static + 24 integration). Run from repo root. |
| **Optional deps** | `deep-translator`, `pypinyin` | Only needed for transcript translation and character enrichment tooling. See `requirements-tools.txt`. |

**There is also a `package.json` in the repo** with React/Vite/Tailwind dependencies — this is for a separate future web platform build, **not** for the current conversation UI. The active app uses no Node.js tooling.

---

## 3. Repo Structure (What Matters)

```
MandarinOS-core/
├── scripts/
│   └── ui_server.py          # THE server — all conversation logic, API endpoints, persona routing
├── ui/
│   ├── index.html             # Entry point
│   ├── app.js                 # All client-side logic (ASR, TTS, UI rendering, state management)
│   ├── styles.css             # Styles
│   ├── cardPanel.js           # Word-insight card panel
│   ├── ttsSpeak.js            # TTS wrapper
│   └── pinyinAlign.js         # Pinyin alignment utility
├── content/
│   ├── mirror_questions.json  # Bank of questions the learner can ask the persona
│   ├── recovery_phrases.json  # Repair/deflection phrases for confusion and misunderstanding
│   └── response_patterns.json # Learner response options per frame
├── personas/
│   ├── xiaoming.json          # 5 distinct personas with profile, voice_lines, discoverable_facts
│   ├── meiling.json
│   ├── jianguo.json
│   ├── xiaoyun.json
│   └── zhiyuan.json
├── p1_frames.json             # Phase 1 frame definitions (questions the app asks)
├── p2_frames.json             # Phase 2 frame definitions
├── p1_words.json / p2_words.json  # Vocabulary lexicons
├── p1_engines.json / p2_engines.json  # Engine (topic) definitions
├── tests/
│   └── test_golden_regression.py  # Primary regression test suite
├── AI_CONTEXT.md              # Authoritative repo map for AI assistants
├── README.md                  # Basic readme
└── docs/                      # Specs, briefings, phase docs (extensive — see §10)
```

### Files You'll Touch Most

- **`scripts/ui_server.py`** — Server logic. All API endpoints, conversation selector, persona answer routing, scoring, discovery panel logic.
- **`ui/app.js`** — Client logic. ASR handling, UI state, option rendering, session tracking.
- **`content/*.json`** — Conversation content. Recovery phrases, mirror questions, response patterns.
- **`personas/*.json`** — Persona profiles and voice lines.

---

## 4. Running Locally

### Prerequisites

- Python 3.10+ (no virtual environment required for the core server)
- A modern browser (Chrome recommended — best Web Speech API support)

### Start the server

```bash
cd MandarinOS-core
python scripts/ui_server.py
```

Output: `[ui_server] Listening on http://localhost:8765`

### Open the app

```
http://localhost:8765/ui/index.html
```

### Run tests

```bash
# Full suite (requires server running):
python tests/test_golden_regression.py

# Static checks only (no server needed):
python tests/test_golden_regression.py --static-only
```

### Mobile / LAN testing

Access via `http://<laptop-LAN-IP>:8765/ui/index.html` on the same Wi-Fi. **Speech input will not work over plain HTTP to a LAN IP** — browsers require HTTPS for microphone access. Typed interaction still works.

---

## 5. API Surface

The server exposes a small set of HTTP endpoints. All are served by `scripts/ui_server.py`.

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/run_turn` | POST | Core turn engine — accepts learner answer + conversation state, returns next frame + options + counter-reply + discovery questions |
| `/api/gloss` | POST | Machine English translation for transcript lines |
| `/api/end_session` | POST | Session end — receives session metrics, returns scorecard |
| `/ui/*` | GET | Static files (HTML/JS/CSS) |
| `/data/*`, `/content/*`, `/personas/*` | GET | Static JSON content |

### `/api/run_turn` — the main endpoint

**Request body (JSON):**
```json
{
  "next_question": true,
  "last_answer": { "submitted_text": "我是成都人", "selected_option_hanzi": "..." },
  "conversation_state": {
    "session_id": "...",
    "current_engine": "place",
    "last_partner_frame_id": "f_place_where",
    "recent_frame_ids": ["f_place_where", "f_identity_name"],
    "exchange_count": 5,
    "persona_id": "xiaoming"
  }
}
```

**Response (JSON):**
```json
{
  "frame_id": "f_place_like",
  "frame_text": "你喜欢在那里生活吗？",
  "frame_text_en": "Do you like living there?",
  "engine_id": "place",
  "options": [ { "hanzi": "喜欢", "pinyin": "xǐhuān", "meaning": "like", "is_gold": true } ],
  "counter_reply": "我是成都人，不过在北京工作已经好几年了。",
  "counter_reply_en": "I'm from Chengdu — though I've been working in Beijing for years.",
  "discovery_questions": [ { "zh": "你喜欢你的家乡吗？", "topic": "place_like" } ],
  "state_update": { "last_partner_frame_text": "你喜欢在那里生活吗？" }
}
```

The client manages `conversation_state` locally and sends it back each turn. There is no server-side session storage — state is round-tripped in the payload.

---

## 6. Architecture Essentials

### Conversation flow

```
Learner input
  → Client (app.js): ASR/text processing, signal detection, option selection
  → POST /api/run_turn with answer + conversation_state
  → Server (ui_server.py):
      1. Counter-reply generation (persona answers, confusion clarification, mirror lookup)
      2. Reaction micro-layer (short acknowledgment prefixes)
      3. Frame selector (next question — engine-aware, depth-triggered, difficulty-ramped)
      4. Discovery panel builder (blue questions the learner can ask)
      5. Scoring signals (interest, confusion count, repair escalation)
  → Response: next frame + options + counter_reply + discovery_questions + state_update
  → Client renders frame, speaks TTS, shows options + discovery panel
```

### Key concepts

- **Engine**: A topic domain (identity, place, food, family, work, travel, hobby). Each engine has its own frames.
- **Frame**: A question the app asks, defined in `p1_frames.json` / `p2_frames.json`. Has `text` (Chinese), `text_en`, `engine_id`, `difficulty`, `move_type`.
- **Persona**: The virtual conversation partner. Has a profile (name, city, job), voice_lines, and discoverable_facts. Lives in `personas/*.json`.
- **Counter-reply**: The persona's spoken response to the learner's answer or question — delivered before the next frame.
- **Discovery panel**: Blue question cards shown to the learner so they can ask the persona questions (user-led conversation).
- **Recovery/repair**: When the learner signals confusion, the system clarifies and escalates through a repair ladder.

### State management

- **No database.** All state is in-memory on the client (`window._*` variables) and round-tripped via `conversation_state` in each API call.
- **No authentication.** Single-user local app. No login, no user accounts.
- **Session**: A session starts when the learner begins a conversation and ends when they tap "End Session". Session metrics are sent to `/api/end_session` for scorecard generation.

---

## 7. Hosting for Beta Testing

### What's needed

The app is currently a **localhost-only Python HTTP server** with a **vanilla JS frontend**. To host it for beta testers, you need:

1. **HTTPS** — Required for Web Speech API (microphone access). Non-negotiable.
2. **A server that can run Python 3.10+** — The conversation logic is all in `ui_server.py`.
3. **Static file serving** — The `ui/` directory and JSON content files.

### Recommended approach: Reverse proxy + cloud VM

```
[Browser] ──HTTPS──▶ [Nginx/Caddy] ──HTTP──▶ [Python ui_server.py :8765]
                     (TLS termination)        (conversation engine)
```

**Option A — Minimal (single VM):**
- Cloud VM (DigitalOcean droplet, AWS Lightsail, Azure B1s, etc.)
- Caddy (auto-HTTPS with Let's Encrypt) or Nginx + Certbot
- `python scripts/ui_server.py` as a systemd service
- Domain name pointed at the VM

**Option B — Container:**
- Dockerize: Python base image, copy repo, expose 8765
- Deploy to any container host (Cloud Run, Fly.io, Railway, etc.)
- Container host handles HTTPS

**Option C — Replit / similar PaaS:**
- The repo already has a `package.json` — some PaaS platforms may try to run the Node.js stack. Ignore that; the active app is the Python server.
- Configure the run command as `python scripts/ui_server.py`

### HTTPS is critical

Without HTTPS, the browser blocks microphone access, and the app loses its primary input method. Typed input still works but defeats the purpose of a speech-first app.

### What does NOT need to change for hosting

- No database setup needed — all data is JSON files in the repo.
- No build step — the JS/HTML/CSS is served directly.
- No Node.js — ignore `package.json` for the core app.
- No environment variables — the server has no configuration beyond the hardcoded port (8765).

### What MIGHT need to change

- **Port**: Currently hardcoded to 8765 in `ui_server.py` line 7199. Easy to parameterize with `argparse` or environment variable.
- **CORS**: Not needed if proxy serves both API and static files from the same origin.
- **Bind address**: Currently `""` (all interfaces). Fine for container/VM; restrict to `127.0.0.1` if behind a reverse proxy.
- **Process management**: Wrap in systemd, supervisor, or Docker for auto-restart.
- **Logging**: Server prints to stdout. Redirect to a log file or use a log aggregator.

---

## 8. Key Content Files (For Beta Feedback Refinement)

When beta testers report issues, most fixes will be **content changes**, not code changes.

| File | What it controls | Common fixes |
|------|-----------------|--------------|
| `p2_frames.json` | Questions the app asks | Add/edit frames, adjust difficulty, fix awkward phrasing |
| `content/response_patterns.json` | Response options shown to learner | Fix wrong options, add missing patterns, adjust difficulty |
| `content/recovery_phrases.json` | What the app says when learner is confused | Improve repair phrases, add new recovery paths |
| `content/mirror_questions.json` | Questions the learner can ask (blue panel) | Add new discovery questions, fix paraphrases |
| `personas/*.json` | Persona answers and personality | Enrich facts, fix voice_lines, add missing topics |
| `p1_words.json` / `p2_words.json` | Vocabulary definitions | Fix pinyin, meanings, add missing words |

### The decision priority for fixing reported issues

1. **Better content** — new/improved frames, responses, options, persona facts
2. **Ordering or builder refinement** — adjust which frames appear when
3. **Minimal selector hygiene** — small logic fix in `ui_server.py`
4. **Architecture change** — only as last resort, with justification

This priority order is a core project principle. See `docs/specs/Cursor_Directive_MandarinOS_Extensibility_Strategy.md`.

---

## 9. Testing & Regression Discipline

### Running the test suite

```bash
# Static assertions only (fast, no server needed):
python tests/test_golden_regression.py --static-only

# Full suite (start server first):
python scripts/ui_server.py &
python tests/test_golden_regression.py
```

### Current test state

- **327 total assertions** (303 static + 24 integration)
- **303 pass** consistently; 24 integration tests fail due to server routing conditions that require specific live state — these are known and pre-existing.
- Static tests cover: persona data integrity, scoring model, discovery trigger timing, confusion handling, answer staging, question selection.

### Regression rule

**Every behavioral change must have a regression test.** If you fix a bug or change conversation behavior, add a test case to `test_golden_regression.py` that locks the fix.

---

## 10. Documentation Index

The `docs/` directory is extensive. Here's what matters for a developer joining now:

| Document | Why you'd read it |
|----------|-------------------|
| `AI_CONTEXT.md` (repo root) | **Start here.** Authoritative repo map, architecture guardrails, current phase status. |
| `docs/specs/MANDARINOS_CONVERSATION_FLOW_DESIGN.md` | How the conversation selector works, anti-patterns to avoid. |
| `docs/specs/Cursor_Directive_MandarinOS_Extensibility_Strategy.md` | The "extensibility first" principle — how to classify and fix issues. |
| `docs/MANDARINOS_REGRESSION_LOCK.md` | Which behaviors are protected by regression tests and why. |
| `docs/archive/specs/Live_Beginner_Ability_Model.md` | The learner ability model (observational — Phase 1; historical background, class C). |
| `docs/archive/briefings/USER_LED_DISCOVERY_STRATEGIST_BRIEF.md` | How the blue discovery panel, counter-reply, and recovery systems work (historical background, class C). |
| `docs/briefings/STRATEGIST_BRIEFING_MAY2026_UI_POLISH_AND_DISTANCE_THREAD.md` | Latest strategist briefing — current priorities and refinement direction. |

### Documents you can skip initially

- Phase 1–9 docs (historical — architecture is settled)
- `docs/design/` (constitution and governance — important but stable; read `AI_CONTEXT.md` summary instead)
- Marketing/social media docs (`docs/Social_Media/`)
- Character etymology docs (unless working on word cards)

---

## 11. Common Developer Tasks

### "A beta tester says the app asked an awkward question"

1. Identify the `frame_id` from the server log or browser console
2. Find it in `p2_frames.json` (or `p1_frames.json`)
3. Edit the `text` / `text_en` fields
4. Run `python tests/test_golden_regression.py --static-only` to check nothing broke

### "A beta tester says the response options don't make sense"

1. Find the frame in `content/response_patterns.json`
2. Edit or add options — each needs `zh`, `pinyin`, `en`, `level`
3. Options must follow the style guide in `docs/RESPONSE_OPTION_STYLE_GUIDE.md`

### "A beta tester says the persona gave a weird answer"

1. Identify which persona and topic (server log: `[counter_reply]` or `[mirror]`)
2. Check `personas/<name>.json` → `discoverable_facts` and `voice_lines`
3. Fix the specific line; the server routing in `_mirror_persona_stub` selects by topic

### "A beta tester says the app didn't understand them"

This is usually an ASR issue or a matching issue:
- **ASR**: Browser speech recognition is imperfect. Check `submitted_text` in the server log.
- **Matching**: The server's answer classification may need a new pattern. Look at `_is_food_answer`, `_is_travel_destination`, etc. in `ui_server.py`.
- **Recovery**: If the app rejected a valid answer, the learner should see a recovery panel. If not, check `classifyUnmatchedFreeAnswerDecision` in `app.js`.

### "I need to add HTTPS for beta deployment"

See §7 above. Simplest: put Caddy in front of the Python server. Caddy auto-provisions Let's Encrypt certificates.

```
# Caddyfile
mandarinos.yourdomain.com {
    reverse_proxy localhost:8765
}
```

---

## 12. What's Coming Next

The project is in a **refinement phase**. The architecture is stable. Near-term work:

1. **Beta hosting** — Get the app online with HTTPS for real testers
2. **Content refinement** — Improve frames, options, and persona answers based on beta feedback
3. **12C stabilization** — Repair/clarification behavior (mostly done)
4. **12D overlay** — Optional "Meaning + Move" hints for ambiguous partner lines (planned, not started)
5. **Hybrid AI layer** — Future: LLM fills gaps where structured engine has no good frame (concept only, not implemented)

---

## 13. Quick Reference

```bash
# Start server
python scripts/ui_server.py

# Open app
open http://localhost:8765/ui/index.html

# Run tests (static only)
python tests/test_golden_regression.py --static-only

# Run tests (full, server must be running)
python tests/test_golden_regression.py

# Check a specific persona
cat personas/xiaoming.json | python -m json.tool

# Server logs
# All conversation debug output goes to stdout — watch the terminal
```

**Port:** 8765 (hardcoded in `scripts/ui_server.py:7199`)
**Python version:** 3.10+
**Browser:** Chrome recommended (best speech API support)
**Database:** None — all JSON files
**Build step:** None — serve files directly
