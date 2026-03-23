from dataclasses import dataclass, asdict
from typing import Optional


@dataclass
class Position:
    position_id: int
    symbol: str  # BTC or ETH
    market_ts: int
    side: str  # UP or DOWN
    contracts: float
    entry_price: float
    entry_cost: float
    opened_at: int
    entry_order_id: Optional[str] = None
    exit_price: Optional[float] = None
    closed_at: Optional[int] = None
    exit_order_id: Optional[str] = None

    @property
    def is_open(self) -> bool:
        return self.exit_price is None

    def to_dict(self):
        return asdict(self)


@dataclass
class QuoteSnapshot:
    symbol: str
    market_ts: int
    up_price: float
    down_price: float
    ts: int
