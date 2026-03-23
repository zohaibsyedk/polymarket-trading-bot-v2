from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import replace
from typing import Dict, Optional

from .market_data import ResolvedMarket, resolve_current_market


class OrderBookWsFeed:
    """Optional websocket top-of-book feed (best-effort, schema-tolerant).

    Enabled only when PMB2_WS_ENABLED=1 and websocket-client is installed.
    """

    def __init__(self):
        self.enabled = os.getenv("PMB2_WS_ENABLED", "0") == "1"
        self.url = os.getenv("PMB2_WS_URL", "wss://clob.polymarket.com/ws")
        self._lock = threading.Lock()
        self._best: dict[str, tuple[Optional[float], Optional[float]]] = {}
        self._tokens: set[str] = set()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self):
        if not self.enabled:
            return
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()

    def set_tokens(self, token_ids: list[str]):
        if not self.enabled:
            return
        with self._lock:
            self._tokens = set(str(x) for x in token_ids if x)

    def get_best(self, token_id: str) -> tuple[Optional[float], Optional[float]]:
        with self._lock:
            return self._best.get(str(token_id), (None, None))

    def _parse_message(self, msg: str):
        try:
            d = json.loads(msg)
        except Exception:
            return

        # Try common shapes.
        rows = []
        if isinstance(d, dict):
            if isinstance(d.get("data"), list):
                rows = d["data"]
            elif isinstance(d.get("data"), dict):
                rows = [d["data"]]
            else:
                rows = [d]
        elif isinstance(d, list):
            rows = d

        with self._lock:
            for r in rows:
                if not isinstance(r, dict):
                    continue
                token = r.get("token_id") or r.get("tokenId") or r.get("asset_id")
                if not token:
                    continue
                bid = r.get("best_bid") or r.get("bestBid") or r.get("bid")
                ask = r.get("best_ask") or r.get("bestAsk") or r.get("ask")
                try:
                    bid_f = float(bid) if bid is not None else None
                except Exception:
                    bid_f = None
                try:
                    ask_f = float(ask) if ask is not None else None
                except Exception:
                    ask_f = None
                self._best[str(token)] = (bid_f, ask_f)

    def _run(self):
        try:
            import websocket  # type: ignore
        except Exception:
            return

        while not self._stop.is_set():
            ws = None
            try:
                ws = websocket.create_connection(self.url, timeout=3)

                # Send subscription if configured.
                subscribe_payload = os.getenv("PMB2_WS_SUBSCRIBE_PAYLOAD", "").strip()
                if subscribe_payload:
                    try:
                        with self._lock:
                            toks = sorted(self._tokens)
                        payload = subscribe_payload.replace("{token_ids_json}", json.dumps(toks))
                        ws.send(payload)
                    except Exception:
                        pass

                while not self._stop.is_set():
                    try:
                        msg = ws.recv()
                    except Exception:
                        break
                    if not msg:
                        continue
                    self._parse_message(msg)
            except Exception:
                pass
            finally:
                try:
                    if ws is not None:
                        ws.close()
                except Exception:
                    pass

            time.sleep(1.0)


class MarketFeed:
    """Background market-data loop so execution loop doesn't block on fetch."""

    def __init__(self, market_interval_seconds: int, poll_seconds: float, hot_poll_seconds: float, final_entry_window_seconds: int):
        self.market_interval_seconds = market_interval_seconds
        self.poll_seconds = float(poll_seconds)
        self.hot_poll_seconds = float(hot_poll_seconds)
        self.final_entry_window_seconds = int(final_entry_window_seconds)

        self._lock = threading.Lock()
        self._active: Dict[str, ResolvedMarket] = {}
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._ws = OrderBookWsFeed()

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._ws.start()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        self._ws.stop()

    def snapshot(self) -> Dict[str, ResolvedMarket]:
        with self._lock:
            return dict(self._active)

    def _run(self):
        while not self._stop.is_set():
            now_ts = int(time.time())
            bucket_ts = now_ts - (now_ts % self.market_interval_seconds)

            fresh: Dict[str, ResolvedMarket] = {}
            for symbol in ("BTC", "ETH"):
                try:
                    m = resolve_current_market(symbol, bucket_ts, now_ts)
                except Exception:
                    m = None
                if m:
                    fresh[symbol] = m

            # Update websocket token subscriptions.
            toks = []
            for m in fresh.values():
                toks.extend([m.up_token_id, m.down_token_id])
            self._ws.set_tokens(toks)

            # If websocket has newer top-of-book, overlay best bid/ask.
            overlaid: Dict[str, ResolvedMarket] = {}
            for sym, m in fresh.items():
                up_bid, up_ask = self._ws.get_best(m.up_token_id)
                dn_bid, dn_ask = self._ws.get_best(m.down_token_id)

                entry_up = up_ask if up_ask is not None else m.entry_up_price
                entry_down = dn_ask if dn_ask is not None else m.entry_down_price
                mark_up = up_bid if up_bid is not None else m.up_price
                mark_down = dn_bid if dn_bid is not None else m.down_price

                overlaid[sym] = replace(
                    m,
                    up_price=float(mark_up),
                    down_price=float(mark_down),
                    entry_up_price=float(entry_up),
                    entry_down_price=float(entry_down),
                    bid_up_price=up_bid if up_bid is not None else m.bid_up_price,
                    ask_up_price=up_ask if up_ask is not None else m.ask_up_price,
                    bid_down_price=dn_bid if dn_bid is not None else m.bid_down_price,
                    ask_down_price=dn_ask if dn_ask is not None else m.ask_down_price,
                )

            with self._lock:
                self._active = overlaid

            sec_in_market = now_ts % self.market_interval_seconds
            in_hot = sec_in_market >= (self.market_interval_seconds - self.final_entry_window_seconds)
            sleep_s = self.hot_poll_seconds if in_hot else self.poll_seconds
            time.sleep(max(0.1, float(sleep_s)))
