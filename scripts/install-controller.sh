#!/usr/bin/env bash
set -euo pipefail

REPO_BASE="https://raw.githubusercontent.com/tomhillmeyer/pi-km/$(curl -fsSL https://api.github.com/repos/tomhillmeyer/pi-km/releases/latest | python3 -c "import sys,json; print(json.load(sys.stdin)['tag_name'])" 2>/dev/null || echo main)"

echo "==> Installing PiKM controller..."

apt update
apt install -y python3 python3-pip python3-evdev

mkdir -p /etc/pikm
echo '{"nodes":{}, "active": ""}' > /etc/pikm/nodes.json

curl -fsSL "$REPO_BASE/controller/hid_controller.py" -o /usr/local/bin/hid_controller.py
chmod +x /usr/local/bin/hid_controller.py

curl -fsSL "$REPO_BASE/services/hid-controller.service" -o /etc/systemd/system/hid-controller.service

systemctl daemon-reload
systemctl enable --now hid-controller

IP=$(hostname -I | awk '{print $1}')
echo ""
echo "==> Controller installed and running."
echo "    Web UI: http://${IP}:80/"
echo "    Add nodes at the web UI or edit /etc/pikm/nodes.json"
