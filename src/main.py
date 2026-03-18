import time
from .config import BotConfig
from .market_discovery import current_5m_window
from .paper_engine import PortfolioState
from .models import QuoteSnapshot
from .strategy import evaluate_entry, evaluate_exit
from .notifier import format_entry_message, format_exit_message
from .logging_io import append_jsonl, write_json
from .telegram_commands import handle_command
from .telegram_io import TelegramIO
from .market_data import resolve_current_market, fetch_market


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
        send("[PolyMarket Trading Bot V2]\n[Status: Started]\n[Commands: Log, Stop]")

    while not stop_requested:
        now_ts = int(time.time())
        window = current_5m_window(now_ts)

        # Telegram command polling
        for chat_id, text in tg.poll_commands():
            if cfg.telegram_chat_id and chat_id != cfg.telegram_chat_id:
                continue
            resp, should_stop = handle_command(text, portfolio)
            tg.send(resp, chat_id=chat_id)
            append_jsonl(events_log, {"type": "command", "ts": now_ts, "chat_id": chat_id, "text": text, "stop": should_stop})
            if should_stop:
                stop_requested = True

        if stop_requested:
            break

        # Resolve most current market per symbol
        active = {}
        for symbol in ("BTC", "ETH"):
            market = resolve_current_market(symbol, window.ts_bucket)
            if market:
                active[symbol] = market
            else:
                append_jsonl(events_log, {"type": "market_missing", "ts": now_ts, "symbol": symbol, "bucket": window.ts_bucket})

        # ENTRY decisions only on current active markets
        for symbol, market in active.items():
            elapsed = now_ts - market.market_ts
            if elapsed < 0:
                # market timestamp is in near future; skip until active
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
                up_price=market.up_price,
                down_price=market.down_price,
                ts=now_ts,
            )

            entry = evaluate_entry(cfg, quote, elapsed, portfolio.cash_available)
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

        # EXIT decisions for all open positions (including older bucket if still open)
        for p in list(portfolio.open_positions.values()):
            elapsed_for_pos = now_ts - p.market_ts
            m = fetch_market(p.symbol, p.market_ts)
            if not m:
                # if unavailable and we're beyond market end, force close pessimistically at 0
                if elapsed_for_pos >= cfg.market_interval_seconds:
                    closed = portfolio.close_position(p.position_id, 0.0, now_ts)
                    send(format_exit_message(closed, portfolio))
                    append_jsonl(trades_log, {
                        "type": "exit",
                        "ts": now_ts,
                        "position": closed.to_dict(),
                        "reason": "forced_no_quote_after_close",
                    })
                continue

            quote = QuoteSnapshot(
                symbol=p.symbol,
                market_ts=p.market_ts,
                up_price=m.up_price,
                down_price=m.down_price,
                ts=now_ts,
            )

            exit_decision = evaluate_exit(cfg, p, quote, elapsed_for_pos)
            if exit_decision.should_exit and exit_decision.price is not None:
                closed = portfolio.close_position(p.position_id, exit_decision.price, now_ts)
                send(format_exit_message(closed, portfolio))
                append_jsonl(trades_log, {
                    "type": "exit",
                    "ts": now_ts,
                    "position": closed.to_dict(),
                    "reason": exit_decision.reason,
                    "slug": m.slug,
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
            "active": {k: {"ts": v.market_ts, "slug": v.slug, "up": v.up_price, "down": v.down_price} for k, v in active.items()},
            "open_positions": len(portfolio.open_positions),
        })

        time.sleep(cfg.poll_seconds)

    final_msg = handle_command("log", portfolio)[0] + "\n[Bot stopped]"
    send(final_msg)
    append_jsonl(events_log, {"type": "stopped", "ts": int(time.time())})


if __name__ == "__main__":
    run()
