<!-- MANDARINOS-DOCUMENT-STATUS:BEGIN -->
> **MandarinOS document authority notice — Class E: Dated report or historical evidence**
>
> - **Current use:** Retained as historical evidence of schema discoveries made during Phase 7.
> - **May guide current implementation:** No.
> - **Current authority:** Verified current schemas, their consuming code, and the applicable R2 state and answer-source contracts.
> - **Principal caution:** Historical schema discoveries do not establish the current schema set, field semantics, or runtime consumption.
> - **Classification source:** `docs/DOCUMENT_AUTHORITY_INDEX.md`
> - **Classification date:** `2026-07-13`
> - **Notice added:** `2026-07-14`
> - **Original content:** Preserved below without reinterpretation.
<!-- MANDARINOS-DOCUMENT-STATUS:END -->

# Phase 7 Schema Invariants (Locked)

## Runtime Cards (cards_by_id.json)
- Keys: word_id strings (w_*)
- Fields: actions, card_id, content, state
- No hanzi fields in runtime cards

## Word Packs (p1_words.json, p2_words.json)
- Top-level key: "words"
- Per-word key: "id" (not "word_id")
- Hanzi field: "hanzi"

## Frame Packs (p1_frames.json, p2_frames.json)
- Top-level key: "frames"
- Per-frame key: "id"
- Text field: "text"

## Runtime cards_index
- by_word_id maps:
  - word_id -> card_id
  - frame_id -> card_id (Phase 7 builder)

## OPEN_CARD event payload
- engine_id
- frame_id
- card_id
- reason
