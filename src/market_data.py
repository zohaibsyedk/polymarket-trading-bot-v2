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


def _midpoint_for_token(token_id: str) -> Optional[float]:
    try:
        req = urllib.request.Request(f"{CLOB_BASE}/midpoint?token_id={token_id}", headers=UA)
        with urllib.request.urlopen(req, timeout=8) as r:
            d = json.loads(r.read().decode())
        mid = d.get("mid")
        if mid is None:
            return None
        v = float(mid)
        if 0.0 < v < 1.0:
            return v
        return None
    except Exception:
        return None


def _last_trade_price_for_token(token_id: str) -> Optional[float]:
    try:
        req = urllib.request.Request(f"{CLOB_BASE}/last-trade-price?token_id={token_id}", headers=UA)
        with urllib.request.urlopen(req, timeout=8) as r:
            d = json.loads(r.read().decode())
        px = d.get("price")
        if px is None:
            return None
        v = float(px)
        if 0.0 < v < 1.0:
            return v
        return None
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

    token_ids = _parse_token_ids(m.get("clobTokenIds"))
    if len(token_ids) < 2:
        return None

    ask_up = _best_ask_for_token(token_ids[0])
    ask_down = _best_ask_for_token(token_ids[1])
    bid_up = _best_bid_for_token(token_ids[0])
    bid_down = _best_bid_for_token(token_ids[1])
    mid_up = _midpoint_for_token(token_ids[0])
    mid_down = _midpoint_for_token(token_ids[1])
    last_up = _last_trade_price_for_token(token_ids[0])
    last_down = _last_trade_price_for_token(token_ids[1])

    def valid_price(x):
        return x is not None and 0.0 < float(x) < 1.0

    # CLOB Get Market Price endpoint first (midpoint), then last trade, then orderbook fallback
    up_mark = mid_up if valid_price(mid_up) else (last_up if valid_price(last_up) else None)
    down_mark = mid_down if valid_price(mid_down) else (last_down if valid_price(last_down) else None)

    if up_mark is None:
        a = float(ask_up) if valid_price(ask_up) else None
        b = float(bid_up) if valid_price(bid_up) else None
        up_mark = (a + b) / 2.0 if (a is not None and b is not None) else (a if a is not None else b)
    if down_mark is None:
        a = float(ask_down) if valid_price(ask_down) else None
        b = float(bid_down) if valid_price(bid_down) else None
        down_mark = (a + b) / 2.0 if (a is not None and b is not None) else (a if a is not None else b)

    if up_mark is None or down_mark is None:
        return None

    # Entry trigger price: buyable ask if available; else use mark from Get Market Price path
    entry_up = float(ask_up) if valid_price(ask_up) else float(up_mark)
    entry_down = float(ask_down) if valid_price(ask_down) else float(down_mark)

    return ResolvedMarket(
        symbol=symbol,
        market_ts=market_ts,
        slug=slug,
        accepting_orders=bool(m.get("acceptingOrders")),
        closed=bool(m.get("closed")),
        up_price=float(up_mark),
        down_price=float(down_mark),
        entry_up_price=float(entry_up),
        entry_down_price=float(entry_down),
        bid_up_price=float(bid_up) if valid_price(bid_up) else None,
        bid_down_price=float(bid_down) if valid_price(bid_down) else None,
        ask_up_price=float(ask_up) if valid_price(ask_up) else None,
        ask_down_price=float(ask_down) if valid_price(ask_down) else None,
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
