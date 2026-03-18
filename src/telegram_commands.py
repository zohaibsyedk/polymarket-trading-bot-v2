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


def build_snapshot_summary(active_market_data: dict[str, dict]) -> str:
    lines = ["[PolyMarket Trading Bot V2 - Snapshot]"]
    for sym in ("BTC", "ETH"):
        d = active_market_data.get(sym) or {}
        slug = d.get("slug")
        up = d.get("up")
        down = d.get("down")
        if slug is None or up is None or down is None:
            lines.append(f"[{sym}] (not resolved)")
            continue
        lines.append(f"[{sym} - {slug.rsplit('-', 1)[-1]}]")
        lines.append(f"[UP: ${float(up):.4f}]")
        lines.append(f"[DOWN: ${float(down):.4f}]")
    return "\n".join(lines)


def handle_command(
    cmd: str,
    portfolio: PortfolioState,
    active_market_slug: dict[str, str] | None = None,
    active_market_data: dict[str, dict] | None = None,
) -> tuple[str, bool]:
    c = cmd.strip().lower()
    if c == "log":
        return build_log_summary(portfolio), False
    if c == "market":
        return build_market_summary(active_market_slug or {}), False
    if c == "snapshot":
        return build_snapshot_summary(active_market_data or {}), False
    if c == "stop":
        return build_log_summary(portfolio), True
    return "Unknown command. Use Log, Market, Snapshot, or Stop.", False
