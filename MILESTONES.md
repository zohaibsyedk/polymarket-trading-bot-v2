# PolyMarket Trading Bot V2 — Milestones

## M0 — Foundation (now)
- [x] Project scaffold created
- [x] Spec copied into project
- [x] Architecture + milestones documented
- [x] Logging/state directories created

## M1 — Core Simulation Engine
- [ ] Implement portfolio accounting (cash/open value/portfolio value)
- [ ] Implement position model + deterministic IDs
- [ ] Implement entry/exit rule evaluation
- [ ] Persist trades/events/snapshots

## M2 — Market Targeting (Current 5m only)
- [x] Implement interval timestamp generator
- [x] Resolve active BTC/ETH market IDs by interval
- [x] Add quote polling for UP/DOWN contracts
- [x] Auto-roll to newest interval market when time advances

## M3 — Notification & Control
- [x] Entry message format per spec
- [x] Exit message format per spec
- [x] Telegram command: `Log`
- [x] Telegram command: `Stop`

## M4 — Reliability & Validation
- [x] Simulated run on mocked feed data for at least 50 intervals
- [x] Validate all entry/exit constraints and forced last-minute exits
- [x] Reconciliation check for cash + open value consistency
- [x] Add runtime health heartbeat/event markers

## M5 — Operator UX
- [x] One-command start script
- [x] Clear README for setup/run/log access
- [x] Troubleshooting guide for API/Telegram failures


## M6 — Strategy Revision (Final 80s Momentum + Settlement)
- [x] Entry only in final 90 seconds of each market, and only after a side reaches >= $0.70
- [x] Enter higher-priced side (UP vs DOWN)
- [x] Remove intramarket TP/SL exits
- [x] Exit only at market close with payout 1/0 per contract
