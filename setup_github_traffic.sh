#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$HOME/projects/github-traffic"
DATA_DIR="$HOME/github-traffic"
DASHBOARD_DIR="$DATA_DIR/dashboard"
LOG_DIR="$DATA_DIR/logs"
SERVICE_DIR="$HOME/.config/systemd/user"
SERVICE_FILE="$SERVICE_DIR/github-traffic-api.service"
CRON_LINE="15 9 * * * $PROJECT_DIR/github_traffic_daily.sh"

mkdir -p "$DATA_DIR" "$DASHBOARD_DIR" "$LOG_DIR" "$SERVICE_DIR"

if [[ ! -f "$PROJECT_DIR/github-traffic.ini" && -f "$PROJECT_DIR/github-traffic.example.ini" ]]; then
  cp "$PROJECT_DIR/github-traffic.example.ini" "$PROJECT_DIR/github-traffic.ini"
  echo "Created local config: $PROJECT_DIR/github-traffic.ini"
fi

cat > "$SERVICE_FILE" <<EOF
[Unit]
Description=GitHub Traffic Local API
After=network.target

[Service]
Type=simple
WorkingDirectory=$PROJECT_DIR
ExecStart=/usr/bin/python3 $PROJECT_DIR/github_traffic_local_api.py --port 8765
Restart=on-failure
RestartSec=3
StandardOutput=append:$DATA_DIR/local-api.log
StandardError=append:$DATA_DIR/local-api.log

[Install]
WantedBy=default.target
EOF

systemctl --user daemon-reload
systemctl --user enable --now github-traffic-api.service

if ! crontab -l 2>/dev/null | grep -Fq "$PROJECT_DIR/github_traffic_daily.sh"; then
  (crontab -l 2>/dev/null; echo "$CRON_LINE") | crontab -
  echo "Installed daily cron job: $CRON_LINE"
else
  echo "Cron job already installed."
fi

python3 "$PROJECT_DIR/generate_static_dashboard.py"

echo
echo "Setup complete."
echo
echo "Useful commands:"
echo "  $PROJECT_DIR/github_traffic_daily.sh"
echo "  $PROJECT_DIR/open_dashboard.sh"
echo "  systemctl --user status github-traffic-api.service"
echo "  curl http://127.0.0.1:8765/health"
