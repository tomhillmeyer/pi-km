import struct
import logging

KEYBOARD_DEVICE = "/dev/hidg0"
MOUSE_DEVICE = "/dev/hidg1"
CONSUMER_DEVICE = "/dev/hidg2"

_initialized = False

log = logging.getLogger("pikm.linux")


def init():
    global _initialized
    try:
        with open(KEYBOARD_DEVICE, "rb+") as f:
            pass
    except FileNotFoundError:
        raise RuntimeError(
            "USB gadget devices not found. "
            "Make sure dwc2 overlay and gadget setup are configured."
        )
    _initialized = True


def _caps_lock_toggle():
    pass


def keyboard_report(report: bytes):
    with open(KEYBOARD_DEVICE, "rb+") as f:
        f.write(report)


def mouse_report(report: bytes):
    with open(MOUSE_DEVICE, "rb+") as f:
        f.write(report)


def consumer_report(report: bytes):
    with open(CONSUMER_DEVICE, "rb+") as f:
        f.write(report)
