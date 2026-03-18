# M4 Validation Tests

Run deterministic simulation validation:

```bash
cd polymarket-bots/polymarket-trading-bot-v2
python3 tests/simulate_m4.py
```

Pass criteria:
- `ok: true`
- no reconciliation failures
- exits happen correctly (TP/SL/last-minute force)
