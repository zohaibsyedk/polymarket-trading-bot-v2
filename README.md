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

Bridge now tracks **actual order updates/fills** (polling order status) and only returns success after sufficient fill.
Tune with env:
- `POLYMARKET_ORDER_POLL_TIMEOUT_S` (default 8)
- `POLYMARKET_ORDER_POLL_INTERVAL_S` (default 0.4)
- `POLYMARKET_MIN_FILL_PCT` (default 0.95)
- `POLYMARKET_CANCEL_UNFILLED_ON_TIMEOUT` (default 1)

Live mode also supports periodic auto-claim checks:
- `PMB2_AUTO_CLAIM_ENABLED=1`
- `PMB2_AUTO_CLAIM_INTERVAL_S=90`

Live mode reconciliation can tie bot cash to account cash:
- `PMB2_RECONCILE_ENABLED=1`
- `PMB2_RECONCILE_INTERVAL_S=20`
- `PMB2_RECONCILE_CASH_DRIFT_USD=1.0`

If drift exceeds threshold, bot pauses **new entries** until drift is back in range.

The bridge accepts:
- `{"action":"claim"}`
- `{"action":"account_state"}`

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
- `Poly` → account available cash, portfolio value, and position value (portfolio - cash)
- `Pause` → pause new entries (exits still run)
- `Resume` → resume new entries
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
