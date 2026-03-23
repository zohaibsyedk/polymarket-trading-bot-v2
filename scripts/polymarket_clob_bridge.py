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
import time
from pathlib import Path
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


def _default_creds_cache_path() -> Path:
    p = os.getenv("POLYMARKET_API_CREDS_CACHE", "").strip()
    if p:
        return Path(p)
    return Path(__file__).resolve().parents[1] / "state" / "bridge_api_creds.json"


def _load_cached_creds() -> dict[str, Any] | None:
    path = _default_creds_cache_path()
    try:
        if not path.exists():
            return None
        data = json.loads(path.read_text())
        # Support both legacy and canonical field names.
        if all(k in data for k in ("api_key", "api_secret", "api_passphrase")):
            return data
        if all(k in data for k in ("key", "secret", "passphrase")):
            return {
                "api_key": data["key"],
                "api_secret": data["secret"],
                "api_passphrase": data["passphrase"],
            }
    except Exception:
        return None
    return None


def _save_cached_creds(creds: Any) -> None:
    path = _default_creds_cache_path()
    try:
        get = creds.get if isinstance(creds, dict) else (lambda _k: None)
        data = {
            "api_key": getattr(creds, "api_key", None) or getattr(creds, "key", None) or get("api_key") or get("key"),
            "api_secret": getattr(creds, "api_secret", None) or getattr(creds, "secret", None) or get("api_secret") or get("secret"),
            "api_passphrase": getattr(creds, "api_passphrase", None) or getattr(creds, "passphrase", None) or get("api_passphrase") or get("passphrase"),
        }
        if not all(data.values()):
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data))
        try:
            os.chmod(path, 0o600)
        except Exception:
            pass
    except Exception:
        pass


def _to_api_creds_obj(creds: Any):
    try:
        from py_clob_client.clob_types import ApiCreds
    except Exception as e:
        raise RuntimeError("py-clob-client missing ApiCreds type") from e

    if isinstance(creds, ApiCreds):
        return creds

    if isinstance(creds, dict):
        return ApiCreds(
            api_key=creds.get("api_key") or creds.get("key") or "",
            api_secret=creds.get("api_secret") or creds.get("secret") or "",
            api_passphrase=creds.get("api_passphrase") or creds.get("passphrase") or "",
        )

    # fallback for objects that already have expected attrs
    return ApiCreds(
        api_key=getattr(creds, "api_key", ""),
        api_secret=getattr(creds, "api_secret", ""),
        api_passphrase=getattr(creds, "api_passphrase", ""),
    )


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
        cached = _load_cached_creds()
        if cached:
            try:
                client.set_api_creds(_to_api_creds_obj(cached))
                return client
            except Exception:
                pass

        creds = client.create_or_derive_api_creds()
        creds_obj = _to_api_creds_obj(creds)
        client.set_api_creds(creds_obj)
        _save_cached_creds(creds_obj)

    return client


def _to_f(v: Any) -> float | None:
    try:
        if v is None:
            return None
        return float(v)
    except Exception:
        return None


def _extract_order_id(resp: dict[str, Any]) -> str | None:
    return (
        (resp or {}).get("orderID")
        or (resp or {}).get("id")
        or (resp or {}).get("order_id")
        or (resp or {}).get("orderId")
    )


def _extract_order_state(order: dict[str, Any]) -> tuple[float, float, float | None, str | None]:
    size = _to_f(order.get("size") or order.get("original_size") or order.get("initial_size")) or 0.0
    filled = _to_f(order.get("size_matched") or order.get("filled_size") or order.get("matched_size") or order.get("filled")) or 0.0
    avg_price = _to_f(order.get("avg_price") or order.get("average_price") or order.get("price"))
    status = str(order.get("status") or order.get("state") or "").lower() or None
    return size, filled, avg_price, status


def _get_order_update(client, order_id: str) -> dict[str, Any] | None:
    # Best-effort across py-clob-client versions.
    candidates = [
        ("get_order", lambda: client.get_order(order_id)),
        ("get_order_by_id", lambda: client.get_order_by_id(order_id)),
    ]
    for name, fn in candidates:
        if not hasattr(client, name):
            continue
        try:
            out = fn()
            if isinstance(out, dict):
                if "order" in out and isinstance(out["order"], dict):
                    return out["order"]
                return out
        except Exception:
            pass

    if hasattr(client, "get_orders"):
        try:
            out = client.get_orders()
            if isinstance(out, list):
                for o in out:
                    if str(o.get("id") or o.get("orderID") or o.get("order_id")) == str(order_id):
                        return o
            elif isinstance(out, dict):
                for key in ("orders", "data"):
                    rows = out.get(key)
                    if isinstance(rows, list):
                        for o in rows:
                            if str(o.get("id") or o.get("orderID") or o.get("order_id")) == str(order_id):
                                return o
        except Exception:
            pass

    return None


def _cancel_order_best_effort(client, order_id: str) -> None:
    for name in ("cancel", "cancel_order", "cancel_orders"):
        if not hasattr(client, name):
            continue
        try:
            fn = getattr(client, name)
            if name == "cancel_orders":
                fn([order_id])
            else:
                fn(order_id)
            return
        except Exception:
            continue


def _wait_for_fill(client, order_id: str, requested_size: float) -> tuple[float, float | None, dict[str, Any] | None]:
    timeout_s = float(os.getenv("POLYMARKET_ORDER_POLL_TIMEOUT_S", "8"))
    interval_s = float(os.getenv("POLYMARKET_ORDER_POLL_INTERVAL_S", "0.4"))

    deadline = time.time() + max(0.5, timeout_s)
    last_order = None

    while time.time() < deadline:
        order = _get_order_update(client, order_id)
        if order:
            last_order = order
            _, filled, avg_price, status = _extract_order_state(order)
            if status in {"filled", "matched", "executed"}:
                return filled, avg_price, last_order
            if requested_size > 0 and filled >= (requested_size - 1e-9):
                return filled, avg_price, last_order
        time.sleep(max(0.1, interval_s))

    if os.getenv("POLYMARKET_CANCEL_UNFILLED_ON_TIMEOUT", "1") == "1":
        _cancel_order_best_effort(client, order_id)

    if last_order:
        _, filled, avg_price, _ = _extract_order_state(last_order)
        return filled, avg_price, last_order
    return 0.0, None, None


def _resolve_order_type_name() -> str:
    raw = os.getenv("POLYMARKET_LIVE_ORDER_TYPE", "GTC").strip().upper()
    if raw not in {"GTC", "FAK", "FOK", "GTD"}:
        raise RuntimeError("POLYMARKET_LIVE_ORDER_TYPE must be one of GTC|FAK|FOK|GTD")
    return raw


def _resolve_order_type():
    try:
        from py_clob_client.clob_types import OrderType
    except Exception as e:
        raise RuntimeError("py-clob-client import mismatch; check installed version") from e

    return getattr(OrderType, _resolve_order_type_name())


def _quantize_buy_size(limit_price: float, size_usd: float, order_type_name: str) -> tuple[float, float]:
    # Polymarket market-style buys (FAK/FOK) are stricter on amount precision.
    if order_type_name in {"FAK", "FOK"}:
        size_usd_q = round(float(size_usd), 2)  # maker amount <= 2 decimals
        contracts_q = round(size_usd_q / float(limit_price), 4)  # taker amount <= 4 decimals
        return size_usd_q, contracts_q

    size_usd_q = round(float(size_usd), 6)
    contracts_q = round(size_usd_q / float(limit_price), 6)
    return size_usd_q, contracts_q


def _quantize_sell_contracts(contracts: float, order_type_name: str) -> float:
    if order_type_name in {"FAK", "FOK"}:
        return round(float(contracts), 4)
    return round(float(contracts), 6)


def _fill_polling_disabled() -> bool:
    return os.getenv("POLYMARKET_DISABLE_FILL_POLLING", "0") == "1"


def _is_invalid_amounts_error(e: Exception) -> bool:
    s = str(e).lower()
    return "invalid amounts" in s or "max accuracy" in s


def _place_limit_buy(client, token_id: str, limit_price: float, size_usd: float) -> dict[str, Any]:
    try:
        from py_clob_client.clob_types import MarketOrderArgs, OrderArgs
        from py_clob_client.order_builder.constants import BUY
    except Exception as e:
        raise RuntimeError("py-clob-client import mismatch; check installed version") from e

    if limit_price <= 0 or limit_price >= 1:
        raise RuntimeError("limit_price must be between 0 and 1")
    if size_usd <= 0:
        raise RuntimeError("size_usd must be > 0")

    order_type_name = _resolve_order_type_name()
    _size_usd_q, requested_contracts = _quantize_buy_size(limit_price, size_usd, order_type_name)

    if requested_contracts <= 0:
        raise RuntimeError("buy_size_too_small_after_precision_rounding")

    order_type = _resolve_order_type()

    if order_type_name in {"FAK", "FOK"}:
        # Use market-order builder for market-style execution; amount is collateral for BUY.
        # Precision edge cases exist at the exchange; retry by reducing amount in 1-cent steps.
        last_exc: Exception | None = None
        signed = None
        for i in range(0, 8):
            amt = round(max(0.01, _size_usd_q - (0.01 * i)), 2)
            try:
                order = MarketOrderArgs(
                    token_id=str(token_id),
                    amount=float(amt),
                    side=BUY,
                    price=float(round(limit_price, 4)),
                )
                signed = client.create_market_order(order)
                requested_contracts = round(amt / float(limit_price), 4)
                break
            except Exception as e:
                last_exc = e
                if not _is_invalid_amounts_error(e):
                    break

        if signed is None:
            # Fallback to regular order builder with quantized size if market builder rejects precision.
            for i in range(0, 8):
                amt = round(max(0.01, _size_usd_q - (0.01 * i)), 2)
                size4 = round(amt / float(limit_price), 4)
                try:
                    order2 = OrderArgs(
                        price=float(round(limit_price, 4)),
                        size=float(size4),
                        side=BUY,
                        token_id=str(token_id),
                    )
                    signed = client.create_order(order2)
                    requested_contracts = size4
                    break
                except Exception as e:
                    last_exc = e
                    if not _is_invalid_amounts_error(e):
                        break

        if signed is None:
            raise RuntimeError(f"buy_order_build_failed: {last_exc}")
    else:
        order = OrderArgs(
            price=float(round(limit_price, 4)),
            size=float(requested_contracts),
            side=BUY,
            token_id=str(token_id),
        )
        signed = client.create_order(order)

    resp = client.post_order(signed, order_type)
    order_id = _extract_order_id(resp or {})

    if not order_id:
        raise RuntimeError(f"missing_order_id_in_response: {resp}")

    if _fill_polling_disabled():
        est_contracts = float(requested_contracts)
        est_price = float(limit_price)
        return {
            "ok": True,
            "fill_price": round(est_price, 6),
            "contracts": round(est_contracts, 6),
            "cost": round(est_contracts * est_price, 6),
            "order_id": order_id,
            "raw": resp,
            "pending_fill": True,
        }

    filled_contracts, avg_price, last_order = _wait_for_fill(client, str(order_id), requested_contracts)
    min_fill_pct = float(os.getenv("POLYMARKET_MIN_FILL_PCT", "0.95"))
    min_contracts = requested_contracts * max(0.0, min(1.0, min_fill_pct))

    if filled_contracts <= 0:
        raise RuntimeError(f"buy_unfilled: order_id={order_id}")
    if filled_contracts < min_contracts:
        raise RuntimeError(
            f"buy_partial_fill_below_threshold: filled={filled_contracts} requested={requested_contracts} min_fill_pct={min_fill_pct}"
        )

    fill_price = float(avg_price) if avg_price and avg_price > 0 else float(limit_price)
    cost = round(filled_contracts * fill_price, 6)

    return {
        "ok": True,
        "fill_price": round(fill_price, 6),
        "contracts": round(float(filled_contracts), 6),
        "cost": cost,
        "order_id": order_id,
        "raw": resp,
        "order": last_order,
    }


def _place_limit_sell(client, token_id: str, limit_price: float, contracts: float) -> dict[str, Any]:
    try:
        from py_clob_client.clob_types import MarketOrderArgs, OrderArgs
        from py_clob_client.order_builder.constants import SELL
    except Exception as e:
        raise RuntimeError("py-clob-client import mismatch; check installed version") from e

    if limit_price <= 0 or limit_price >= 1:
        raise RuntimeError("limit_price must be between 0 and 1")
    if contracts <= 0:
        raise RuntimeError("contracts must be > 0")

    order_type_name = _resolve_order_type_name()
    requested_contracts = _quantize_sell_contracts(float(contracts), order_type_name)

    if requested_contracts <= 0:
        raise RuntimeError("sell_size_too_small_after_precision_rounding")

    order_type = _resolve_order_type()

    if order_type_name in {"FAK", "FOK"}:
        order = MarketOrderArgs(
            token_id=str(token_id),
            amount=float(round(requested_contracts, 4)),
            side=SELL,
            price=float(round(limit_price, 4)),
        )
        try:
            signed = client.create_market_order(order)
        except Exception:
            order2 = OrderArgs(
                price=float(round(limit_price, 4)),
                size=float(round(requested_contracts, 4)),
                side=SELL,
                token_id=str(token_id),
            )
            signed = client.create_order(order2)
    else:
        order = OrderArgs(
            price=float(round(limit_price, 4)),
            size=float(requested_contracts),
            side=SELL,
            token_id=str(token_id),
        )
        signed = client.create_order(order)

    resp = client.post_order(signed, order_type)
    order_id = _extract_order_id(resp or {})

    if not order_id:
        raise RuntimeError(f"missing_order_id_in_response: {resp}")

    if _fill_polling_disabled():
        est_price = float(limit_price)
        return {
            "ok": True,
            "fill_price": round(est_price, 6),
            "proceeds": round(float(requested_contracts) * est_price, 6),
            "order_id": order_id,
            "raw": resp,
            "pending_fill": True,
        }

    filled_contracts, avg_price, last_order = _wait_for_fill(client, str(order_id), requested_contracts)
    min_fill_pct = float(os.getenv("POLYMARKET_MIN_FILL_PCT", "0.95"))
    min_contracts = requested_contracts * max(0.0, min(1.0, min_fill_pct))

    if filled_contracts <= 0:
        raise RuntimeError(f"sell_unfilled: order_id={order_id}")
    if filled_contracts < min_contracts:
        raise RuntimeError(
            f"sell_partial_fill_below_threshold: filled={filled_contracts} requested={requested_contracts} min_fill_pct={min_fill_pct}"
        )

    fill_price = float(avg_price) if avg_price and avg_price > 0 else float(limit_price)
    proceeds = round(filled_contracts * fill_price, 6)

    return {
        "ok": True,
        "fill_price": round(fill_price, 6),
        "proceeds": proceeds,
        "order_id": order_id,
        "raw": resp,
        "order": last_order,
    }


def _normalize_usdc_amount(v: float | None) -> float | None:
    if v is None:
        return None
    # Balance allowance commonly returns USDC in 6-decimal base units.
    if abs(v) > 1_000_000:
        return float(v) / 1_000_000.0
    return float(v)


def _extract_cash_from_any(resp: Any) -> float | None:
    if isinstance(resp, dict):
        for k in ("cash", "cash_available", "available", "available_balance", "balance", "usdc", "collateral"):
            v = _to_f(resp.get(k))
            if v is not None:
                return _normalize_usdc_amount(float(v))
        for k in ("data", "result", "account", "balances"):
            if k in resp:
                v = _extract_cash_from_any(resp[k])
                if v is not None:
                    return v
    elif isinstance(resp, list):
        for row in resp:
            v = _extract_cash_from_any(row)
            if v is not None:
                return v
    return None


def _extract_portfolio_value_from_any(resp: Any) -> float | None:
    if isinstance(resp, dict):
        for k in ("portfolio_value", "equity", "total_value", "account_value", "net_value"):
            v = _to_f(resp.get(k))
            if v is not None:
                return float(v)
        for k in ("data", "result", "account", "balances"):
            if k in resp:
                v = _extract_portfolio_value_from_any(resp[k])
                if v is not None:
                    return v
    elif isinstance(resp, list):
        for row in resp:
            v = _extract_portfolio_value_from_any(row)
            if v is not None:
                return v
    return None


def _extract_positions_from_any(resp: Any) -> list[dict[str, Any]]:
    if isinstance(resp, list):
        out = []
        for row in resp:
            if isinstance(row, dict):
                out.append(row)
        return out
    if isinstance(resp, dict):
        for k in ("positions", "data", "result"):
            if k in resp:
                rows = _extract_positions_from_any(resp[k])
                if rows:
                    return rows
    return []


def _account_state(client) -> dict[str, Any]:
    cash = None
    portfolio_value = None
    positions: list[dict[str, Any]] = []

    # Preferred cash source on py-clob-client: balance allowance (USDC collateral).
    try:
        from py_clob_client.clob_types import BalanceAllowanceParams, AssetType

        if hasattr(client, "get_balance_allowance"):
            resp = client.get_balance_allowance(
                BalanceAllowanceParams(
                    asset_type=AssetType.COLLATERAL,
                    token_id="",
                    signature_type=int(os.getenv("POLYMARKET_SIGNATURE_TYPE", "2")),
                )
            )
            v = _extract_cash_from_any(resp)
            if v is not None:
                cash = round(float(v), 6)
    except Exception:
        pass

    # Try cash/balance/account methods
    for name in ("get_balance", "get_balances", "get_collateral", "get_account", "get_profile"):
        if not hasattr(client, name):
            continue
        try:
            resp = getattr(client, name)()
            if cash is None:
                v = _extract_cash_from_any(resp)
                if v is not None:
                    cash = round(float(v), 6)
            if portfolio_value is None:
                pv = _extract_portfolio_value_from_any(resp)
                if pv is not None:
                    portfolio_value = round(float(pv), 6)
            if cash is not None and portfolio_value is not None:
                break
        except Exception:
            continue

    # Try positions methods
    for name in ("get_positions", "get_open_positions", "get_trades"):
        if not hasattr(client, name):
            continue
        try:
            resp = getattr(client, name)()
            rows = _extract_positions_from_any(resp)
            if rows:
                positions = rows
                break
        except Exception:
            continue

    # Derive portfolio value if needed and possible
    if portfolio_value is None and cash is not None:
        pos_val = 0.0
        for row in positions:
            for k in ("value", "current_value", "market_value", "position_value", "notional", "usd_value"):
                v = _to_f(row.get(k))
                if v is not None:
                    pos_val += float(v)
                    break
        portfolio_value = round(float(cash) + pos_val, 6)

    return {
        "ok": True,
        "cash_available": cash,
        "portfolio_value": portfolio_value,
        "positions": positions,
    }


def _claim_available(client) -> dict[str, Any]:
    """
    Best-effort claim adapter across py-clob-client versions.
    Returns amount if surfaced by API, else 0 with raw response.
    """
    methods = [
        "claim",
        "claim_funds",
        "claim_rewards",
        "redeem",
        "redeem_positions",
        "settle",
    ]
    last_err = None
    for name in methods:
        if not hasattr(client, name):
            continue
        fn = getattr(client, name)
        try:
            resp = fn()
            claimed = 0.0
            if isinstance(resp, dict):
                for k in ("claimed", "amount", "claimed_amount", "total_claimed"):
                    v = _to_f(resp.get(k))
                    if v is not None:
                        claimed = float(v)
                        break
            return {"ok": True, "claimed": round(float(claimed), 6), "raw": resp, "method": name}
        except TypeError:
            # Some versions may require kwargs; try with no-arg variants only for safety.
            last_err = f"{name}: signature_mismatch"
        except Exception as e:
            last_err = f"{name}: {e}"

    if hasattr(client, "get_claimable"):
        try:
            resp = client.get_claimable()
            amt = 0.0
            if isinstance(resp, dict):
                for k in ("claimable", "amount", "total"):
                    v = _to_f(resp.get(k))
                    if v is not None:
                        amt = float(v)
                        break
            return {"ok": True, "claimed": 0.0, "claimable": round(float(amt), 6), "raw": resp, "method": "get_claimable"}
        except Exception as e:
            last_err = f"get_claimable: {e}"

    raise RuntimeError(f"claim_not_supported_or_failed: {last_err}")


def _process_payload(payload: dict[str, Any], client) -> dict[str, Any]:
    action = str(payload.get("action", "")).strip().lower()

    if action == "claim":
        return _claim_available(client)
    if action == "account_state":
        return _account_state(client)
    if action in {"buy", "sell"}:
        symbol = str(payload.get("symbol", "")).strip().upper()
        market_ts = int(payload.get("market_ts"))
        side = str(payload.get("side", "")).strip().upper()

        token_id = str(payload.get("token_id") or "").strip()
        if not token_id:
            slug = _slug(symbol, market_ts)
            market = _fetch_market(slug)
            token_id = _token_id_for_side(market, side)

        if action == "buy":
            limit_price = float(payload.get("limit_price"))
            size_usd = float(payload.get("size_usd"))
            return _place_limit_buy(client, token_id, limit_price, size_usd)

        limit_price = float(payload.get("limit_price"))
        contracts = float(payload.get("contracts"))
        return _place_limit_sell(client, token_id, limit_price, contracts)

    return _fail("action must be buy, sell, claim, or account_state")


def main() -> int:
    daemon = "--daemon" in sys.argv

    if daemon:
        client = _init_clob_client()
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
                out = _process_payload(payload, client)
            except Exception as e:
                out = _fail(str(e))
            sys.stdout.write(json.dumps(out) + "\n")
            sys.stdout.flush()
        return 0

    try:
        payload = _read_stdin_json()
        client = _init_clob_client()
        out = _process_payload(payload, client)
    except Exception as e:
        out = _fail(str(e))

    sys.stdout.write(json.dumps(out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
