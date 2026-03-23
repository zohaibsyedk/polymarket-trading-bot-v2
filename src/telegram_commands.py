from .paper_engine import PortfolioState


def build_log_summary(portfolio: PortfolioState, live_account: dict | None = None) -> str:
    live = live_account or {}
    live_cash = live.get("cash_available")
    live_portfolio = live.get("portfolio_value")

    if live_cash is not None or live_portfolio is not None:
        cash_f = float(live_cash) if live_cash is not None else 0.0
        port_f = float(live_portfolio) if live_portfolio is not None else cash_f
        pos_f = port_f - cash_f
        note = "" if live_portfolio is not None else "\n[Note: Portfolio value unavailable from API; using cash-only estimate]"
        return (
            "[PolyMarket Trading Bot V2 - Log]\n"
            f"[Open Positions (Bot): {len(portfolio.open_positions)}]\n"
            f"[Total Realized P&L (Bot): {portfolio.realized_pnl():.4f}]\n"
            f"[Cash Available: {cash_f:.4f}]\n"
            f"[Position Value: {pos_f:.4f}]\n"
            f"[Portfolio Value: {port_f:.4f}]"
            f"{note}"
        )

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
    live_account: dict | None = None,
    entries_paused: bool = False,
) -> tuple[str, bool, str | None]:
    c = cmd.strip().lower()
    # Accept telegram-style commands like /poly or /poly@BotName
    if c.startswith('/'):
        c = c[1:]
    if '@' in c:
        c = c.split('@', 1)[0]
    if ' ' in c:
        c = c.split(' ', 1)[0]
    if c == "log":
        return build_log_summary(portfolio, live_account=live_account), False, None
    if c == "market":
        return build_market_summary(active_market_slug or {}), False, None
    if c == "snapshot":
        return build_snapshot_summary(active_market_data or {}), False, None
    if c == "poly":
        acct = live_account or {}
        cash = acct.get("cash_available")
        portfolio_total = acct.get("portfolio_value")
        if cash is None and portfolio_total is None:
            return "[Poly] Account totals unavailable yet. Wait for reconcile tick.", False, None
        cash_f = float(cash) if cash is not None else 0.0
        if portfolio_total is None:
            port_f = cash_f
            note = "\n[Note: Portfolio value unavailable from API; using cash-only estimate]"
        else:
            port_f = float(portfolio_total)
            note = ""
        pos_f = port_f - cash_f
        return (
            "[PolyMarket Account]\n"
            f"[Available Cash: ${cash_f:.4f}]\n"
            f"[Portfolio Value: ${port_f:.4f}]\n"
            f"[Position Value: ${pos_f:.4f}]"
            f"{note}"
        ), False, None
    if c == "pause":
        if entries_paused:
            return "[Trading] Entries already paused.", False, None
        return "[Trading] Entries paused.", False, "pause"
    if c == "resume":
        if not entries_paused:
            return "[Trading] Entries already active.", False, None
        return "[Trading] Entries resumed.", False, "resume"
    if c == "stop":
        return build_log_summary(portfolio, live_account=live_account), True, None
    return "Unknown command. Use Log, Market, Snapshot, Poly, Pause, Resume, or Stop.", False, None
