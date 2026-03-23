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
        return self.create_position_from_fill(
            symbol=symbol,
            market_ts=market_ts,
            side=side,
            price=price,
            contracts=contracts,
            cost=cost,
            now_ts=now_ts,
        )

    def create_position_from_fill(
        self,
        symbol: str,
        market_ts: int,
        side: str,
        price: float,
        contracts: float,
        cost: float,
        now_ts: int,
        entry_order_id: str | None = None,
        token_id: str | None = None,
    ) -> Position:
        if cost > self.cash_available:
            raise ValueError("insufficient cash")

        p = Position(
            position_id=self.next_position_id,
            symbol=symbol,
            market_ts=market_ts,
            side=side,
            contracts=round(contracts, 6),
            entry_price=round(price, 6),
            entry_cost=round(cost, 6),
            opened_at=now_ts,
            entry_order_id=entry_order_id,
            token_id=token_id,
        )
        self.next_position_id += 1
        self.cash_available = round(self.cash_available - p.entry_cost, 6)
        self.open_positions[p.position_id] = p
        return p

    def close_position(self, position_id: int, exit_price: float, now_ts: int) -> Position:
        proceeds = round(self.open_positions[position_id].contracts * exit_price, 6)
        return self.close_position_from_fill(position_id, exit_price, proceeds, now_ts)

    def close_position_from_fill(
        self,
        position_id: int,
        exit_price: float,
        proceeds: float,
        now_ts: int,
        exit_order_id: str | None = None,
    ) -> Position:
        p = self.open_positions.pop(position_id)
        self.cash_available = round(self.cash_available + round(proceeds, 6), 6)
        p.exit_price = round(exit_price, 6)
        p.closed_at = now_ts
        p.exit_order_id = exit_order_id
        self.closed_positions.append(p)
        return p

    def realized_pnl(self) -> float:
        total = 0.0
        for p in self.closed_positions:
            if p.exit_price is None:
                continue
            total += (p.exit_price - p.entry_price) * p.contracts
        return round(total, 6)
