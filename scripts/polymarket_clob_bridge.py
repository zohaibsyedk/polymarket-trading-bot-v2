#!/usr/bin/env python3
"""
PolyMarket CLOB bridge for PMB2 live mode.

Reads request JSON from stdin and writes response JSON to stdout.

Input (buy):
  {"action":"buy","symbol":"BTC","market_ts":123,"side":"UP","limit_price":0.81,"size_usd":50}
Input (sell):
  {"action":"sell","symbol":"BTC","market_ts":123,"side":"UP","contracts":61.7,"limit_price":0.52}

Output success (buy):
  {"ok":true,"fill_price":0.81,"contracts":61.7,"cost":49.98,"order_id":"..."}
Output success (sell):
  {"ok":true,"fill_price":0.52,"proceeds":32.08,"order_id":"..."}
Output error:
  {"ok":false,"error":"..."}

ENV required:
  POLYMARKET_PRIVATE_KEY=0x...
  POLYMARKET_FUNDER=0x...         # proxy/funder wallet address

ENV optional:
  POLYMARKET_CLOB_HOST=https://clob.polymarket.com
  POLYMARKET_GAMMA_HOST=https://gamma-api.polymarket.com
  POLYMARKET_CHAIN_ID=137
  POLYMARKET_SIGNATURE_TYPE=2
  POLYMARKET_USE_DERIVED_CREDS=1

Dependencies:
  pip install py-clob-client
"""

from __future__ import annotations

import json
import os
import sys
import urllib.parse
import urllib.request
from typing import Any


def _fail(msg: str) -> dict[str, Any]:
    return {"ok": False, "error": msg}


def _read_stdin_json() -> dict[str, Any]:
    raw = sys.stdin.read().strip()
    if not raw:
        raise ValueError("empty_stdin")
    d = json.loads(raw)
    if not isinstance(d, dict):
        raise ValueError("payload_must_be_object")
    return d


def _slug(symbol: str, market_ts: int) -> str:
    s = symbol.strip().lower()
    if s not in {"btc", "eth"}:
        raise ValueError("symbol must be BTC or ETH")
    return f"{s}-updown-5m-{int(market_ts)}"


def _fetch_market(slug: str) -> dict[str, Any]:
    gamma = os.getenv("POLYMARKET_GAMMA_HOST", "https://gamma-api.polymarket.com").rstrip("/")
    url = f"{gamma}/markets?slug={urllib.parse.quote(slug)}"
    req = urllib.request.Request(url, headers={"User-Agent": "PMB2-Bridge", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=12) as r:
        data = json.loads(r.read().decode("utf-8"))
    if not data:
        raise RuntimeError(f"market_not_found:{slug}")
    return data[0]


def _token_id_for_side(market: dict[str, Any], side: str) -> str:
    token_ids = market.get("clobTokenIds")
    if isinstance(token_ids, str):
        token_ids = json.loads(token_ids)
    if not isinstance(token_ids, list) or len(token_ids) < 2:
        raise RuntimeError("invalid_clobTokenIds")
    s = side.strip().upper()
    if s == "UP":
        return str(token_ids[0])
    if s == "DOWN":
        return str(token_ids[1])
    raise RuntimeError("side must be UP or DOWN")


def _init_clob_client():
    try:
        from py_clob_client.client import ClobClient
    except Exception as e:
        raise RuntimeError("py-clob-client not installed; run: pip install py-clob-client") from e

    host = os.getenv("POLYMARKET_CLOB_HOST", "https://clob.polymarket.com").rstrip("/")
    private_key = os.getenv("POLYMARKET_PRIVATE_KEY", "").strip()
    funder = os.getenv("POLYMARKET_FUNDER", "").strip()
    chain_id = int(os.getenv("POLYMARKET_CHAIN_ID", "137"))
    sig_type = int(os.getenv("POLYMARKET_SIGNATURE_TYPE", "2"))

    if not private_key:
        raise RuntimeError("POLYMARKET_PRIVATE_KEY missing")
    if not funder:
        raise RuntimeError("POLYMARKET_FUNDER missing")

    # signature_type=2 for proxy/funder flow (most common Polymarket setup)
    client = ClobClient(host, key=private_key, chain_id=chain_id, signature_type=sig_type, funder=funder)

    use_derived = os.getenv("POLYMARKET_USE_DERIVED_CREDS", "1") == "1"
    if use_derived:
        creds = client.create_or_derive_api_creds()
        client.set_api_creds(creds)

    return client


def _place_limit_buy(client, token_id: str, limit_price: float, size_usd: float) -> dict[str, Any]:
    try:
        from py_clob_client.clob_types import OrderArgs, OrderType
        from py_clob_client.order_builder.constants import BUY
    except Exception as e:
        raise RuntimeError("py-clob-client import mismatch; check installed version") from e

    if limit_price <= 0 or limit_price >= 1:
        raise RuntimeError("limit_price must be between 0 and 1")
    if size_usd <= 0:
        raise RuntimeError("size_usd must be > 0")

    # Approx contracts at limit price. Exchange may fill partially.
    contracts = round(size_usd / limit_price, 6)

    order = OrderArgs(
        price=float(limit_price),
        size=float(contracts),
        side=BUY,
        token_id=str(token_id),
    )
    signed = client.create_order(order)
    resp = client.post_order(signed, OrderType.GTC)

    # Post-order response shape can vary by client version.
    order_id = (resp or {}).get("orderID") or (resp or {}).get("id") or (resp or {}).get("order_id")

    return {
        "ok": True,
        "fill_price": float(limit_price),
        "contracts": float(contracts),
        "cost": round(float(contracts) * float(limit_price), 6),
        "order_id": order_id,
        "raw": resp,
    }


def _place_limit_sell(client, token_id: str, limit_price: float, contracts: float) -> dict[str, Any]:
    try:
        from py_clob_client.clob_types import OrderArgs, OrderType
        from py_clob_client.order_builder.constants import SELL
    except Exception as e:
        raise RuntimeError("py-clob-client import mismatch; check installed version") from e

    if limit_price <= 0 or limit_price >= 1:
        raise RuntimeError("limit_price must be between 0 and 1")
    if contracts <= 0:
        raise RuntimeError("contracts must be > 0")

    order = OrderArgs(
        price=float(limit_price),
        size=float(contracts),
        side=SELL,
        token_id=str(token_id),
    )
    signed = client.create_order(order)
    resp = client.post_order(signed, OrderType.GTC)

    order_id = (resp or {}).get("orderID") or (resp or {}).get("id") or (resp or {}).get("order_id")

    return {
        "ok": True,
        "fill_price": float(limit_price),
        "proceeds": round(float(contracts) * float(limit_price), 6),
        "order_id": order_id,
        "raw": resp,
    }


def main() -> int:
    try:
        payload = _read_stdin_json()
        action = str(payload.get("action", "")).strip().lower()
        symbol = str(payload.get("symbol", "")).strip().upper()
        market_ts = int(payload.get("market_ts"))
        side = str(payload.get("side", "")).strip().upper()

        slug = _slug(symbol, market_ts)
        market = _fetch_market(slug)
        token_id = _token_id_for_side(market, side)
        client = _init_clob_client()

        if action == "buy":
            limit_price = float(payload.get("limit_price"))
            size_usd = float(payload.get("size_usd"))
            out = _place_limit_buy(client, token_id, limit_price, size_usd)
        elif action == "sell":
            limit_price = float(payload.get("limit_price"))
            contracts = float(payload.get("contracts"))
            out = _place_limit_sell(client, token_id, limit_price, contracts)
        else:
            out = _fail("action must be buy or sell")

    except Exception as e:
        out = _fail(str(e))

    sys.stdout.write(json.dumps(out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
