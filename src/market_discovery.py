import time
from dataclasses import dataclass


@dataclass
class ActiveMarketWindow:
    ts_bucket: int
    bucket_start: int
    bucket_end: int


def current_5m_window(now: int | None = None) -> ActiveMarketWindow:
    now = now or int(time.time())
    bucket_start = now - (now % 300)
    return ActiveMarketWindow(
        ts_bucket=bucket_start,
        bucket_start=bucket_start,
        bucket_end=bucket_start + 300,
    )


def market_slug(symbol: str, ts_bucket: int) -> str:
    symbol = symbol.lower()
    if symbol not in {"btc", "eth"}:
        raise ValueError("symbol must be btc or eth")
    return f"{symbol}-updown-5m-{ts_bucket}"
