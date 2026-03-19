from dataclasses import dataclass
from pathlib import Path
import os


@dataclass
class BotConfig:
    starting_cash: float = float(os.getenv("PMB2_STARTING_CASH", "1000"))
    poll_seconds: float = float(os.getenv("PMB2_POLL_SECONDS", "2"))

    market_interval_seconds: int = 300
    final_entry_window_seconds: int = 90
    entry_min_price_threshold: float = 0.75
    stop_loss_pct_of_entry: float = 0.40

    min_cash_to_enter: float = 10.0
    min_position_usd: float = 50.0
    position_pct_cash: float = 0.10

    workspace_root: Path = Path(__file__).resolve().parents[1]
    logs_dir: Path = Path(os.getenv("PMB2_LOGS_DIR", str(workspace_root / "logs")))
    state_dir: Path = Path(os.getenv("PMB2_STATE_DIR", str(workspace_root / "state")))

    # Telegram runtime controls
    telegram_enabled: bool = os.getenv("PMB2_TELEGRAM_ENABLED", "0") == "1"
    telegram_bot_token: str = os.getenv("PMB2_TELEGRAM_BOT_TOKEN", "")
    telegram_chat_id: str = os.getenv("PMB2_TELEGRAM_CHAT_ID", "")
    telegram_poll_timeout_s: int = int(os.getenv("PMB2_TELEGRAM_POLL_TIMEOUT_S", "0"))
