# PolyMarket Trading Bot V2

Trading bot for BTC/ETH 5-minute Polymarket up/down markets.

Supports:
- `paper` mode (default): simulated fills, internal accounting
- `live` mode: executes via an external bridge command

## Current Strategy (as coded)
- Works only on the most current 5-minute market per symbol
- Entry window: final 50 seconds of market
- Entry trigger: once either side reaches >= 0.75, buy the higher side
- Position size: `max($50, 10% cash)` capped by risk vars
- Stop loss: side price <= 60% of entry (with liquidity)
- Otherwise exit at settlement

## Run
```bash
cd polymarket-bots/polymarket-trading-bot-v2
python3 -m src.main
```

## Modes

### Paper mode (default)
```bash
export PMB2_TRADING_MODE=paper
python3 -m src.main
```

### Live mode (bridge-based)
```bash
export PMB2_TRADING_MODE=live
export PMB2_LIVE_BRIDGE_CMD='python3 /abs/path/to/scripts/polymarket_clob_bridge.py'

# bridge auth env
export POLYMARKET_PRIVATE_KEY='0x...'
export POLYMARKET_FUNDER='0x...'

python3 -m src.main
```

`PMB2_LIVE_BRIDGE_CMD` must read JSON from stdin and return JSON on stdout.
A ready bridge is provided at `scripts/polymarket_clob_bridge.py`.

Buy payload sent by bot:
```json
{"action":"buy","symbol":"BTC","market_ts":123,"side":"UP","limit_price":0.81,"size_usd":50}
```
Expected buy response:
```json
{"ok":true,"fill_price":0.81,"contracts":61.728395,"cost":50,"order_id":"abc"}
```

Sell payload sent by bot:
```json
{"action":"sell","symbol":"BTC","market_ts":123,"side":"UP","contracts":61.728395,"limit_price":0.52}
```
Expected sell response:
```json
{"ok":true,"fill_price":0.52,"proceeds":32.098765,"order_id":"def"}
```

## Risk Controls (env)
```bash
export PMB2_MAX_POSITION_USD=100
export PMB2_MAX_TOTAL_OPEN_USD=300
```

## Telegram Commands
- `Log` → open positions, realized P&L, cash, position value, portfolio value
- `Market` → current BTC/ETH market links
- `Snapshot` → current UP/DOWN prices
- `Stop` → final summary and graceful shutdown

Enable Telegram:
```bash
export PMB2_TELEGRAM_ENABLED=1
export PMB2_TELEGRAM_BOT_TOKEN='YOUR_BOT_TOKEN'
export PMB2_TELEGRAM_CHAT_ID='YOUR_CHAT_ID'
export PMB2_TELEGRAM_POLL_TIMEOUT_S=0
```

## Logs
```bash
cat logs/trades.jsonl
tail -f logs/events.jsonl
cat state/status_snapshot.json
```
