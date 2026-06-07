#!/usr/bin/env bash
set -euo pipefail

usage() {
    cat <<EOF
Usage: $0 <host> <role>

Deploy Pi HID Switch files to a Raspberry Pi.

Roles:
  controller    Pi 4B — deploys hid_controller.py + service
  node          Pi Zero W — deploys hid_node.py + usb_gadget_setup.sh + service

Examples:
  $0 192.168.1.100 controller
  $0 hid-controller.local controller
  $0 hid-node-1.local node
EOF
    exit 1
}

HOST="${1:-}"
ROLE="${2:-}"

if [[ -z "$HOST" || -z "$ROLE" ]]; then
    usage
fi

PI_USER="${PI_USER:-pi}"

echo "==> Deploying $ROLE to $PI_USER@$HOST ..."

case "$ROLE" in
    controller)
        echo "    Copying controller daemon..."
        scp controller/hid_controller.py "$PI_USER@$HOST:/usr/local/bin/hid_controller.py"

        echo "    Copying logo..."
        scp assets/pi-km-logo.png "$PI_USER@$HOST:/usr/local/bin/pi-km-logo.png"

        echo "    Copying systemd service..."
        scp services/hid-controller.service "$PI_USER@$HOST:/etc/systemd/system/hid-controller.service"

        echo "    Setting up service..."
        ssh "$PI_USER@$HOST" bash -s <<'SSHEOF'
            set -euo pipefail
            chmod +x /usr/local/bin/hid_controller.py
            mkdir -p /etc/pikm
            systemctl daemon-reload
            systemctl enable hid-controller
            systemctl restart hid-controller
            echo "    Controller service status:"
            systemctl --no-pager status hid-controller
SSHEOF
        ;;

    node)
        echo "    Copying node daemon..."
        scp node/hid_node.py "$PI_USER@$HOST:/usr/local/bin/hid_node.py"

        echo "    Copying USB gadget setup..."
        scp node/usb_gadget_setup.sh "$PI_USER@$HOST:/usr/local/bin/usb_gadget_setup.sh"

        echo "    Copying systemd service..."
        scp services/hid-node.service "$PI_USER@$HOST:/etc/systemd/system/hid-node.service"

        echo "    Setting up service and gadget..."
        ssh "$PI_USER@$HOST" bash -s <<'SSHEOF'
            set -euo pipefail
            chmod +x /usr/local/bin/hid_node.py
            chmod +x /usr/local/bin/usb_gadget_setup.sh

            # Ensure rc.local runs the gadget setup
            if ! grep -q "usb_gadget_setup.sh" /etc/rc.local 2>/dev/null; then
                sed -i '/^exit 0/i /usr/local/bin/usb_gadget_setup.sh' /etc/rc.local
            fi

            systemctl daemon-reload
            systemctl enable hid-node
            systemctl restart hid-node
            echo "    Node service status:"
            systemctl --no-pager status hid-node
SSHEOF

        echo ""
        echo "============================================================"
        echo "  IMPORTANT: Manual steps required for this node:"
        echo "  1. Add 'dtoverlay=dwc2' to /boot/config.txt"
        echo "  2. Add 'modules-load=dwc2,libcomposite' to /boot/cmdline.txt"
        echo "     (insert after 'rootwait' on the same line)"
        echo "  3. Reboot or run usb_gadget_setup.sh manually"
        echo "============================================================"
        ;;

    *)
        echo "Unknown role: $ROLE"
        usage
        ;;
esac

echo "==> Done."
