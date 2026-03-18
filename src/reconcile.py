from .paper_engine import PortfolioState


def check_portfolio_consistency(portfolio: PortfolioState, initial_cash: float, tol: float = 1e-4) -> tuple[bool, str]:
    realized = portfolio.realized_pnl()
    lhs = portfolio.cash_available + portfolio.open_position_value
    rhs = initial_cash + realized
    diff = abs(lhs - rhs)
    ok = diff <= tol
    return ok, f"lhs={lhs:.6f} rhs={rhs:.6f} diff={diff:.8f}"
