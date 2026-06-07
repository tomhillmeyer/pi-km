#!/usr/bin/env python3
import socket
import struct
import threading
import sys
import os
import logging

try:
    from .backends import create_backend
except ImportError:
    from backends import create_backend

HOST = "0.0.0.0"
PORT = 9876
LOG_FILE = "/tmp/pikm-node.log"
VERSION = "1.0.0"

WORDMARK_B64 = """iVBORw0KGgoAAAANSUhEUgAAABYAAAAWCAYAAADEtGw7AAABiUlEQVR4nO3TP2xOYRQG8N93P7o0GmFjaMRCooLEKCYLQxMGiejAKHQgJjEJkRgNVgwk0qGzVtOIRiQGbZogaFhYWFT81ytv81y5EQODoUlPcnPfc857znme857DsixZ6WDFH+w/0MUCqvwXcr/bOndaPi3//0V8DivRE6SPMIEzuI79mMI4VuE0nuIjtmMMd5Ov+E82XajxHS/wLvox3MH+6OcTOBl9G0Zznmq15XBsdZWkl7ARA9FX4xbe4AvmcQG7sSusxLcTm5PwKD7jU4P4ZlAcin45/xNJvogiNIsUQLdxH29xFmty50Za+iuozvcKB1L1CD5gBA/xOAkK7XtJcgWzuIg5HEyeRepXsQlb0Je2lKpD+Ibj6E/AaKvfpeDW2L/iFPaUnFXmbh5PUvk9ekO3Jy+8IUyGMZgWFUDrMYPXmaxreZ9uobQPL0OzCtLePNR0ED3HsyAriDoBU/QH2IG16fu6jOE/z/1f+ZsVrFtr2dibVa5+87dXtm7d6YRtE7ssS1V+Ai4acyPKsCkCAAAAAElFTkSuQmCC"""

def _wordmark_path():
    path = "/tmp/pikm-wordmark.png"
    if not os.path.exists(path):
        import base64
        with open(path, "wb") as f:
            f.write(base64.b64decode(WORDMARK_B64))
    return path


def _load_wordmark_pil():
    try:
        from PIL import Image
        import base64
        from io import BytesIO
        data = base64.b64decode(WORDMARK_B64)
        img = Image.open(BytesIO(data))
        return img
    except Exception:
        return None
        data = base64.b64decode(WORDMARK_B64)
        img = Image.open(BytesIO(data))
        return img
    except Exception:
        return None
backend = None
_connected = False
_connected_addr = None
_connection_lock = threading.Lock()
_listener_thread = None
_stop_event = threading.Event()
_log_handler = None

_num_lock_on = True
_caps_lock_held = False
_last_kbd_report = None

_NUMPAD_TO_NAV = {
    0x59: 0x4D,  # KP1 → End
    0x5A: 0x51,  # KP2 → Down
    0x5B: 0x4E,  # KP3 → PageDown
    0x5C: 0x50,  # KP4 → Left
    0x5E: 0x4F,  # KP6 → Right
    0x5F: 0x4A,  # KP7 → Home
    0x60: 0x52,  # KP8 → Up
    0x61: 0x4B,  # KP9 → PageUp
    0x62: 0x49,  # KP0 → Insert
    0x63: 0x4C,  # KP. → Delete
}


def _preprocess_kbd(report: bytes) -> bytes:
    global _num_lock_on, _caps_lock_held, _last_kbd_report
    keys = bytearray(report[2:])
    old_set = set(_last_kbd_report[2:]) if _last_kbd_report else set()
    new_set = set(keys) - {0x00}
    if 0x53 in new_set and 0x53 not in old_set:
        _num_lock_on = not _num_lock_on
    if 0x39 in new_set and not _caps_lock_held:
        backend._caps_lock_toggle()
        _caps_lock_held = True
    elif 0x39 not in new_set and _caps_lock_held:
        _caps_lock_held = False
    if not _num_lock_on:
        for i in range(6):
            if keys[i] in _NUMPAD_TO_NAV:
                keys[i] = _NUMPAD_TO_NAV[keys[i]]
    for i in range(6):
        if keys[i] == 0x39:
            keys[i] = 0x00
    _last_kbd_report = bytes([report[0], report[1]]) + bytes(keys)
    return _last_kbd_report


def _setup_logging():
    global _log_handler
    logger = logging.getLogger("pikm")
    logger.setLevel(logging.DEBUG)
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    try:
        fh = logging.FileHandler(LOG_FILE)
        fh.setFormatter(fmt)
        logger.addHandler(fh)
    except Exception:
        pass
    sh = logging.StreamHandler(sys.stderr)
    sh.setFormatter(fmt)
    logger.addHandler(sh)
    _log_handler = sh


def log(msg, level=logging.INFO):
    logging.getLogger("pikm").log(level, msg)


def _recv_exact(conn, n):
    data = bytearray()
    while len(data) < n:
        chunk = conn.recv(n - len(data))
        if not chunk:
            return None
        data.extend(chunk)
    return bytes(data)


def _handle_connection(conn, addr):
    global _connected, _connected_addr
    with _connection_lock:
        _connected = True
        _connected_addr = addr
    log(f"Connection from {addr}")
    with conn:
        while not _stop_event.is_set():
            try:
                conn.settimeout(1.0)
                type_byte = _recv_exact(conn, 1)
                if type_byte is None:
                    break
                msg_type = type_byte[0]
                if msg_type == 0x00:
                    continue
                elif msg_type == 0x01:
                    report = _recv_exact(conn, 8)
                    if report is None:
                        break
                    log(f"kbd report: {report.hex()}", logging.DEBUG)
                    report = _preprocess_kbd(report)
                    backend.keyboard_report(report)
                elif msg_type == 0x02:
                    report = _recv_exact(conn, 4)
                    if report is None:
                        break
                    log(f"mouse report: {report.hex()}", logging.DEBUG)
                    backend.mouse_report(report)
                elif msg_type == 0x03:
                    report = _recv_exact(conn, 2)
                    if report is None:
                        break
                    log(f"consumer report: {report.hex()}", logging.DEBUG)
                    backend.consumer_report(report)
            except socket.timeout:
                continue
            except Exception as e:
                log(f"handler error: {e}", logging.ERROR)
                break
    with _connection_lock:
        _connected = False
        _connected_addr = None
    log(f"Connection from {addr} closed")


def _listener():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind((HOST, PORT))
        s.listen()
        s.settimeout(0.5)
        log(f"Listening on {PORT}")
        while not _stop_event.is_set():
            try:
                conn, addr = s.accept()
                threading.Thread(
                    target=_handle_connection, args=(conn, addr), daemon=True
                ).start()
            except socket.timeout:
                continue
            except Exception as e:
                log(f"listener error: {e}", logging.ERROR)
                break


_menu_instance = None


def run_cli():
    global _listener_thread
    log("CLI mode")
    _listener_thread = threading.Thread(target=_listener, daemon=True)
    _listener_thread.start()
    try:
        while not _stop_event.is_set():
            threading.Event().wait(1)
    except KeyboardInterrupt:
        log("Shutting down (Ctrl+C)")


def run_tray():
    global _listener_thread
    _listener_thread = threading.Thread(target=_listener, daemon=True)
    _listener_thread.start()

    if sys.platform == "darwin":
        _run_rumps_tray()
    else:
        _run_pystray_tray()


def _load_wordmark_nsimage():
    try:
        import AppKit
        import base64
        data = base64.b64decode(WORDMARK_B64)
        img = AppKit.NSImage.alloc().initWithData_(data)
        if img:
            img.setTemplate_(True)
        return img
    except Exception:
        return None


def _load_wordmark_pil():
    try:
        from PIL import Image
        import base64
        from io import BytesIO
        data = base64.b64decode(WORDMARK_B64)
        img = Image.open(BytesIO(data))
        return img
    except Exception:
        return None


def _run_rumps_tray():
    global _menu_instance
    try:
        import rumps
    except ImportError:
        log("rumps not installed, fallback to CLI")
        run_cli()
        return

    class PiKMApp(rumps.App):
        def __init__(self):
            super().__init__("PiKM", icon=_wordmark_path(), template=True, quit_button=None)
            self.menu = [
                rumps.MenuItem(f"PiKM Node v{VERSION}", callback=None),
                None,
                rumps.MenuItem("Quit"),
            ]

        @rumps.clicked("Quit")
        def quit_item(self, _):
            _stop_event.set()
            rumps.quit_application()

    _menu_instance = PiKMApp()
    _menu_instance.run()


def _run_pystray_tray():
    try:
        import pystray
    except ImportError:
        log("pystray not installed, fallback to CLI")
        run_cli()
        return

    icon_img = _load_wordmark_pil()

    def on_quit(icon):
        _stop_event.set()
        icon.stop()

    menu = pystray.Menu(
        pystray.MenuItem(f"PiKM Node v{VERSION}", None, enabled=False),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Quit", on_quit),
    )
    icon = pystray.Icon("PiKM", icon_img, "PiKM Receiver", menu)
    icon.run()


def main():
    global backend

    _setup_logging()

    try:
        backend = create_backend()
    except Exception as e:
        log(f"Backend init failed: {e}", logging.ERROR)
        sys.exit(1)

    log(f"Backend loaded: {type(backend).__module__}")

    has_tray = False
    if sys.platform == "darwin":
        try:
            import rumps  # noqa: F401
            has_tray = True
        except ImportError:
            pass
    elif sys.platform == "win32":
        try:
            import pystray  # noqa: F401
            has_tray = True
        except ImportError:
            pass

    if has_tray and not os.environ.get("PIKM_NO_TRAY"):
        run_tray()
    else:
        run_cli()


if __name__ == "__main__":
    main()
