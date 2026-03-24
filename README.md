# PolyMarket Trading Bot V2

BTC/ETH 5-minute Polymarket bot with paper + live modes.

## Current Status
Implemented and runnable with:
- Strategy engine (current-market only)
- Paper + live execution modes
- Live CLOB bridge (`scripts/polymarket_clob_bridge.py`)
- Optional fill polling (can be disabled for lower latency)
- Separate background market-data feed loop (execution loop reads cached snapshot)
- Optional websocket top-of-book overlay feed (`PMB2_WS_ENABLED=1`)
- Auto-claim loop (live)
- Live account reconciliation + entry pause on drift
- Telegram control commands (`Log`, `Market`, `Snapshot`, `Poly`, `Status`, `Pause`, `Resume`, `Stop`)
- Per-run archived logs/state via `run.sh`

---

## Strategy (as currently coded)
- Markets: BTC + ETH 5-minute up/down
- Uses only most current active market per symbol
- Entry polling starts at the beginning of the final 70-second window
- Entry window: final 70 seconds of market (via `PMB2_FINAL_ENTRY_WINDOW_SECONDS=70`)
- Entry trigger: once either side >= 0.75, buy higher side
- Sizing: proportional-only `10% cash` (no fixed minimum), then capped by risk limits
- Stop-loss: side price <= 60% of entry price (with liquidity)
- Otherwise hold to settlement

---

## Quick Start
From this directory:

```bash
./run.sh
```

`run.sh` behavior:
- Auto-activates `.venv` if present
- Loads `.env.live` first (fallback `.env`)
- Creates run archive folders:
  - `logs/archive/<RUN_ID>/`
  - `state/archive/<RUN_ID>/`
- Updates symlinks:
  - `logs/latest`
  - `state/latest`
- Launches `python3 -m src.main`

---

## Live Mode Setup

Install dependency:

```bash
pip install py-clob-client
```

Set env (normally via `.env.live`):

```bash
PMB2_TRADING_MODE=live
PMB2_LIVE_BRIDGE_CMD=python3 ./scripts/polymarket_clob_bridge.py

POLYMARKET_PRIVATE_KEY=0x...
POLYMARKET_FUNDER=0x...
POLYMARKET_CHAIN_ID=137
POLYMARKET_SIGNATURE_TYPE=2
POLYMARKET_USE_DERIVED_CREDS=1
# GTC|FAK|FOK|GTD (FAK behaves closest to market-style execution)
POLYMARKET_LIVE_ORDER_TYPE=GTC
```

> In live mode, orders are real.
> If you want market-style execution with a protection limit, use `POLYMARKET_LIVE_ORDER_TYPE=FAK`.

---

## Risk / Safety Controls

```bash
PMB2_MAX_POSITION_USD=100
PMB2_MAX_TOTAL_OPEN_USD=300
PMB2_MIN_BUY_TRIGGER_PRICE=0.74
PMB2_MIN_BUY_FILL_PRICE=0.74
PMB2_PAUSE_ON_BUY_FILL_BELOW_MIN=1
PMB2_BUY_CAP_OFFSET=0.00

PMB2_HOT_POLL_SECONDS=0.5
PMB2_BRIDGE_PERSISTENT=1
PMB2_WS_ENABLED=0
PMB2_WS_URL=wss://clob.polymarket.com/ws
# optional for your WS protocol
# PMB2_WS_SUBSCRIBE_PAYLOAD={"type":"subscribe","token_ids":{token_ids_json}}

POLYMARKET_DISABLE_FILL_POLLING=0
POLYMARKET_ORDER_POLL_TIMEOUT_S=8
POLYMARKET_ORDER_POLL_INTERVAL_S=0.4
POLYMARKET_MIN_FILL_PCT=0.95
POLYMARKET_CANCEL_UNFILLED_ON_TIMEOUT=1

PMB2_AUTO_CLAIM_ENABLED=1
PMB2_AUTO_CLAIM_INTERVAL_S=90

PMB2_RECONCILE_ENABLED=1
PMB2_RECONCILE_INTERVAL_S=20
PMB2_RECONCILE_CASH_DRIFT_USD=1.0
```

Reconcile behavior:
- Bot syncs/logs account drift and cash.
- Reconcile/claim checks are skipped in the final entry window to protect order latency.

Manual entry control via Telegram:
- `Pause` / `Resume`

---

## Telegram Commands
- `Log` → bot ledger summary
- `Market` → current BTC/ETH market links
- `Snapshot` → current UP/DOWN prices
- Order notifications: Telegram messages on order placement attempts and explicit fill failures
- Latency metrics in events log (`latency_market_fetch`, `latency_order_submit`, `latency_summary` with p50/p95)
- Hot-window latency guards: deferred non-critical Telegram sends, unchanged-quote skip, deadline-aware command polling skip
- `Poly` → live account summary:
  - Available cash
  - Portfolio value
  - Position value (`portfolio - cash`)
- `Status` → mode, order type, pause state, buy-floor guards, and account summary
- `Pause` → pause new entries
- `Resume` → resume new entries
- `Stop` → final summary + graceful shutdown

Telegram env:

```bash
PMB2_TELEGRAM_ENABLED=1
PMB2_TELEGRAM_BOT_TOKEN=...
PMB2_TELEGRAM_CHAT_ID=...
PMB2_TELEGRAM_POLL_TIMEOUT_S=0
```

---

## Logs / State

Current run:
- `logs/latest/trades.jsonl`
- `logs/latest/events.jsonl`
- `state/latest/status_snapshot.json`

All runs:
- `logs/archive/*`
- `state/archive/*`

---

## Bridge API (for custom bridge implementations)
Bot sends bridge actions:
- `buy`
- `sell`
- `claim`
- `account_state`

Bridge response must be JSON with `ok: true|false`.

Default bridge file:
- `scripts/polymarket_clob_bridge.py`
