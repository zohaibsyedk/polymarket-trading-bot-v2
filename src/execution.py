from __future__ import annotations

import json
import subprocess
import threading
from dataclasses import dataclass

from .models import Position
from .paper_engine import PortfolioState


@dataclass
class EntryFill:
    price: float
    contracts: float
    cost: float
    order_id: str | None = None


@dataclass
class ExitFill:
    price: float
    proceeds: float
    order_id: str | None = None


class BaseExecutionEngine:
    def enter_position(
        self,
        portfolio: PortfolioState,
        symbol: str,
        market_ts: int,
        side: str,
        limit_price: float,
        size_usd: float,
        now_ts: int,
        token_id: str | None = None,
    ) -> Position:
        raise NotImplementedError

    def exit_position(
        self,
        portfolio: PortfolioState,
        p: Position,
        limit_price: float,
        now_ts: int,
    ) -> Position:
        raise NotImplementedError

    def claim_available_funds(self) -> dict:
        return {"ok": True, "claimed": 0.0, "details": "not_supported"}

    def get_account_state(self) -> dict:
        return {"ok": True, "cash_available": None, "positions": []}


class PaperExecutionEngine(BaseExecutionEngine):
    def enter_position(
        self,
        portfolio: PortfolioState,
        symbol: str,
        market_ts: int,
        side: str,
        limit_price: float,
        size_usd: float,
        now_ts: int,
        token_id: str | None = None,
    ) -> Position:
        return portfolio.create_position(symbol, market_ts, side, limit_price, now_ts, size_usd)

    def exit_position(
        self,
        portfolio: PortfolioState,
        p: Position,
        limit_price: float,
        now_ts: int,
    ) -> Position:
        return portfolio.close_position(p.position_id, limit_price, now_ts)

    def get_account_state(self) -> dict:
        return {"ok": True, "cash_available": None, "positions": []}


class LiveExecutionBridgeEngine(BaseExecutionEngine):
    """
    Live mode via external bridge command.

    Configure PMB2_LIVE_BRIDGE_CMD as an executable command that reads JSON from stdin
    and returns JSON to stdout.

    Buy request payload example:
      {"action":"buy","symbol":"BTC","market_ts":123,"side":"UP","limit_price":0.81,"size_usd":50}

    Buy response JSON expected:
      {"ok":true,"fill_price":0.81,"contracts":61.728395,"cost":50,"order_id":"abc"}

    Sell request payload example:
      {"action":"sell","symbol":"BTC","market_ts":123,"side":"UP","contracts":61.728395,"limit_price":0.52}

    Sell response JSON expected:
      {"ok":true,"fill_price":0.52,"proceeds":32.098765,"order_id":"def"}
    """

    def __init__(self, bridge_cmd: str, timeout_seconds: int = 15, persistent: bool = True):
        if not bridge_cmd.strip():
            raise ValueError("PMB2_LIVE_BRIDGE_CMD is required in live mode")
        self.bridge_cmd = bridge_cmd
        self.timeout_seconds = timeout_seconds
        self.persistent = persistent
        self._proc = None
        self._lock = threading.Lock()

    def _ensure_proc(self):
        if self._proc and self._proc.poll() is None:
            return
        cmd = f"{self.bridge_cmd} --daemon"
        self._proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            shell=True,
            bufsize=1,
        )

    def _call_bridge_once(self, payload: dict) -> dict:
        p = subprocess.run(
            self.bridge_cmd,
            input=json.dumps(payload),
            capture_output=True,
            text=True,
            shell=True,
            timeout=self.timeout_seconds,
            check=False,
        )
        if p.returncode != 0:
            raise RuntimeError(f"bridge_failed: rc={p.returncode} stderr={p.stderr.strip()}")
        try:
            out = json.loads(p.stdout.strip() or "{}")
        except Exception as e:
            raise RuntimeError(f"bridge_invalid_json: {e}") from e
        if not out.get("ok"):
            raise RuntimeError(f"bridge_order_rejected: {out}")
        return out

    def _call_bridge(self, payload: dict) -> dict:
        if not self.persistent:
            return self._call_bridge_once(payload)

        with self._lock:
            self._ensure_proc()
            assert self._proc and self._proc.stdin and self._proc.stdout
            self._proc.stdin.write(json.dumps(payload) + "\n")
            self._proc.stdin.flush()
            line = self._proc.stdout.readline().strip()
            if not line:
                # fallback once if daemon protocol unavailable
                return self._call_bridge_once(payload)
            try:
                out = json.loads(line)
            except Exception as e:
                raise RuntimeError(f"bridge_invalid_json: {e}; raw={line[:200]}") from e
            if not out.get("ok"):
                raise RuntimeError(f"bridge_order_rejected: {out}")
            return out

    def enter_position(
        self,
        portfolio: PortfolioState,
        symbol: str,
        market_ts: int,
        side: str,
        limit_price: float,
        size_usd: float,
        now_ts: int,
        token_id: str | None = None,
    ) -> Position:
        payload = {
            "action": "buy",
            "symbol": symbol,
            "market_ts": market_ts,
            "side": side,
            "limit_price": float(limit_price),
            "size_usd": float(size_usd),
        }
        if token_id:
            payload["token_id"] = str(token_id)
        out = self._call_bridge(payload)
        fill = EntryFill(
            price=float(out["fill_price"]),
            contracts=float(out["contracts"]),
            cost=float(out["cost"]),
            order_id=out.get("order_id"),
        )
        return portfolio.create_position_from_fill(
            symbol=symbol,
            market_ts=market_ts,
            side=side,
            price=fill.price,
            contracts=fill.contracts,
            cost=fill.cost,
            now_ts=now_ts,
            entry_order_id=fill.order_id,
            token_id=str(token_id) if token_id else None,
        )

    def exit_position(
        self,
        portfolio: PortfolioState,
        p: Position,
        limit_price: float,
        now_ts: int,
    ) -> Position:
        payload = {
            "action": "sell",
            "symbol": p.symbol,
            "market_ts": p.market_ts,
            "side": p.side,
            "contracts": float(p.contracts),
            "limit_price": float(limit_price),
        }
        if p.token_id:
            payload["token_id"] = str(p.token_id)
        out = self._call_bridge(payload)
        fill = ExitFill(
            price=float(out["fill_price"]),
            proceeds=float(out["proceeds"]),
            order_id=out.get("order_id"),
        )
        return portfolio.close_position_from_fill(
            position_id=p.position_id,
            exit_price=fill.price,
            proceeds=fill.proceeds,
            now_ts=now_ts,
            exit_order_id=fill.order_id,
        )

    def claim_available_funds(self) -> dict:
        return self._call_bridge({"action": "claim"})

    def get_account_state(self) -> dict:
        return self._call_bridge({"action": "account_state"})
