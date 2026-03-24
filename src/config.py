from dataclasses import dataclass
from pathlib import Path
import os


@dataclass
class BotConfig:
    starting_cash: float = float(os.getenv("PMB2_STARTING_CASH", "1000"))
    poll_seconds: float = float(os.getenv("PMB2_POLL_SECONDS", "2"))
    hot_poll_seconds: float = float(os.getenv("PMB2_HOT_POLL_SECONDS", "1.0"))
    hot_tick_budget_ms: float = float(os.getenv("PMB2_HOT_TICK_BUDGET_MS", "300"))
    hot_min_logging: bool = os.getenv("PMB2_HOT_MIN_LOGGING", "1") == "1"

    market_interval_seconds: int = 300
    final_entry_window_seconds: int = 50
    entry_min_price_threshold: float = 0.75
    stop_loss_pct_of_entry: float = 0.60

    min_cash_to_enter: float = 10.0
    min_position_usd: float = 50.0
    position_pct_cash: float = 0.10

    workspace_root: Path = Path(__file__).resolve().parents[1]
    logs_dir: Path = Path(os.getenv("PMB2_LOGS_DIR", str(workspace_root / "logs")))
    state_dir: Path = Path(os.getenv("PMB2_STATE_DIR", str(workspace_root / "state")))

    # Trading mode
    trading_mode: str = os.getenv("PMB2_TRADING_MODE", "paper").strip().lower()  # paper | live
    live_bridge_cmd: str = os.getenv("PMB2_LIVE_BRIDGE_CMD", "").strip()
    live_bridge_timeout_s: int = int(os.getenv("PMB2_LIVE_BRIDGE_TIMEOUT_S", "15"))
    bridge_persistent: bool = os.getenv("PMB2_BRIDGE_PERSISTENT", "1") == "1"

    # Risk controls
    max_position_usd: float = float(os.getenv("PMB2_MAX_POSITION_USD", "100"))
    max_total_open_usd: float = float(os.getenv("PMB2_MAX_TOTAL_OPEN_USD", "300"))

    # Buy-floor controls
    min_buy_trigger_price: float = float(os.getenv("PMB2_MIN_BUY_TRIGGER_PRICE", "0.74"))
    min_buy_fill_price: float = float(os.getenv("PMB2_MIN_BUY_FILL_PRICE", "0.74"))
    pause_on_buy_fill_below_min: bool = os.getenv("PMB2_PAUSE_ON_BUY_FILL_BELOW_MIN", "1") == "1"
    buy_cap_offset: float = float(os.getenv("PMB2_BUY_CAP_OFFSET", "0.00"))

    # Entry polling starts at final_entry_window_seconds boundary.

    # Live auto-claim controls
    auto_claim_enabled: bool = os.getenv("PMB2_AUTO_CLAIM_ENABLED", "1") == "1"
    auto_claim_interval_s: int = int(os.getenv("PMB2_AUTO_CLAIM_INTERVAL_S", "90"))

    # Live reconciliation controls
    reconcile_enabled: bool = os.getenv("PMB2_RECONCILE_ENABLED", "1") == "1"
    reconcile_interval_s: int = int(os.getenv("PMB2_RECONCILE_INTERVAL_S", "20"))
    reconcile_cash_drift_usd: float = float(os.getenv("PMB2_RECONCILE_CASH_DRIFT_USD", "1.0"))

    # Telegram runtime controls
    telegram_enabled: bool = os.getenv("PMB2_TELEGRAM_ENABLED", "0") == "1"
    telegram_bot_token: str = os.getenv("PMB2_TELEGRAM_BOT_TOKEN", "")
    telegram_chat_id: str = os.getenv("PMB2_TELEGRAM_CHAT_ID", "")
    telegram_poll_timeout_s: int = int(os.getenv("PMB2_TELEGRAM_POLL_TIMEOUT_S", "0"))
