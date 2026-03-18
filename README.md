# PolyMarket Trading Bot V2 (Paper Trading)

Paper-trading simulation bot for BTC/ETH 5-minute Polymarket up/down markets.

## Current Status
M1 + M2 implemented:
- paper portfolio accounting
- final-80s entry + settlement-at-close rule engine
- trade/event/state logging
- Telegram command wiring (`Log`, `Stop`)
- live market discovery + quote fetch from Polymarket Gamma API for BTC/ETH 5m markets

> The bot resolves and trades only the most current 5-minute market per symbol.

## Directory Layout
- `src/` runtime code
- `logs/trades.jsonl` trade-by-trade event log
- `logs/events.jsonl` runtime/diagnostic events
- `state/status_snapshot.json` latest state snapshot
- `spec/` frozen project specification

## Run
```bash
cd polymarket-bots/polymarket-trading-bot-v2
python3 -m src.main
```

## Telegram Commands
Commands accepted by bot:
- `Log` → reports open positions, realized P&L, cash, position value, portfolio value
- `Stop` → sends final summary and gracefully exits

### Enable Telegram control/messages
Set environment variables before run:
```bash
export PMB2_TELEGRAM_ENABLED=1
export PMB2_TELEGRAM_BOT_TOKEN='YOUR_BOT_TOKEN'
export PMB2_TELEGRAM_CHAT_ID='YOUR_CHAT_ID'   # optional but recommended lock
export PMB2_TELEGRAM_POLL_TIMEOUT_S=0          # 0 for short polling
```

## Accessing Logs
```bash
# trades
cat logs/trades.jsonl

# runtime events
tail -f logs/events.jsonl

# latest status snapshot
cat state/status_snapshot.json
```
