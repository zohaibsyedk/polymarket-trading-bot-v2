from dataclasses import dataclass
from .config import BotConfig
from .models import QuoteSnapshot, Position


@dataclass
class EntryDecision:
    should_enter: bool
    side: str | None = None
    price: float | None = None
    size_usd: float | None = None
    reason: str = ""


@dataclass
class ExitDecision:
    should_exit: bool
    price: float | None = None
    reason: str = ""


def compute_entry_size(cash_available: float, cfg: BotConfig) -> float:
    return max(cfg.min_position_usd, cfg.position_pct_cash * cash_available)


def evaluate_entry(cfg: BotConfig, quote: QuoteSnapshot, elapsed_in_market_sec: int, cash_available: float) -> EntryDecision:
    if cash_available < cfg.min_cash_to_enter:
        return EntryDecision(False, reason="cash_below_min")

    if elapsed_in_market_sec >= cfg.entry_window_seconds:
        return EntryDecision(False, reason="outside_entry_window")

    if quote.up_price <= cfg.entry_trigger_price:
        size = compute_entry_size(cash_available, cfg)
        return EntryDecision(True, side="UP", price=quote.up_price, size_usd=size, reason="up_trigger")

    if quote.down_price <= cfg.entry_trigger_price:
        size = compute_entry_size(cash_available, cfg)
        return EntryDecision(True, side="DOWN", price=quote.down_price, size_usd=size, reason="down_trigger")

    return EntryDecision(False, reason="no_trigger")


def evaluate_exit(cfg: BotConfig, position: Position, quote: QuoteSnapshot, elapsed_in_market_sec: int) -> ExitDecision:
    current_price = quote.up_price if position.side == "UP" else quote.down_price

    if elapsed_in_market_sec >= cfg.last_minute_start_second:
        return ExitDecision(True, price=current_price, reason="force_exit_last_minute")

    if current_price >= cfg.take_profit_price:
        return ExitDecision(True, price=current_price, reason="take_profit")

    if current_price <= cfg.stop_loss_price:
        return ExitDecision(True, price=current_price, reason="stop_loss")

    return ExitDecision(False)
