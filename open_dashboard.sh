#!/usr/bin/env bash
set -euo pipefail

DASHBOARD="$HOME/github-traffic/dashboard/dashboard.html"

if [[ ! -f "$DASHBOARD" ]]; then
  cd "$HOME/projects/github-traffic"
  python3 generate_static_dashboard.py
fi

xdg-open "$DASHBOARD" >/dev/null 2>&1 &
echo "Opened $DASHBOARD"
