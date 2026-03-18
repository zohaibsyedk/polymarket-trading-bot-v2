from dataclasses import dataclass, field
from typing import Dict, List
from .models import Position


@dataclass
class PortfolioState:
    cash_available: float
    open_positions: Dict[int, Position] = field(default_factory=dict)
    closed_positions: List[Position] = field(default_factory=list)
    next_position_id: int = 1

    @property
    def open_position_value(self) -> float:
        return round(sum(p.entry_cost for p in self.open_positions.values()), 6)

    @property
    def portfolio_value(self) -> float:
        return round(self.cash_available + self.open_position_value, 6)

    def create_position(self, symbol: str, market_ts: int, side: str, price: float, now_ts: int, size_usd: float) -> Position:
        contracts = round(size_usd / price, 6)
        cost = round(contracts * price, 6)
        if cost > self.cash_available:
            raise ValueError("insufficient cash")

        p = Position(
            position_id=self.next_position_id,
            symbol=symbol,
            market_ts=market_ts,
            side=side,
            contracts=contracts,
            entry_price=price,
            entry_cost=cost,
            opened_at=now_ts,
        )
        self.next_position_id += 1
        self.cash_available = round(self.cash_available - cost, 6)
        self.open_positions[p.position_id] = p
        return p

    def close_position(self, position_id: int, exit_price: float, now_ts: int) -> Position:
        p = self.open_positions.pop(position_id)
        proceeds = round(p.contracts * exit_price, 6)
        self.cash_available = round(self.cash_available + proceeds, 6)
        p.exit_price = exit_price
        p.closed_at = now_ts
        self.closed_positions.append(p)
        return p

    def realized_pnl(self) -> float:
        total = 0.0
        for p in self.closed_positions:
            if p.exit_price is None:
                continue
            total += (p.exit_price - p.entry_price) * p.contracts
        return round(total, 6)
