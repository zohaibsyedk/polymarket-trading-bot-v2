import random
from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.config import BotConfig
from src.models import QuoteSnapshot
from src.paper_engine import PortfolioState
from src.strategy import evaluate_entry, evaluate_exit
from src.reconcile import check_portfolio_consistency


def run_sim(intervals: int = 60, seed: int = 7):
    random.seed(seed)
    cfg = BotConfig()
    portfolio = PortfolioState(cash_available=cfg.starting_cash)
    initial_cash = cfg.starting_cash

    trades = []

    base_ts = 1773813600
    for i in range(intervals):
        market_ts = base_ts + (i * cfg.market_interval_seconds)

        # 5-minute sequence sampled every 10s
        for elapsed in range(0, cfg.market_interval_seconds, 10):
            now_ts = market_ts + elapsed
            for symbol in ("BTC", "ETH"):
                # synthetic prices with occasional entry trigger
                up = max(0.01, min(0.99, round(0.12 + random.random() * 0.55, 4)))
                down = max(0.01, min(0.99, round(1.0 - up, 4)))
                q = QuoteSnapshot(symbol=symbol, market_ts=market_ts, up_price=up, down_price=down, ts=now_ts)

                symbol_open = [p for p in portfolio.open_positions.values() if p.symbol == symbol and p.market_ts == market_ts]
                if not symbol_open:
                    entry = evaluate_entry(cfg, q, elapsed, portfolio.cash_available)
                    if entry.should_enter and entry.side and entry.price and entry.size_usd:
                        p = portfolio.create_position(symbol, market_ts, entry.side, entry.price, now_ts, entry.size_usd)
                        trades.append({"type": "entry", "id": p.position_id, "symbol": symbol, "market_ts": market_ts})

                for p in list(portfolio.open_positions.values()):
                    if p.symbol != symbol or p.market_ts != market_ts:
                        continue
                    x = evaluate_exit(cfg, p, q, elapsed)
                    if x.should_exit and x.price is not None:
                        c = portfolio.close_position(p.position_id, x.price, now_ts)
                        trades.append({"type": "exit", "id": c.position_id, "reason": x.reason})

        ok, detail = check_portfolio_consistency(portfolio, initial_cash)
        if not ok:
            return {
                "ok": False,
                "error": "reconciliation_failed",
                "detail": detail,
                "interval_index": i,
                "open_positions": len(portfolio.open_positions),
            }

    ok, detail = check_portfolio_consistency(portfolio, initial_cash)
    return {
        "ok": ok,
        "detail": detail,
        "intervals": intervals,
        "trades": len(trades),
        "entries": len([t for t in trades if t["type"] == "entry"]),
        "exits": len([t for t in trades if t["type"] == "exit"]),
        "open_positions": len(portfolio.open_positions),
        "realized_pnl": portfolio.realized_pnl(),
        "cash_available": portfolio.cash_available,
        "portfolio_value": portfolio.portfolio_value,
    }


if __name__ == "__main__":
    out = run_sim(intervals=60)
    print(json.dumps(out, indent=2))
