import json
import urllib.request
from dataclasses import dataclass
from typing import Optional

UA = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
GAMMA_BASE = "https://gamma-api.polymarket.com/markets?slug="
CLOB_BASE = "https://clob.polymarket.com"


@dataclass
class ResolvedMarket:
    symbol: str
    market_ts: int
    slug: str
    accepting_orders: bool
    closed: bool
    up_price: float           # display/mark price (Gamma)
    down_price: float         # display/mark price (Gamma)
    entry_up_price: float     # composite trigger price
    entry_down_price: float   # composite trigger price
    bid_up_price: Optional[float]
    bid_down_price: Optional[float]
    ask_up_price: Optional[float]
    ask_down_price: Optional[float]


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


def _best_ask_for_token(token_id: str) -> Optional[float]:
    try:
        req = urllib.request.Request(f"{CLOB_BASE}/book?token_id={token_id}", headers=UA)
        with urllib.request.urlopen(req, timeout=8) as r:
            d = json.loads(r.read().decode())
        asks = d.get("asks") or []
        if not asks:
            return None
        return float(asks[0].get("price"))
    except Exception:
        return None


def _best_bid_for_token(token_id: str) -> Optional[float]:
    try:
        req = urllib.request.Request(f"{CLOB_BASE}/book?token_id={token_id}", headers=UA)
        with urllib.request.urlopen(req, timeout=8) as r:
            d = json.loads(r.read().decode())
        bids = d.get("bids") or []
        if not bids:
            return None
        return float(bids[0].get("price"))
    except Exception:
        return None


def _parse_token_ids(v) -> list[str]:
    if isinstance(v, str):
        try:
            v = json.loads(v)
        except Exception:
            return []
    if not isinstance(v, list):
        return []
    return [str(x) for x in v]


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

    token_ids = _parse_token_ids(m.get("clobTokenIds"))
    ask_up = _best_ask_for_token(token_ids[0]) if len(token_ids) > 0 else None
    ask_down = _best_ask_for_token(token_ids[1]) if len(token_ids) > 1 else None
    bid_up = _best_bid_for_token(token_ids[0]) if len(token_ids) > 0 else None
    bid_down = _best_bid_for_token(token_ids[1]) if len(token_ids) > 1 else None

    def valid_price(x):
        return x is not None and 0.0 < float(x) < 1.0

    up_candidates = [float(up)]
    down_candidates = [float(down)]
    if valid_price(ask_up):
        up_candidates.append(float(ask_up))
    if valid_price(bid_up):
        up_candidates.append(float(bid_up))
    if valid_price(ask_down):
        down_candidates.append(float(ask_down))
    if valid_price(bid_down):
        down_candidates.append(float(bid_down))

    # composite trigger price: most favorable observed tradable/display value
    entry_up = min(up_candidates)
    entry_down = min(down_candidates)

    return ResolvedMarket(
        symbol=symbol,
        market_ts=market_ts,
        slug=slug,
        accepting_orders=bool(m.get("acceptingOrders")),
        closed=bool(m.get("closed")),
        up_price=float(up),
        down_price=float(down),
        entry_up_price=entry_up,
        entry_down_price=entry_down,
        bid_up_price=bid_up,
        bid_down_price=bid_down,
        ask_up_price=ask_up,
        ask_down_price=ask_down,
    )


def resolve_current_market(symbol: str, bucket_ts: int, now_ts: int) -> Optional[ResolvedMarket]:
    """
    Resolve the *active* 5-minute market for the current time.

    We prefer non-future buckets (<= now_ts). This avoids selecting the next
    interval too early, which can suppress valid entries in the current market.
    """
    candidates = [bucket_ts, bucket_ts - 300, bucket_ts + 300]
    resolved: list[ResolvedMarket] = []
    for ts in candidates:
        m = fetch_market(symbol, ts)
        if not m:
            continue
        if m.closed:
            continue
        resolved.append(m)

    if not resolved:
        return None

    non_future = [m for m in resolved if m.market_ts <= now_ts]
    if non_future:
        return max(non_future, key=lambda m: m.market_ts)

    return min(resolved, key=lambda m: m.market_ts)
