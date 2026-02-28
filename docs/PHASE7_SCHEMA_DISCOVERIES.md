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
