#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$HOME/projects/github-traffic"
LOG_DIR="$HOME/github-traffic/logs"
LOG_FILE="$LOG_DIR/daily.log"

mkdir -p "$LOG_DIR"

{
  echo
  echo "=== GitHub Traffic Daily Run: $(date -Is) ==="
  cd "$PROJECT_DIR"

  python3 github_traffic_collect.py --verbose

  latest_status="$(sqlite3 "$HOME/github-traffic/github-traffic.sqlite3" "SELECT status FROM collection_runs ORDER BY id DESC LIMIT 1;")"
  echo "Latest collection status: $latest_status"

  if [[ "$latest_status" == "completed_new_daily_data" || "$latest_status" == "completed" ]]; then
    python3 generate_static_dashboard.py
    echo "Dashboard regenerated because new daily data was detected."
  else
    echo "Dashboard regeneration skipped because no new daily data was detected."
  fi

  echo "=== Done: $(date -Is) ==="
} >> "$LOG_FILE" 2>&1
