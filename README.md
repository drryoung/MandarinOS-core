# MandarinOS (Core)

MandarinOS is a **conversation-first Mandarin Chinese learning system** designed to build usable spoken competence — not passive vocabulary recognition.

The learner has a structured conversation with a Chinese-speaking persona. The system selects questions, manages topic flow, reacts to answers, and adapts to the learner's level — all without an LLM at runtime. Every partner sentence comes from curated JSON content and persona data.

## Quick Start

```bash
# Start the server (Python 3.10+ required, no other dependencies for core)
python scripts/ui_server.py

# Open in browser
http://localhost:8765/ui/index.html
```

Speech input requires Chrome (best Web Speech API support). Typed input works in any browser.

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Server | Python 3.10+ stdlib HTTP server (`scripts/ui_server.py`) |
| Client | Vanilla JS / HTML / CSS (`ui/`) |
| Speech | Web Speech API (browser-native ASR + TTS) |
| Data | JSON files — no database |
| Tests | `python tests/test_golden_regression.py` |

No build step. No Node.js required for the core app.

## Testing

```bash
# Static checks only (no server needed):
python tests/test_golden_regression.py --static-only

# Full suite (start server first):
python tests/test_golden_regression.py
```

## Key Files

| File | Role |
|------|------|
| `scripts/ui_server.py` | All server logic — conversation engine, persona routing, scoring, API |
| `ui/app.js` | All client logic — ASR, TTS, UI rendering, session state |
| `personas/*.json` | 5 conversation personas with profiles, voice lines, discoverable facts |
| `content/*.json` | Recovery phrases, mirror questions, response patterns |
| `p2_frames.json` | Frame definitions (questions the app asks) |
| `AI_CONTEXT.md` | Authoritative repo map for AI assistants and developers |

## Documentation

- **[Developer Onboarding & Hosting Guide](docs/DEVELOPER_ONBOARDING.md)** — Start here if you're a developer joining the project. Covers architecture, hosting, API surface, beta deployment, and common tasks.
- **[AI Context](AI_CONTEXT.md)** — Authoritative repo map, architecture guardrails, phase status.
- **[Regression Lock](docs/MANDARINOS_REGRESSION_LOCK.md)** — Protected behaviors and testing discipline.

## Guardrails

MandarinOS is conversation-first, frame-driven, and learner-centered. If proposed changes introduce vocabulary-first flows, teacher-style explanations, or schema refactors "for cleanliness", stop and re-evaluate.

See `docs/design/mandarinos_design_constitution.txt` for non-negotiable principles.
See `docs/specs/Cursor_Directive_MandarinOS_Extensibility_Strategy.md` for the extensibility-first approach to fixes.
