import struct
import time
from ..keymap import HID_TO_WIN, HID_CONSUMER_TO_WIN_VK

try:
    import ctypes
    from ctypes import wintypes

    USER32 = ctypes.windll.user32
    PUL = ctypes.POINTER(ctypes.c_ulong)

    class KEYBDINPUT(ctypes.Structure):
        _fields_ = [
            ("wVk", wintypes.WORD),
            ("wScan", wintypes.WORD),
            ("dwFlags", ctypes.c_ulong),
            ("time", ctypes.c_ulong),
            ("dwExtraInfo", PUL),
        ]

    class MOUSEINPUT(ctypes.Structure):
        _fields_ = [
            ("dx", ctypes.c_long),
            ("dy", ctypes.c_long),
            ("mouseData", ctypes.c_ulong),
            ("dwFlags", ctypes.c_ulong),
            ("time", ctypes.c_ulong),
            ("dwExtraInfo", PUL),
        ]

    class INPUT_UNION(ctypes.Union):
        _fields_ = [
            ("mi", MOUSEINPUT),
            ("ki", KEYBDINPUT),
        ]

    class INPUT(ctypes.Structure):
        _fields_ = [
            ("type", ctypes.c_ulong),
            ("u", INPUT_UNION),
        ]

    INPUT_KEYBOARD = 1
    INPUT_MOUSE = 0
    KEYEVENTF_KEYUP = 0x0002
    MOUSEEVENTF_MOVE = 0x0001
    MOUSEEVENTF_LEFTDOWN = 0x0002
    MOUSEEVENTF_LEFTUP = 0x0004
    MOUSEEVENTF_RIGHTDOWN = 0x0008
    MOUSEEVENTF_RIGHTUP = 0x0010
    MOUSEEVENTF_MIDDLEDOWN = 0x0020
    MOUSEEVENTF_MIDDLEUP = 0x0040
    MOUSEEVENTF_WHEEL = 0x0800

    WINAPI_AVAILABLE = True
except Exception:
    WINAPI_AVAILABLE = False

_last_mouse_state = 0


def init():
    if not WINAPI_AVAILABLE:
        raise RuntimeError("Windows API not available")
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        pass


def _caps_lock_toggle():
    pass


def keyboard_report(report: bytes):
    mod_byte = report[0]
    keys = report[2:]

    old_mods = getattr(keyboard_report, "_old_mods", 0)
    old_keys = getattr(keyboard_report, "_old_keys", b'\x00' * 6)

    mod_changes = []
    for bit in [0x01, 0x02, 0x04, 0x08, 0x10, 0x20, 0x40, 0x80]:
        if (old_mods & bit) and not (mod_byte & bit):
            vk = _mod_hid_to_vk(bit)
            if vk:
                mod_changes.append((vk, False))
        elif not (old_mods & bit) and (mod_byte & bit):
            vk = _mod_hid_to_vk(bit)
            if vk:
                mod_changes.append((vk, True))

    for vk, down in mod_changes:
        _send_key(vk, down)

    old_set = set(old_keys)
    new_set = set(keys)

    for hid in old_set - new_set:
        if hid and hid in HID_TO_WIN:
            _send_key(HID_TO_WIN[hid], False)

    for hid in new_set - old_set:
        if hid and hid in HID_TO_WIN:
            _send_key(HID_TO_WIN[hid], True)

    keyboard_report._old_mods = mod_byte
    keyboard_report._old_keys = keys


def _mod_hid_to_vk(bit):
    if bit == 0x01:
        return 0xA2
    elif bit == 0x02:
        return 0xA0
    elif bit == 0x04:
        return 0xA4
    elif bit == 0x08:
        return 0x5B
    elif bit == 0x10:
        return 0xA3
    elif bit == 0x20:
        return 0xA1
    elif bit == 0x40:
        return 0xA5
    elif bit == 0x80:
        return 0x5C
    return None


def _send_key(vk: int, down: bool):
    inp = INPUT(INPUT_KEYBOARD)
    inp.u.ki = KEYBDINPUT(vk, 0, 0 if down else KEYEVENTF_KEYUP, 0, None)
    USER32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(inp))


def mouse_report(report: bytes):
    global _last_mouse_state
    buttons, dx, dy, scroll = struct.unpack("4b", report)

    if dx or dy:
        inp = INPUT(INPUT_MOUSE)
        inp.u.mi = MOUSEINPUT(dx, dy, 0, MOUSEEVENTF_MOVE, 0, None)
        USER32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(inp))

    if scroll:
        inp = INPUT(INPUT_MOUSE)
        inp.u.mi = MOUSEINPUT(0, 0, scroll << 16, MOUSEEVENTF_WHEEL, 0, None)
        USER32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(inp))

    old_buttons = _last_mouse_state
    _last_mouse_state = buttons

    btn_map = [
        (0x01, MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP),
        (0x02, MOUSEEVENTF_RIGHTDOWN, MOUSEEVENTF_RIGHTUP),
        (0x04, MOUSEEVENTF_MIDDLEDOWN, MOUSEEVENTF_MIDDLEUP),
    ]
    for btn_bit, down_flag, up_flag in btn_map:
        was = old_buttons & btn_bit
        now = buttons & btn_bit
        if was and not now:
            _send_mouse_button(up_flag)
        elif not was and now:
            _send_mouse_button(down_flag)


def _send_mouse_button(flag: int):
    inp = INPUT(INPUT_MOUSE)
    inp.u.mi = MOUSEINPUT(0, 0, 0, flag, 0, None)
    USER32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(inp))


def consumer_report(report: bytes):
    usage = struct.unpack("<H", report)[0]
    vk = HID_CONSUMER_TO_WIN_VK.get(usage)
    if vk is None:
        return
    _send_key(vk, True)
    time.sleep(0.02)
    _send_key(vk, False)
