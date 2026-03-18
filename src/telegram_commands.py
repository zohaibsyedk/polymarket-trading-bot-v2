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


def handle_command(cmd: str, portfolio: PortfolioState) -> tuple[str, bool]:
    c = cmd.strip().lower()
    if c == "log":
        return build_log_summary(portfolio), False
    if c == "stop":
        return build_log_summary(portfolio), True
    return "Unknown command. Use Log or Stop.", False
