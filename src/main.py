import time
from .config import BotConfig
from .market_discovery import current_5m_window
from .paper_engine import PortfolioState
from .models import QuoteSnapshot
from .strategy import evaluate_entry
from .notifier import format_entry_message, format_exit_message
from .logging_io import append_jsonl, write_json
from .telegram_commands import handle_command
from .telegram_io import TelegramIO
from .market_data import resolve_current_market, resolve_settlement_payout


def run() -> None:
    cfg = BotConfig()
    portfolio = PortfolioState(cash_available=cfg.starting_cash)

    trades_log = cfg.logs_dir / "trades.jsonl"
    events_log = cfg.logs_dir / "events.jsonl"
    status_path = cfg.state_dir / "status_snapshot.json"

    tg = TelegramIO(
        token=cfg.telegram_bot_token if cfg.telegram_enabled else "",
        default_chat_id=cfg.telegram_chat_id,
        poll_timeout_s=cfg.telegram_poll_timeout_s,
    )

    def send(msg: str):
        print("\n--- BOT MESSAGE ---\n" + msg + "\n--- END ---\n")
        tg.send(msg)

    stop_requested = False

    if cfg.telegram_enabled and cfg.telegram_bot_token:
        send("[PolyMarket Trading Bot V2]\n[Status: Started]\n[Commands: Log, Market, Snapshot, Stop]")

    while not stop_requested:
        now_ts = int(time.time())
        window = current_5m_window(now_ts)

        # resolve market map first so command `Market` has current links
        active = {}
        for symbol in ("BTC", "ETH"):
            market = resolve_current_market(symbol, window.ts_bucket, now_ts)
            if market:
                active[symbol] = market

        # Telegram command polling
        for chat_id, text in tg.poll_commands():
            if cfg.telegram_chat_id and chat_id != cfg.telegram_chat_id:
                continue
            resp, should_stop = handle_command(
                text,
                portfolio,
                {k: v.slug for k, v in active.items()},
                {k: {"slug": v.slug, "up": v.up_price, "down": v.down_price} for k, v in active.items()},
            )
            tg.send(resp, chat_id=chat_id)
            append_jsonl(events_log, {"type": "command", "ts": now_ts, "chat_id": chat_id, "text": text, "stop": should_stop})
            if should_stop:
                stop_requested = True

        if stop_requested:
            break

        # Resolve most current market per symbol (already resolved for command handling)
        for symbol in ("BTC", "ETH"):
            if symbol not in active:
                append_jsonl(events_log, {"type": "market_missing", "ts": now_ts, "symbol": symbol, "bucket": window.ts_bucket})

        # ENTRY decisions only on current active markets
        for symbol, market in active.items():
            elapsed = now_ts - market.market_ts
            if elapsed < 0:
                append_jsonl(events_log, {"type": "skip_future_market", "ts": now_ts, "symbol": symbol, "market_ts": market.market_ts})
                continue

            if not market.accepting_orders:
                append_jsonl(events_log, {"type": "skip_not_accepting_orders", "ts": now_ts, "symbol": symbol, "slug": market.slug})
                continue

            symbol_open = [
                p for p in portfolio.open_positions.values()
                if p.symbol == symbol and p.market_ts == market.market_ts
            ]
            if symbol_open:
                continue

            quote = QuoteSnapshot(
                symbol=symbol,
                market_ts=market.market_ts,
                up_price=market.entry_up_price,
                down_price=market.entry_down_price,
                ts=now_ts,
            )

            entry = evaluate_entry(cfg, quote, elapsed, portfolio.cash_available)
            append_jsonl(events_log, {
                "type": "entry_check",
                "ts": now_ts,
                "symbol": symbol,
                "market_ts": market.market_ts,
                "slug": market.slug,
                "elapsed": elapsed,
                "cash_available": portfolio.cash_available,
                "up_trigger_price": quote.up_price,
                "down_trigger_price": quote.down_price,
                "decision": {
                    "should_enter": entry.should_enter,
                    "reason": entry.reason,
                    "side": entry.side,
                    "price": entry.price,
                    "size_usd": entry.size_usd,
                },
            })
            if entry.should_enter and entry.side and entry.price and entry.size_usd:
                p = portfolio.create_position(symbol, market.market_ts, entry.side, entry.price, now_ts, entry.size_usd)
                send(format_entry_message(p, portfolio))
                append_jsonl(trades_log, {
                    "type": "entry",
                    "ts": now_ts,
                    "position": p.to_dict(),
                    "reason": entry.reason,
                    "slug": market.slug,
                })

        # EXIT at market close settlement only: payout is 1.0 for winner, 0.0 for loser
        for p in list(portfolio.open_positions.values()):
            payout = resolve_settlement_payout(p.symbol, p.market_ts, p.side)
            if payout is None:
                continue
            closed = portfolio.close_position(p.position_id, payout, now_ts)
            send(format_exit_message(closed, portfolio))
            append_jsonl(trades_log, {
                "type": "exit",
                "ts": now_ts,
                "position": closed.to_dict(),
                "reason": "market_settlement",
                "payout_per_contract": payout,
            })

        snapshot = {
            "ts": now_ts,
            "active_market_ts": {k: v.market_ts for k, v in active.items()},
            "active_market_slug": {k: v.slug for k, v in active.items()},
            "cash_available": portfolio.cash_available,
            "open_position_value": portfolio.open_position_value,
            "portfolio_value": portfolio.portfolio_value,
            "open_positions": [p.to_dict() for p in portfolio.open_positions.values()],
            "realized_pnl": portfolio.realized_pnl(),
        }
        write_json(status_path, snapshot)
        append_jsonl(events_log, {
            "type": "tick",
            "ts": now_ts,
            "active": {k: {"ts": v.market_ts, "slug": v.slug, "up": v.up_price, "down": v.down_price, "entry_up": v.entry_up_price, "entry_down": v.entry_down_price, "bid_up": v.bid_up_price, "ask_up": v.ask_up_price, "bid_down": v.bid_down_price, "ask_down": v.ask_down_price} for k, v in active.items()},
            "open_positions": len(portfolio.open_positions),
        })

        time.sleep(cfg.poll_seconds)

    final_msg = handle_command("log", portfolio)[0] + "\n[Bot stopped]"
    send(final_msg)
    append_jsonl(events_log, {"type": "stopped", "ts": int(time.time())})


if __name__ == "__main__":
    run()
