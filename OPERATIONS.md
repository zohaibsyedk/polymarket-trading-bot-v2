# PolyMarket Trading Bot V2 — Operations (M3)

## Start
```bash
cd polymarket-bots/polymarket-trading-bot-v2
cp .env.example .env
# edit .env with your token/chat id
./scripts/healthcheck.sh
./run.sh
```

## Telegram Commands
Send these to the bot chat:
- `Log` → current open positions, realized P&L, cash, position value, portfolio value
- `Market` → links to current BTC/ETH markets being watched
- `Snapshot` → current UP/DOWN prices for BTC and ETH watched markets
- `Stop` → sends final log summary and gracefully stops process

## Logs
- Trades: `logs/trades.jsonl`
- Runtime events: `logs/events.jsonl`
- Current state: `state/status_snapshot.json`

## Message formats implemented
- Entry: ID, market/timestamp, side+price, contract count + total position value, cash, position value, portfolio value
- Exit: ID, market/timestamp, side+entry, side+sell, per-contract net P/L (+/-), cash, position value, portfolio value
