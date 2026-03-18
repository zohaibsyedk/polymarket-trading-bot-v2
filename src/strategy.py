from dataclasses import dataclass
from .config import BotConfig
from .models import QuoteSnapshot


@dataclass
class EntryDecision:
    should_enter: bool
    side: str | None = None
    price: float | None = None
    size_usd: float | None = None
    reason: str = ""


def compute_entry_size(cash_available: float, cfg: BotConfig) -> float:
    return max(cfg.min_position_usd, cfg.position_pct_cash * cash_available)


def evaluate_entry(cfg: BotConfig, quote: QuoteSnapshot, elapsed_in_market_sec: int, cash_available: float) -> EntryDecision:
    if cash_available < cfg.min_cash_to_enter:
        return EntryDecision(False, reason="cash_below_min")

    entry_start = cfg.market_interval_seconds - cfg.final_entry_window_seconds
    if elapsed_in_market_sec < entry_start or elapsed_in_market_sec >= cfg.market_interval_seconds:
        return EntryDecision(False, reason="outside_final_90s_window")

    # New rule: in final window, only enter once any side reaches threshold.
    top = max(quote.up_price, quote.down_price)
    if top < cfg.entry_min_price_threshold:
        return EntryDecision(False, reason="waiting_for_0.77_threshold")

    if quote.up_price >= quote.down_price:
        side = "UP"
        px = quote.up_price
    else:
        side = "DOWN"
        px = quote.down_price

    size = compute_entry_size(cash_available, cfg)
    return EntryDecision(True, side=side, price=px, size_usd=size, reason="final_90s_threshold_then_higher_side")
