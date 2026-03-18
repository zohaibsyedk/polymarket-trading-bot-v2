# PolyMarket Trading Bot V2 — Architecture

## Objective
Paper-trading bot for Polymarket BTC/ETH 5-minute up/down markets that:
- always tracks the current live 5-minute interval market
- applies deterministic entry/exit rules
- sends entry/exit notifications
- supports Telegram commands: `Log`, `Stop`

## System Components

1. **Market Discovery** (`src/market_discovery.py`)
   - Computes current 5-minute UNIX timestamp window
   - Builds candidate slugs:
     - `btc-updown-5m-{ts}`
     - `eth-updown-5m-{ts}`
   - Resolves active market metadata for current interval only

2. **Market Data Adapter** (`src/market_data.py`)
   - Fetches latest quote data for UP/DOWN contracts
   - Normalizes quote schema: bid/ask/last per side
   - Provides price snapshots to strategy engine

3. **Strategy Engine** (`src/strategy.py`)
   - Entry window: first 2 minutes of 5-minute market
   - Entry trigger: if either side reaches $0.20
   - Position sizing: `max($10, 3% of cash_available)` with cash gate
   - Exit rules:
     - Rule Set 1 (pre-last-minute): TP @ $0.40, SL @ $0.10
     - Rule Set 2 (last minute): force close any open position

4. **Paper Portfolio Engine** (`src/paper_engine.py`)
   - Tracks:
     - cash_available
     - open_position_value (entry-cost basis)
     - portfolio_value = cash_available + open_position_value
   - Creates position IDs
   - Applies fills and updates balances

5. **Notifier** (`src/notifier.py`)
   - Sends formatted Entry/Exit messages with exact fields requested
   - Supports stdout fallback when Telegram is disabled

6. **Command Handler** (`src/telegram_commands.py`)
   - `Log`: open positions, P&L, account balance
   - `Stop`: sends final log summary and gracefully stops loop

7. **Runtime Orchestrator** (`src/main.py`)
   - Main polling loop
   - Refreshes active markets each cycle
   - Executes strategy decisions
   - Persists event logs and status snapshots

## Data & Logs

- `logs/trades.jsonl` — append-only trade events
- `logs/events.jsonl` — lifecycle + diagnostics
- `state/status_snapshot.json` — latest dashboard state

## Safety Constraints

- Paper mode only (no real order placement)
- No entries if `cash_available < $10`
- At most one active position per market-side entry event (configurable later)
- Deterministic decimal handling for price/size calculations

## Planned Implementation Sequence

1. Scaffolding + config + models
2. Paper portfolio state machine
3. Strategy rule implementation
4. Market discovery + quote adapters
5. Telegram notifier + commands
6. End-to-end simulation tests on mocked feeds
