<!-- MANDARINOS-DOCUMENT-STATUS:BEGIN -->
> **MandarinOS document authority notice — Class F: Proposal, plan, or unimplemented specification**
>
> - **Current use:** Retained as the proposed minimal implementation sequence for Phase 10.7.
> - **May guide current implementation:** No.
> - **Current authority:** Verified current code, the applicable detailed R2 contracts, and `docs/CHANGE_CHECKLIST.md`.
> - **Principal caution:** The plan describes intended work and sequencing. It does not prove that any step was implemented, retained, or incorporated into the R2 baseline.
> - **Classification source:** `docs/DOCUMENT_AUTHORITY_INDEX.md`
> - **Classification date:** `2026-07-13`
> - **Notice added:** `2026-07-14`
> - **Original content:** Preserved below without reinterpretation.
<!-- MANDARINOS-DOCUMENT-STATUS:END -->

# Phase 10.7 — Minimal implementation plan (preserve Phase 10.5 / 10.6)

**Purpose:** Apply **`docs/briefings/MANDARINOS_PHASE_10_7_PHASE_11_BRIEFING.txt`** in the **smallest safe slices**, and execute the **move_type tagging pass** per **`docs/briefings/MANDARINOS_MOVE_TYPE_TAGGING_BRIEF.txt`**, **without** regressing **Phase 10.5** (server behaviour layer) or **Phase 10.6** (ASR / unmatched handling in `ui/app.js`).

**Principles:**
- **Additive first** — new fields and branches; **fallback** to current behaviour when tags absent.
- **No new heuristics** in the strategist sense: do not stack parallel probability rules; **replace** only when `move_type` is present and validated.
- **Do not rewrite frame `text`** during tagging (per move_type brief).

---

## 0) Taxonomy alignment (two briefings)

| Phase 10.7 briefing | Move-type tagging brief | **Canonical value (use in JSON)** |
|---------------------|-------------------------|-----------------------------------|
| *(none)*            | OPEN                    | **OPEN**                          |
| ASK                 | ASK                     | ASK                               |
| ANSWER              | ANSWER                  | ANSWER                            |
| REACTION            | REACTION                | REACTION                          |
| EXTENSION           | EXTEND                  | **EXTEND**                        |
| LOOP                | LOOP                    | LOOP                              |
| RECIPROCITY         | RECIPROCITY             | RECIPROCITY                       |
| REPAIR              | REPAIR                  | REPAIR                            |
| BRIDGE              | BRIDGE                  | BRIDGE                            |
| CLOSE               | CLOSE                   | CLOSE                             |

**Rule:** All new tags use the **tagging brief** spellings (**OPEN**, **EXTEND**). Document that **EXTENSION** in the Phase 10.7 txt is the same intent as **EXTEND**.

**Response roles** — both briefs align: **SAFE**, **EXPAND**, **REPAIR**, **RECIPROCITY**.

---

## 1) What we do **not** touch (10.5 / 10.6 preservation)

| Area | Files / behaviour | Rule |
|------|-------------------|------|
| **10.6** | `ui/app.js` — transcript matching, soft-match frames, two-strike fallback, `SPEECH_NOT_UNDERSTOOD`, trace reasons | **No logic changes** unless a **separate** mini-spec adds optional trace keys; no change to matching thresholds or frame-id lists without retest. |
| **10.5** | `ui/app.js` — `Promise.all` boot, threaded server assumption | No change required for 10.7 tagging. |
| **10.5** | `scripts/ui_server.py` — reaction probability, curiosity depth, weak-loop avoidance, memory suppression, probe/direction stubs, `ThreadedHTTPServer` | **Keep all existing paths live.** New selector logic must be **`if move_type_available: … else: legacy_path()`** until tagging coverage is high. |

---

## 2) Minimal implementation phases (ordered)

### Phase A — Tagging pass only (no selector refactor)

**Goal:** Satisfy **Stages 1–4** of **`MANDARINOS_MOVE_TYPE_TAGGING_BRIEF.txt`** without changing runtime decisions.

1. **Tooling**  
   - Add `scripts/propose_move_type_tags.py` (name flexible) that:  
     - Loads `p1_frames.json`, `p2_frames.json`.  
     - Emits **`docs/reports/move_type_tagging_audit.md`** (table: `frame_id`, `engine`, `text`, `proposed_move_type`, `confidence`, `reason`).  
     - Emits **`data/move_type_tags.proposed.json`** (machine-readable: same fields + optional `allowed_response_roles`, `default_next_move_types` per Stage 3).  
   - Optional: second script **`scripts/apply_move_type_tags.py`** — merges reviewed proposals into `p1_frames.json` / `p2_frames.json` **only** for rows marked `confidence >= medium` and human-approved (or interactive flag file).

2. **Schema (source frames)**  
   Per Phase 10.7 §5 / tagging brief, each frame may gain:
   ```json
   "move_type": "ASK",
   "allowed_response_roles": ["SAFE", "EXPAND", "REPAIR", "RECIPROCITY"]
   ```
   Optional later: `default_next_move_types` (reference only until selector uses it).

3. **Builder**  
   - Extend **`tools/build_runtime_artifacts.py`** → `build_frame_options` to **copy** onto each runtime entry (additive):
     - `move_type`, `allowed_response_roles` (if present on source frame).  
   - Keeps UI/server able to read tags from **`frame_options.runtime.json`** without loading full frame files twice (optional: server already has `_frames_by_id` from p1/p2 — either path is fine; **pick one** to avoid drift).

4. **Validation**  
   - `build_report` or small check: every frame has `move_type` **or** is listed in `move_type_tagging_audit.md` as **low-confidence / pending**.

**Exit criteria:** Audit + proposed JSON exist; human review list short; **no** change to which frame is chosen next (10.5 logic unchanged).

---

### Phase B — Option-level `response_role` (still minimal)

**Goal:** Satisfy Phase 10.7 §4 at **option** granularity without changing scoring.

1. **Data**  
   - Prefer tagging **in builder output**: when emitting each option in `frame_options.runtime.json`, add optional **`response_role`** per option (`SAFE` default for gold if unspecified).  
   - **Heuristic defaults** (allowed as *defaults*, not new conversational heuristics): `is_gold` → `SAFE`; slot frames → `SAFE`; others `EXPAND` until curated.

2. **Contract**  
   - Document in **`AI_CONTEXT.md`** or turn contract doc: options may include `response_role`.

**Exit criteria:** Runtime JSON carries roles where cheap; **10.6** unchanged; options still render and submit identically.

---

### Phase C — Selector: read `move_type`, fallback to 10.5

**Goal:** First **move-based** filtering **without** removing 10.5 probabilities.

1. **Helper**  
   - `_frame_move_type(fid) -> str | None` from `_frames_by_id` or `frame_options`.

2. **Integration**  
   - At **candidate shortlist** step (after engine/deps satisfied):  
     - If **all** candidates have `move_type` and a **small transition table** (tagging brief §4) says “after REACTION only LOOP | RECIPROCITY | …”, **filter** candidates to legal next moves.  
     - **Else:** skip filter → **existing 10.5** behaviour exactly.

3. **Metrics hook (optional)**  
   - Trace field `move_type_selected` / `move_type_filter_skipped` for later Phase 11.

**Exit criteria:** With **zero** tags, behaviour matches current prod; with **full** tags, transitions respect reference model; **no** removal of `P_REACTION_AFTER_MEANINGFUL` etc. until a follow-up milestone explicitly replaces them.

---

### Phase D — Remove redundant heuristics (explicit follow-up, not “minimal”)

**Deferred** until Phase C is stable and tagging coverage > threshold (e.g. 95% frames).  
Then: collapse duplicate rules (e.g. reaction insertion) into **move_type-driven** flow per strategist **§6** and **§12**.

---

## 3) Move_type tagging pass — checklist (from `MANDARINOS_MOVE_TYPE_TAGGING_BRIEF.txt`)

- [ ] **Stage 1 — Frame audit** → markdown report with confidence + reason.  
- [ ] **Stage 2 — Decision rules** — one primary function; 你呢？ → RECIPROCITY; LOOP vs BRIDGE; etc.  
- [ ] **Stage 3** — `allowed_response_roles` + `default_next_move_types` proposals in JSON.  
- [ ] **Stage 4** — Markdown audit + machine-readable artifact + **low-confidence list** for human review.  
- [ ] **Constraints:** no `text` rewrites; no new move types; flag ambiguity.

---

## 4) Risks and mitigations

| Risk | Mitigation |
|------|------------|
| Drift between p1/p2 and `frame_options.runtime.json` | Single builder pass copies tags; CI or `build_runtime_artifacts` required before ship. |
| Partial tagging breaks selector | **Always** fallback to 10.5 path when `move_type` missing or transition unknown. |
| EXTEND vs EXTENSION confusion | Single canonical **EXTEND** in JSON; doc alias. |
| 10.6 regression | No edits to unmatched / soft-match blocks in same PR as selector refactor; separate PR + retest. |

---

## 5) Suggested PR sequence

1. **PR1:** Scripts + reports only (Phase A tooling, empty or sample output).  
2. **PR2:** Apply reviewed tags to `p1_frames.json` / `p2_frames.json` + builder copy-through + rebuild runtime.  
3. **PR3:** Option `response_role` defaults in builder (Phase B).  
4. **PR4:** Selector gated transition filter + fallbacks (Phase C).  
5. **PR5 (later):** Retire overlapping 10.5 heuristics (Phase D).

---

## 6) Reference briefings

- **`docs/briefings/MANDARINOS_PHASE_10_7_PHASE_11_BRIEFING.txt`** — strategic goals, selector refactor order, Phase 11 hooks.  
- **`docs/briefings/MANDARINOS_MOVE_TYPE_TAGGING_BRIEF.txt`** — staged audit, taxonomies, constraints (**authoritative** for allowed `move_type` / role strings).  
- **`docs/briefings/PHASE_10_5_10_6_ALPHA_STRATEGIST_BRIEFING.md`** — current baseline and “no new heuristics” intent.

---

*End of plan.*
