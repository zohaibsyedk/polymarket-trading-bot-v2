#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

if [ -f .env ]; then
  set -a
  source .env
  set +a
fi

RUN_ID="$(date +%Y%m%d-%H%M%S)-$$"
ARCHIVE_LOG_DIR="$(pwd)/logs/archive/${RUN_ID}"
ARCHIVE_STATE_DIR="$(pwd)/state/archive/${RUN_ID}"

mkdir -p "$ARCHIVE_LOG_DIR" "$ARCHIVE_STATE_DIR"

# Per-run isolated output directories.
export PMB2_LOGS_DIR="$ARCHIVE_LOG_DIR"
export PMB2_STATE_DIR="$ARCHIVE_STATE_DIR"

# Convenience symlinks to the active/latest run.
ln -sfn "$ARCHIVE_LOG_DIR" "$(pwd)/logs/latest"
ln -sfn "$ARCHIVE_STATE_DIR" "$(pwd)/state/latest"

echo "[run.sh] RUN_ID=$RUN_ID"
echo "[run.sh] logs -> $PMB2_LOGS_DIR"
echo "[run.sh] state -> $PMB2_STATE_DIR"

python3 -m src.main
