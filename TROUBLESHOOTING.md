# PolyMarket Trading Bot V2 — Troubleshooting

## 1) Bot starts but no trades happen
- Confirm entry window logic: entries only in first 2 minutes of each 5-minute market.
- Check prices in logs; entry only triggers when UP or DOWN <= 0.20.
- Verify cash gate: no entries if cash < $10.

## 2) Telegram commands not working (`Log`, `Stop`)
- Ensure `.env` has:
  - `PMB2_TELEGRAM_ENABLED=1`
  - valid `PMB2_TELEGRAM_BOT_TOKEN`
- Send `/start` to the bot from your Telegram account.
- If using chat lock, ensure `PMB2_TELEGRAM_CHAT_ID` matches your chat id.

## 3) Telegram message send failures
- Run healthcheck:
```bash
./scripts/healthcheck.sh
```
- If OpenClaw message tool path is flaky, runtime direct Bot API path is used by this bot.
- Re-test token directly:
```bash
curl "https://api.telegram.org/bot$PMB2_TELEGRAM_BOT_TOKEN/getMe"
```

## 4) Market resolve failures
- This bot depends on Polymarket Gamma API availability.
- Run healthcheck and confirm BTC/ETH slug resolution.
- If repeatedly failing, wait and re-run; log events in `logs/events.jsonl`.

## 5) State/accounting sanity check
- Run deterministic M4 simulation:
```bash
python3 tests/simulate_m4.py
```
- Expect `ok: true` and balanced entries/exits.

## 6) Where to inspect runtime
- Trades: `logs/trades.jsonl`
- Events: `logs/events.jsonl`
- Snapshot: `state/status_snapshot.json`
