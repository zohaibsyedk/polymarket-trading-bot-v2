from .paper_engine import PortfolioState
from .models import Position


def _fmt_money(x: float) -> str:
    return f"{x:.4f}"


def format_entry_message(p: Position, portfolio: PortfolioState) -> str:
    return "\n".join([
        f"[ID: {p.position_id}]",
        f"[{p.symbol} - {p.market_ts}]",
        f"[Purchase: {p.side} @ ${_fmt_money(p.entry_price)}]",
        f"[Position: {p.contracts:.6f} Contracts for ${_fmt_money(p.entry_cost)}]",
        f"[Cash Available: ${_fmt_money(portfolio.cash_available)}]",
        f"[Position Value: ${_fmt_money(portfolio.open_position_value)}]",
        f"[Portfolio Value: ${_fmt_money(portfolio.portfolio_value)}]",
    ])


def format_exit_message(p: Position, portfolio: PortfolioState) -> str:
    assert p.exit_price is not None
    per_contract = p.exit_price - p.entry_price
    sign = "+" if per_contract >= 0 else ""
    return "\n".join([
        f"[ID: {p.position_id}]",
        f"[{p.symbol} - {p.market_ts}]",
        f"[Purchase: {p.side} @ ${_fmt_money(p.entry_price)}]",
        f"[Sold: {p.side} @ ${_fmt_money(p.exit_price)}]",
        f"[Net Profit Per Contract: {sign}{per_contract:.4f}]",
        f"[Cash Available: ${_fmt_money(portfolio.cash_available)}]",
        f"[Position Value: ${_fmt_money(portfolio.open_position_value)}]",
        f"[Portfolio Value: ${_fmt_money(portfolio.portfolio_value)}]",
    ])
