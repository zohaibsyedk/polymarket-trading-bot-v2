import json
import urllib.request
from dataclasses import dataclass
from typing import Optional

UA = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
GAMMA_BASE = "https://gamma-api.polymarket.com/markets?slug="


@dataclass
class ResolvedMarket:
    symbol: str
    market_ts: int
    slug: str
    accepting_orders: bool
    closed: bool
    up_price: float
    down_price: float


def _fetch_slug(slug: str) -> Optional[dict]:
    req = urllib.request.Request(GAMMA_BASE + slug, headers=UA)
    with urllib.request.urlopen(req, timeout=12) as r:
        d = json.loads(r.read().decode())
    return d[0] if d else None


def _parse_prices(v) -> tuple[Optional[float], Optional[float]]:
    if isinstance(v, str):
        try:
            v = json.loads(v)
        except Exception:
            return None, None
    if not isinstance(v, list) or len(v) < 2:
        return None, None
    try:
        return float(v[0]), float(v[1])
    except Exception:
        return None, None


def market_slug(symbol: str, market_ts: int) -> str:
    s = symbol.lower()
    if s not in {"btc", "eth"}:
        raise ValueError("symbol must be BTC/ETH")
    return f"{s}-updown-5m-{market_ts}"


def fetch_market(symbol: str, market_ts: int) -> Optional[ResolvedMarket]:
    slug = market_slug(symbol, market_ts)
    m = _fetch_slug(slug)
    if not m:
        return None

    up, down = _parse_prices(m.get("outcomePrices"))
    if up is None or down is None:
        return None

    return ResolvedMarket(
        symbol=symbol,
        market_ts=market_ts,
        slug=slug,
        accepting_orders=bool(m.get("acceptingOrders")),
        closed=bool(m.get("closed")),
        up_price=float(up),
        down_price=float(down),
    )


def resolve_current_market(symbol: str, bucket_ts: int) -> Optional[ResolvedMarket]:
    """
    Resolve the most current tradable market around this 5m bucket.
    Preference: current bucket, then next bucket, then previous.
    """
    candidates = [bucket_ts, bucket_ts + 300, bucket_ts - 300]
    best: Optional[ResolvedMarket] = None
    for ts in candidates:
        m = fetch_market(symbol, ts)
        if not m:
            continue
        if m.closed:
            continue
        if best is None:
            best = m
            continue
        if m.market_ts > best.market_ts:
            best = m
    return best
