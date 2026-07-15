#!/usr/bin/env bash
set -euo pipefail

REPO_BASE="https://raw.githubusercontent.com/tomhillmeyer/pi-km/$(curl -fsSL https://api.github.com/repos/tomhillmeyer/pi-km/releases/latest | python3 -c "import sys,json; print(json.load(sys.stdin)['tag_name'])" 2>/dev/null || echo main)"

echo "==> Installing PiKM node (USB gadget)..."

apt update
apt install -y python3 python3-pip

curl -fsSL "$REPO_BASE/node/hid_node.py" -o /usr/local/bin/hid_node.py
chmod +x /usr/local/bin/hid_node.py

curl -fsSL "$REPO_BASE/node/usb_gadget_setup.sh" -o /usr/local/bin/usb_gadget_setup.sh
chmod +x /usr/local/bin/usb_gadget_setup.sh

curl -fsSL "$REPO_BASE/services/hid-node.service" -o /etc/systemd/system/hid-node.service
curl -fsSL "$REPO_BASE/services/pikm-usb-gadget.service" -o /etc/systemd/system/pikm-usb-gadget.service

if ! grep -q "^dtoverlay=dwc2" /boot/config.txt 2>/dev/null; then
    echo "dtoverlay=dwc2" >> /boot/config.txt
fi

if ! grep -q "modules-load=dwc2,libcomposite" /boot/cmdline.txt 2>/dev/null; then
    sed -i 's/rootwait/rootwait modules-load=dwc2,libcomposite/' /boot/cmdline.txt
fi

systemctl daemon-reload
systemctl enable --now pikm-usb-gadget hid-node

echo ""
echo "==> Node installed. Rebooting to activate USB gadget..."
reboot
