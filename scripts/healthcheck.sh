#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

if [ -f .env ]; then
  set -a
  source .env
  set +a
fi

echo "[M5 Healthcheck] PolyMarket Trading Bot V2"

echo "- Python: $(python3 --version 2>/dev/null || echo missing)"

if [ "${PMB2_TELEGRAM_ENABLED:-0}" = "1" ]; then
  if [ -z "${PMB2_TELEGRAM_BOT_TOKEN:-}" ]; then
    echo "- Telegram: FAIL (PMB2_TELEGRAM_BOT_TOKEN missing)"
    exit 1
  fi
  echo "- Telegram: configured"
  python3 - <<'PY'
import os, json, urllib.request
token=os.environ.get('PMB2_TELEGRAM_BOT_TOKEN','')
url=f'https://api.telegram.org/bot{token}/getMe'
try:
    with urllib.request.urlopen(url, timeout=12) as r:
        d=json.loads(r.read().decode())
    ok=d.get('ok',False)
    u=d.get('result',{}).get('username')
    print(f"- Telegram getMe: {'OK' if ok else 'FAIL'} ({u})")
except Exception as e:
    print(f"- Telegram getMe: FAIL ({e})")
    raise
PY
else
  echo "- Telegram: disabled (PMB2_TELEGRAM_ENABLED!=1)"
fi

python3 - <<'PY'
import time
from src.market_discovery import current_5m_window
from src.market_data import resolve_current_market
now=int(time.time())
w=current_5m_window(now)
print(f"- Time bucket: {w.ts_bucket}")
for sym in ('BTC','ETH'):
    m=resolve_current_market(sym, w.ts_bucket)
    if not m:
        print(f"- {sym} market resolve: FAIL")
    else:
        print(f"- {sym} market resolve: OK ({m.slug}) up={m.up_price} down={m.down_price}")
PY

echo "- Logs path: $(pwd)/logs"
echo "- State path: $(pwd)/state/status_snapshot.json"
echo "Healthcheck complete."
