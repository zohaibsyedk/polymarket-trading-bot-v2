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
    up_token_id: str
    down_token_id: str


def _fetch_slug(slug: str) -> Optional[dict]:
    try:
        req = urllib.request.Request(GAMMA_BASE + slug, headers=UA)
        with urllib.request.urlopen(req, timeout=3) as r:
            d = json.loads(r.read().decode())
        return d[0] if d else None
    except Exception:
        return None


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
        with urllib.request.urlopen(req, timeout=2) as r:
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
        with urllib.request.urlopen(req, timeout=2) as r:
            d = json.loads(r.read().decode())
        bids = d.get("bids") or []
        if not bids:
            return None
        return float(bids[0].get("price"))
    except Exception:
        return None


def _market_price_for_token(token_id: str, side: str) -> Optional[float]:
    """Use CLOB Get Market Price endpoint (/price). side in {BUY, SELL}."""
    try:
        req = urllib.request.Request(
            f"{CLOB_BASE}/price?token_id={token_id}&side={side}",
            headers=UA,
        )
        with urllib.request.urlopen(req, timeout=2) as r:
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

    # CLOB Get Market Price endpoint prices (token IDs sourced from Gamma)
    # side=SELL -> best ask (buyable)
    # side=BUY  -> best bid (sellable)
    sell_up = _market_price_for_token(token_ids[0], "SELL")
    sell_down = _market_price_for_token(token_ids[1], "SELL")
    buy_up = _market_price_for_token(token_ids[0], "BUY")
    buy_down = _market_price_for_token(token_ids[1], "BUY")

    def valid_price(x):
        return x is not None and 0.0 < float(x) < 1.0

    # Entry trigger should use buyable price (SELL side quote).
    entry_up = float(sell_up) if valid_price(sell_up) else (float(buy_up) if valid_price(buy_up) else None)
    entry_down = float(sell_down) if valid_price(sell_down) else (float(buy_down) if valid_price(buy_down) else None)

    # Runtime mark/exit reference uses sellable price (BUY side quote).
    up_mark = float(buy_up) if valid_price(buy_up) else (float(sell_up) if valid_price(sell_up) else None)
    down_mark = float(buy_down) if valid_price(buy_down) else (float(sell_down) if valid_price(sell_down) else None)

    if up_mark is None or down_mark is None or entry_up is None or entry_down is None:
        return None

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
        bid_up_price=float(buy_up) if valid_price(buy_up) else None,
        bid_down_price=float(buy_down) if valid_price(buy_down) else None,
        ask_up_price=float(sell_up) if valid_price(sell_up) else None,
        ask_down_price=float(sell_down) if valid_price(sell_down) else None,
        up_token_id=str(token_ids[0]),
        down_token_id=str(token_ids[1]),
    )


def resolve_current_market(symbol: str, bucket_ts: int, now_ts: int) -> Optional[ResolvedMarket]:
    """
    Resolve the *active* 5-minute market for the current time.

    We prefer non-future buckets (<= now_ts). This avoids selecting the next
    interval too early, which can suppress valid entries in the current market.
    """
    candidates = [bucket_ts, bucket_ts - 300]
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


def resolve_settlement_payout(symbol: str, market_ts: int, side: str) -> Optional[float]:
    """
    Returns payout per contract at/after market close:
    - 1.0 if chosen side won
    - 0.0 if chosen side lost
    - None if market not yet resolved
    """
    slug = market_slug(symbol, market_ts)
    m = _fetch_slug(slug)
    if not m or not bool(m.get("closed")):
        return None

    up, down = _parse_prices(m.get("outcomePrices"))
    if up is None or down is None:
        return None

    side_u = side.upper()
    if side_u == "UP":
        if up == 1.0:
            return 1.0
        if up == 0.0:
            return 0.0
    elif side_u == "DOWN":
        if down == 1.0:
            return 1.0
        if down == 0.0:
            return 0.0

    # unresolved/ambiguous settlement state
    return None
