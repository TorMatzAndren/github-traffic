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
  python3 generate_static_dashboard.py

  echo "=== Done: $(date -Is) ==="
} >> "$LOG_FILE" 2>&1
