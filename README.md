<img src="assets/pi-km-logo.png" width="300px">

PiKM is a network switchable, theoretically infinitely scalable HID server for Raspberry Pi. Use a Raspberry Pi to send keyboard and mouse input over LAN.

## Why PiKM?
- PiKM was created for situations where high quality video and network switching infrastructure already exists, but that infrastructure didn't have USB switching.
- In professional production environments where high quality video switching and routing infrastructure is already necessary, PiKM slots in providing the ability to interact with the sources being routed.
- Using the PiKM API, users can use applications such as Bitfocus Companion to keep video routers and PiKM in sync.

### Use Cases
- Quickly switch between controlling computers being used as displays, without relying on a Bluetooth or wireless dongle range.
- Extend your keyboard and mouse over LAN

### It's not for every use case
- Gaming for one! Mouse and keyboard inputs are being read by a Raspberry Pi and then transported over a network, so latency is going to exist. Much like full KVMs, most are intended for intermittent access and not daily driving.

## Overview
PiKM exists in two pieces: the **Controller** and **Nodes**. 

The controller is a Raspberry Pi on your LAN with your keyboard and mouse plugged in to. 

Nodes are all of the devices you want to control. You can install PiKM as a toolbar app on macOS and Windows, or you can set up another Pi to act as a USB HID device.

The controller hosts a web UI, where nodes are added to the controller and you can switch between them. Switching between nodes is also available through an API.

## Install

### Controller (Pi 4/5)
_(Raspberry Pi OS Lite)_

```bash
curl -fsSL https://raw.githubusercontent.com/tomhillmeyer/pi-km/main/scripts/install-controller.sh | sudo bash
```

Web UI available at `http://<controller-ip>/` after install.

### Node (Pi Zero/4/5, USB gadget)
_(Raspberry Pi OS Lite)_

```bash
curl -fsSL https://raw.githubusercontent.com/tomhillmeyer/pi-km/main/scripts/install-node.sh | sudo bash
```

The node script will reboot after setup to activate the USB gadget kernel modules.

### Node (macOS and Windows)

Download the latest installers from [Releases](https://github.com/tomhillmeyer/pi-km/releases)


## API

All on the controller (port 80):

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/` | Web UI |
| `GET` | `/status` | `{"active":"...", "connected":true/false}` |
| `GET` | `/switch?target=<name>` | Switch to node |
| `GET` | `/nodes` | List all nodes |
| `POST` | `/nodes` | Add node (JSON: `{"name":"...","ip":"..."}`) |
| `DELETE` | `/nodes?name=<name>` | Remove node |

## Protocol

TCP :9876, one type byte + fixed payload:

| Type | Name | Payload |
|------|------|---------|
| `0x00` | Heartbeat | 0 bytes |
| `0x01` | Keyboard | 8 bytes (modifiers, reserved, 6× HID keycodes) |
| `0x02` | Mouse | 4 bytes (buttons, dx, dy, scroll) |
| `0x03` | Consumer | 2 bytes (HID consumer usage, LE) |

## Local Development

### Clone the repo

```bash
git clone https://github.com/tomhillmeyer/pi-km.git
cd pi-km
```

### Install dependencies

**macOS:**

```bash
pip3 install -r desktop_node/requirements.txt
pip3 install rumps pyobjc
```

**Windows:**

```bash
pip install -r desktop_node/requirements.txt
pip install pystray Pillow
```

### Run the desktop node locally

**macOS:**

```bash
python3 pikm-node.py
```

**Windows:**

```bash
python pikm-node.py
```

### Development test tools

```bash
python3 devtools/test_keyboard.py <node-ip>
python3 devtools/test_mouse.py <node-ip>
python3 devtools/send_report.py <host> <type_hex> <hex_bytes...>
```

### Deploy controller changes to a Pi

```bash
./deploy.sh <ip> controller
```

### Deploy node changes to a Pi

```bash
./deploy.sh <ip> node
```
