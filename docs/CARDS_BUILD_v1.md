# Cards Build v1

Run the cards builder:

```bash
python tools/cards/build_cards.py
# or with config
python tools/cards/build_cards.py --config tools/cards/cards_config.json
```

Outputs (default):
- `tools/cards/out/cards.json`
- `tools/cards/out/cards_index.json`

The builder uses only the Python standard library and enforces Card Contract v1 rules: required fields, action effects that change state, and monotonic reveal_level increments.
