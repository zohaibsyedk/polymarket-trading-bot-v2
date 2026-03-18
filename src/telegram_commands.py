from .paper_engine import PortfolioState


def build_log_summary(portfolio: PortfolioState) -> str:
    return (
        "[PolyMarket Trading Bot V2 - Log]\n"
        f"[Open Positions: {len(portfolio.open_positions)}]\n"
        f"[Total Realized P&L: {portfolio.realized_pnl():.4f}]\n"
        f"[Cash Available: {portfolio.cash_available:.4f}]\n"
        f"[Position Value: {portfolio.open_position_value:.4f}]\n"
        f"[Portfolio Value: {portfolio.portfolio_value:.4f}]"
    )


def build_market_summary(active_market_slug: dict[str, str]) -> str:
    btc = active_market_slug.get("BTC")
    eth = active_market_slug.get("ETH")
    lines = ["[PolyMarket Trading Bot V2 - Markets]"]
    if btc:
        lines.append(f"BTC: https://polymarket.com/event/{btc}")
    else:
        lines.append("BTC: (not resolved)")
    if eth:
        lines.append(f"ETH: https://polymarket.com/event/{eth}")
    else:
        lines.append("ETH: (not resolved)")
    return "\n".join(lines)


def handle_command(cmd: str, portfolio: PortfolioState, active_market_slug: dict[str, str] | None = None) -> tuple[str, bool]:
    c = cmd.strip().lower()
    if c == "log":
        return build_log_summary(portfolio), False
    if c == "market":
        return build_market_summary(active_market_slug or {}), False
    if c == "stop":
        return build_log_summary(portfolio), True
    return "Unknown command. Use Log, Market, or Stop.", False
