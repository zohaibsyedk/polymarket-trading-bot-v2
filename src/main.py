import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from .config import BotConfig
from .market_discovery import current_5m_window
from .paper_engine import PortfolioState
from .models import QuoteSnapshot
from .strategy import evaluate_entry
from .execution import PaperExecutionEngine, LiveExecutionBridgeEngine
from .notifier import format_entry_message, format_exit_message
from .logging_io import append_jsonl, write_json
from .telegram_commands import handle_command
from .telegram_io import TelegramIO
from .market_data import resolve_current_market, resolve_settlement_payout, fetch_market


def run() -> None:
    cfg = BotConfig()
    if cfg.trading_mode not in {"paper", "live"}:
        raise ValueError("PMB2_TRADING_MODE must be 'paper' or 'live'")

    portfolio = PortfolioState(cash_available=cfg.starting_cash)

    trades_log = cfg.logs_dir / "trades.jsonl"
    events_log = cfg.logs_dir / "events.jsonl"
    status_path = cfg.state_dir / "status_snapshot.json"

    tg = TelegramIO(
        token=cfg.telegram_bot_token if cfg.telegram_enabled else "",
        default_chat_id=cfg.telegram_chat_id,
        poll_timeout_s=cfg.telegram_poll_timeout_s,
    )

    if cfg.trading_mode == "live":
        engine = LiveExecutionBridgeEngine(
            cfg.live_bridge_cmd,
            timeout_seconds=cfg.live_bridge_timeout_s,
            persistent=cfg.bridge_persistent,
        )
    else:
        engine = PaperExecutionEngine()

    def send(msg: str):
        print("\n--- BOT MESSAGE ---\n" + msg + "\n--- END ---\n")
        # Defer non-critical Telegram sends during hot window to reduce latency jitter.
        if in_hot_window:
            deferred_telegram_msgs.append(msg)
            return
        tg.send(msg)

    stop_requested = False
    last_claim_check_ts = 0
    last_reconcile_ts = 0
    trading_paused_by_reconcile = False
    manual_entries_paused = False
    latest_live_account: dict = {}
    last_market_bucket_seen: int | None = None
    in_hot_window = False
    deferred_telegram_msgs: list[str] = []
    last_entry_quote_sig: dict[tuple[str, int], tuple[float, float]] = {}

    # Startup sync in live mode: seed bot cash/portfolio view from account state.
    if cfg.trading_mode == "live":
        try:
            acct = engine.get_account_state()
            bridge_cash = acct.get("cash_available")
            bridge_portfolio_value = acct.get("portfolio_value")

            if bridge_portfolio_value is None and bridge_cash is not None:
                pos_val = 0.0
                for row in (acct.get("positions") or []):
                    if not isinstance(row, dict):
                        continue
                    for k in ("value", "current_value", "market_value", "position_value", "notional", "usd_value"):
                        if row.get(k) is not None:
                            try:
                                pos_val += float(row.get(k))
                                break
                            except Exception:
                                pass
                bridge_portfolio_value = float(bridge_cash) + pos_val
                acct["portfolio_value"] = round(float(bridge_portfolio_value), 6)

            latest_live_account = {
                "cash_available": bridge_cash,
                "portfolio_value": acct.get("portfolio_value"),
                "positions": acct.get("positions") or [],
            }

            if bridge_cash is not None:
                portfolio.cash_available = round(float(bridge_cash), 6)
        except Exception as e:
            append_jsonl(events_log, {
                "type": "startup_reconcile_failed",
                "ts": int(time.time()),
                "error": str(e),
            })

    if cfg.telegram_enabled and cfg.telegram_bot_token:
        send(
            "[PolyMarket Trading Bot V2]\n"
            f"[Status: Started - Mode: {cfg.trading_mode.upper()}]\n"
            "[Commands: Log, Market, Snapshot, Poly, Status, Pause, Resume, Stop]"
        )

    while not stop_requested:
        now_ts = int(time.time())
        window = current_5m_window(now_ts)
        sec_in_market = now_ts % cfg.market_interval_seconds
        in_hot_window = sec_in_market >= (cfg.market_interval_seconds - cfg.final_entry_window_seconds)

        # market rollover update (start of following market)
        if cfg.trading_mode == "live":
            if last_market_bucket_seen is None:
                last_market_bucket_seen = window.ts_bucket
            elif window.ts_bucket != last_market_bucket_seen:
                last_market_bucket_seen = window.ts_bucket
                try:
                    acct = engine.get_account_state()
                    cash = acct.get("cash_available")
                    port = acct.get("portfolio_value")
                    if port is None and cash is not None:
                        port = cash
                    if cash is not None or port is not None:
                        cash_f = float(cash) if cash is not None else 0.0
                        port_f = float(port) if port is not None else cash_f
                        send(
                            "[Market Rollover Update] "
                            f"[Cash: ${cash_f:.4f}] "
                            f"[Portfolio: ${port_f:.4f}] "
                            f"[Position Value: ${port_f - cash_f:.4f}]"
                        )
                except Exception as e:
                    append_jsonl(events_log, {
                        "type": "rollover_update_failed",
                        "ts": now_ts,
                        "error": str(e),
                    })

        # live-mode auto-claim checks (skip during final entry window to protect latency)
        if cfg.trading_mode == "live" and cfg.auto_claim_enabled:
            sec_in_market = now_ts % cfg.market_interval_seconds
            in_final_entry_window = sec_in_market >= (cfg.market_interval_seconds - cfg.final_entry_window_seconds)
            if in_final_entry_window:
                append_jsonl(events_log, {
                    "type": "claim_skipped_final_window",
                    "ts": now_ts,
                    "sec_in_market": sec_in_market,
                    "final_entry_window_seconds": cfg.final_entry_window_seconds,
                })
            elif (now_ts - last_claim_check_ts) >= max(15, cfg.auto_claim_interval_s):
                last_claim_check_ts = now_ts
                try:
                    claim = engine.claim_available_funds()
                    append_jsonl(events_log, {
                        "type": "claim_check",
                        "ts": now_ts,
                        "result": claim,
                    })
                    claimed_amt = float(claim.get("claimed", 0.0) or 0.0)
                    if claimed_amt > 0:
                        send(f"[Claimed: ${claimed_amt:.4f}]")
                except Exception as e:
                    append_jsonl(events_log, {
                        "type": "claim_failed",
                        "ts": now_ts,
                        "error": str(e),
                    })

        # live-mode reconciliation checks
        if cfg.trading_mode == "live" and cfg.reconcile_enabled:
            sec_in_market = now_ts % cfg.market_interval_seconds
            in_final_entry_window = sec_in_market >= (cfg.market_interval_seconds - cfg.final_entry_window_seconds)
            if in_final_entry_window:
                append_jsonl(events_log, {
                    "type": "reconcile_skipped_final_window",
                    "ts": now_ts,
                    "sec_in_market": sec_in_market,
                    "final_entry_window_seconds": cfg.final_entry_window_seconds,
                })
            elif (now_ts - last_reconcile_ts) >= max(5, cfg.reconcile_interval_s):
                last_reconcile_ts = now_ts
                try:
                    acct = engine.get_account_state()
                    bridge_cash = acct.get("cash_available")

                    # Fill derived totals when bridge cannot provide direct portfolio value.
                    bridge_portfolio_value = acct.get("portfolio_value")
                    if bridge_portfolio_value is None and bridge_cash is not None:
                        pos_val = 0.0
                        for row in (acct.get("positions") or []):
                            if not isinstance(row, dict):
                                continue
                            for k in ("value", "current_value", "market_value", "position_value", "notional", "usd_value"):
                                if row.get(k) is not None:
                                    try:
                                        pos_val += float(row.get(k))
                                        break
                                    except Exception:
                                        pass
                        bridge_portfolio_value = float(bridge_cash) + pos_val
                        acct["portfolio_value"] = round(float(bridge_portfolio_value), 6)

                    latest_live_account = {
                        "cash_available": bridge_cash,
                        "portfolio_value": acct.get("portfolio_value"),
                        "positions": acct.get("positions") or [],
                    }

                    cash_drift = None
                    trading_paused_by_reconcile = False
                    if bridge_cash is not None:
                        bridge_cash = float(bridge_cash)
                        cash_drift = round(abs(bridge_cash - portfolio.cash_available), 6)
                        # Reconcile now logs drift but does not pause entries.
                        portfolio.cash_available = round(bridge_cash, 6)

                    append_jsonl(events_log, {
                        "type": "reconcile_check",
                        "ts": now_ts,
                        "account_state": acct,
                        "cash_drift": cash_drift,
                        "paused_entries": trading_paused_by_reconcile,
                    })
                except Exception as e:
                    append_jsonl(events_log, {
                        "type": "reconcile_failed",
                        "ts": now_ts,
                        "error": str(e),
                    })

        # resolve market map first so command `Market` has current links
        fetch_t0 = time.perf_counter()
        active = {}
        with ThreadPoolExecutor(max_workers=2) as ex:
            futs = {ex.submit(resolve_current_market, symbol, window.ts_bucket, now_ts): symbol for symbol in ("BTC", "ETH")}
            for fut in as_completed(futs):
                symbol = futs[fut]
                try:
                    market = fut.result()
                except Exception:
                    market = None
                if market:
                    active[symbol] = market
        append_jsonl(events_log, {
            "type": "latency_market_fetch",
            "ts": now_ts,
            "ms": round((time.perf_counter() - fetch_t0) * 1000, 2),
            "symbols": list(active.keys()),
        })

        # Telegram command polling
        for chat_id, text in tg.poll_commands():
            if cfg.telegram_chat_id and chat_id != cfg.telegram_chat_id:
                continue
            resp, should_stop, control_action = handle_command(
                text,
                portfolio,
                {k: v.slug for k, v in active.items()},
                {k: {"slug": v.slug, "up": v.up_price, "down": v.down_price} for k, v in active.items()},
                latest_live_account,
                manual_entries_paused or trading_paused_by_reconcile,
                {
                    "trading_mode": cfg.trading_mode,
                    "order_type": os.getenv("POLYMARKET_LIVE_ORDER_TYPE", "GTC").upper(),
                    "min_buy_trigger_price": cfg.min_buy_trigger_price,
                    "min_buy_fill_price": cfg.min_buy_fill_price,
                    "pause_on_buy_fill_below_min": cfg.pause_on_buy_fill_below_min,
                },
            )
            if control_action == "pause":
                manual_entries_paused = True
            elif control_action == "resume":
                manual_entries_paused = False

            tg.send(resp, chat_id=chat_id)
            append_jsonl(events_log, {
                "type": "command",
                "ts": now_ts,
                "chat_id": chat_id,
                "text": text,
                "stop": should_stop,
                "control_action": control_action,
                "manual_entries_paused": manual_entries_paused,
            })
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
            if trading_paused_by_reconcile or manual_entries_paused:
                append_jsonl(events_log, {
                    "type": "entry_blocked_pause",
                    "ts": now_ts,
                    "symbol": symbol,
                    "market_ts": market.market_ts,
                    "slug": market.slug,
                    "reconcile_pause": trading_paused_by_reconcile,
                    "manual_pause": manual_entries_paused,
                })
                continue
            elapsed = now_ts - market.market_ts
            if elapsed < 0:
                append_jsonl(events_log, {"type": "skip_future_market", "ts": now_ts, "symbol": symbol, "market_ts": market.market_ts})
                continue

            poll_start = cfg.market_interval_seconds - cfg.final_entry_window_seconds
            if elapsed < poll_start:
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

            # Prebuild hint when quote is near trigger to reduce work at decision edge.
            if max(quote.up_price, quote.down_price) >= (cfg.entry_min_price_threshold - 0.05):
                append_jsonl(events_log, {
                    "type": "entry_prebuild_hint",
                    "ts": now_ts,
                    "symbol": symbol,
                    "market_ts": market.market_ts,
                    "up": quote.up_price,
                    "down": quote.down_price,
                })

            qkey = (symbol, market.market_ts)
            qsig = (round(float(quote.up_price), 6), round(float(quote.down_price), 6))
            if last_entry_quote_sig.get(qkey) == qsig:
                append_jsonl(events_log, {
                    "type": "entry_check_skipped_unchanged_quote",
                    "ts": now_ts,
                    "symbol": symbol,
                    "market_ts": market.market_ts,
                })
                continue
            last_entry_quote_sig[qkey] = qsig

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
                if float(entry.price) < cfg.min_buy_trigger_price:
                    append_jsonl(events_log, {
                        "type": "entry_blocked_min_buy_trigger",
                        "ts": now_ts,
                        "symbol": symbol,
                        "market_ts": market.market_ts,
                        "entry_price": float(entry.price),
                        "min_buy_trigger_price": cfg.min_buy_trigger_price,
                    })
                    continue

                intended_size = min(entry.size_usd, cfg.max_position_usd)
                if portfolio.open_position_value + intended_size > cfg.max_total_open_usd:
                    append_jsonl(events_log, {
                        "type": "entry_blocked_risk",
                        "ts": now_ts,
                        "symbol": symbol,
                        "market_ts": market.market_ts,
                        "size_usd": intended_size,
                        "max_total_open_usd": cfg.max_total_open_usd,
                    })
                    continue
                token_id = market.up_token_id if entry.side == "UP" else market.down_token_id
                submit_t0 = time.perf_counter()
                try:
                    p = engine.enter_position(
                        portfolio=portfolio,
                        symbol=symbol,
                        market_ts=market.market_ts,
                        side=entry.side,
                        limit_price=entry.price,
                        size_usd=intended_size,
                        now_ts=now_ts,
                        token_id=token_id,
                    )
                except Exception as e:
                    err = str(e)
                    append_jsonl(events_log, {
                        "type": "latency_order_submit",
                        "ts": now_ts,
                        "symbol": symbol,
                        "market_ts": market.market_ts,
                        "action": "entry_failed",
                        "ms": round((time.perf_counter() - submit_t0) * 1000, 2),
                    })
                    send(
                        "[Fill Failed] "
                        f"[{symbol} {entry.side}] "
                        f"[Market: {market.slug}] "
                        f"[Limit: {float(entry.price):.4f}] "
                        f"[Size USD: {float(intended_size):.2f}] "
                        f"[Error: {err}]"
                    )
                    append_jsonl(events_log, {
                        "type": "entry_failed",
                        "ts": now_ts,
                        "symbol": symbol,
                        "market_ts": market.market_ts,
                        "slug": market.slug,
                        "error": err,
                    })
                    continue

                append_jsonl(events_log, {
                    "type": "latency_order_submit",
                    "ts": now_ts,
                    "symbol": symbol,
                    "market_ts": market.market_ts,
                    "action": "entry",
                    "ms": round((time.perf_counter() - submit_t0) * 1000, 2),
                })

                send(
                    "[Order Placed] "
                    f"[{symbol} {entry.side}] "
                    f"[Market: {market.slug}] "
                    f"[Limit: {float(entry.price):.4f}] "
                    f"[Size USD: {float(intended_size):.2f}] "
                    f"[Order ID: {p.entry_order_id or 'n/a'}]"
                )

                if p.entry_price < cfg.min_buy_fill_price:
                    warn = (
                        "[Buy Fill Guard] "
                        f"Filled at {p.entry_price:.4f} below minimum {cfg.min_buy_fill_price:.4f}."
                    )
                    send(warn)
                    append_jsonl(events_log, {
                        "type": "buy_fill_below_min",
                        "ts": now_ts,
                        "symbol": symbol,
                        "market_ts": market.market_ts,
                        "filled_price": p.entry_price,
                        "min_buy_fill_price": cfg.min_buy_fill_price,
                    })
                    if cfg.pause_on_buy_fill_below_min:
                        manual_entries_paused = True
                        send("[Trading] Entries paused due to buy-fill guard.")

                send(format_entry_message(p, portfolio))
                append_jsonl(trades_log, {
                    "type": "entry",
                    "ts": now_ts,
                    "position": p.to_dict(),
                    "reason": entry.reason,
                    "slug": market.slug,
                    "mode": cfg.trading_mode,
                })

        # EXIT rules:
        # 1) Stop-loss before close: if side price <= (entry_price * 0.60) and there is sell-side liquidity, exit.
        # 2) Otherwise hold to settlement and payout at close (1/0).
        for p in list(portfolio.open_positions.values()):
            m = fetch_market(p.symbol, p.market_ts)
            if m is not None:
                side_price = m.up_price if p.side == "UP" else m.down_price
                side_liquidity_px = m.bid_up_price if p.side == "UP" else m.bid_down_price
                stop_loss_price = round(p.entry_price * cfg.stop_loss_pct_of_entry, 6)
                if side_price <= stop_loss_price and side_liquidity_px is not None and side_liquidity_px > 0:
                    exit_t0 = time.perf_counter()
                    try:
                        closed = engine.exit_position(
                            portfolio=portfolio,
                            p=p,
                            limit_price=side_liquidity_px,
                            now_ts=now_ts,
                        )
                    except Exception as e:
                        err = str(e)
                        append_jsonl(events_log, {
                            "type": "latency_order_submit",
                            "ts": now_ts,
                            "symbol": p.symbol,
                            "market_ts": p.market_ts,
                            "action": "exit_failed",
                            "ms": round((time.perf_counter() - exit_t0) * 1000, 2),
                        })
                        send(
                            "[Fill Failed] "
                            f"[{p.symbol} EXIT {p.side}] "
                            f"[Reason: STOP_LOSS] "
                            f"[Limit: {float(side_liquidity_px):.4f}] "
                            f"[Contracts: {float(p.contracts):.4f}] "
                            f"[Error: {err}]"
                        )
                        append_jsonl(events_log, {
                            "type": "exit_failed",
                            "ts": now_ts,
                            "position_id": p.position_id,
                            "reason": "stop_loss",
                            "error": err,
                        })
                        continue

                    append_jsonl(events_log, {
                        "type": "latency_order_submit",
                        "ts": now_ts,
                        "symbol": p.symbol,
                        "market_ts": p.market_ts,
                        "action": "exit",
                        "ms": round((time.perf_counter() - exit_t0) * 1000, 2),
                    })
                    send(
                        "[Order Placed] "
                        f"[{p.symbol} EXIT {p.side}] "
                        f"[Reason: STOP_LOSS] "
                        f"[Limit: {float(side_liquidity_px):.4f}] "
                        f"[Contracts: {float(p.contracts):.4f}] "
                        f"[Order ID: {closed.exit_order_id or 'n/a'}]"
                    )
                    send(format_exit_message(closed, portfolio))
                    append_jsonl(trades_log, {
                        "type": "exit",
                        "ts": now_ts,
                        "position": closed.to_dict(),
                        "reason": "stop_loss_60pct_of_entry_with_liquidity",
                        "market_price": side_price,
                        "stop_loss_price": stop_loss_price,
                        "executed_price": side_liquidity_px,
                        "mode": cfg.trading_mode,
                    })
                    continue

            payout = resolve_settlement_payout(p.symbol, p.market_ts, p.side)
            if payout is None:
                continue
            # Settlement does not require placing a CLOB order.
            # Close position locally at resolved payout; claim/reconcile handles account cash updates.
            closed = portfolio.close_position(p.position_id, payout, now_ts)

            send(format_exit_message(closed, portfolio))
            append_jsonl(trades_log, {
                "type": "exit",
                "ts": now_ts,
                "position": closed.to_dict(),
                "reason": "market_settlement",
                "payout_per_contract": payout,
                "mode": cfg.trading_mode,
            })

        snapshot = {
            "ts": now_ts,
            "trading_mode": cfg.trading_mode,
            "active_market_ts": {k: v.market_ts for k, v in active.items()},
            "active_market_slug": {k: v.slug for k, v in active.items()},
            "cash_available": portfolio.cash_available,
            "open_position_value": portfolio.open_position_value,
            "portfolio_value": portfolio.portfolio_value,
            "open_positions": [p.to_dict() for p in portfolio.open_positions.values()],
            "realized_pnl": portfolio.realized_pnl(),
            "paused_entries": (trading_paused_by_reconcile or manual_entries_paused),
            "paused_entries_reconcile": trading_paused_by_reconcile,
            "paused_entries_manual": manual_entries_paused,
            "live_account": latest_live_account,
        }
        write_json(status_path, snapshot)
        append_jsonl(events_log, {
            "type": "tick",
            "ts": now_ts,
            "active": {k: {"ts": v.market_ts, "slug": v.slug, "up": v.up_price, "down": v.down_price, "entry_up": v.entry_up_price, "entry_down": v.entry_down_price, "bid_up": v.bid_up_price, "ask_up": v.ask_up_price, "bid_down": v.bid_down_price, "ask_down": v.ask_down_price} for k, v in active.items()},
            "open_positions": len(portfolio.open_positions),
        })

        # Flush deferred Telegram sends when we leave the hot window.
        if not in_hot_window and deferred_telegram_msgs:
            for m in deferred_telegram_msgs[:]:
                tg.send(m)
            deferred_telegram_msgs.clear()

        if in_hot_window:
            sleep_s = cfg.hot_poll_seconds
        else:
            sleep_s = cfg.poll_seconds

        time.sleep(max(0.1, float(sleep_s)))

    final_msg = handle_command("log", portfolio, live_account=latest_live_account)[0] + "\n[Bot stopped]"
    send(final_msg)
    append_jsonl(events_log, {"type": "stopped", "ts": int(time.time())})


if __name__ == "__main__":
    run()
