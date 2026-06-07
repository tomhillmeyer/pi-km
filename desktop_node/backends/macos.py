import struct
import time
import logging
from ..keymap import HID_TO_MAC, MAC_MOD_FLAGS, HID_CONSUMER_TO_MAC_NX

try:
    import Quartz
    import AppKit
    OBJC_AVAILABLE = True
except ImportError:
    OBJC_AVAILABLE = False

log = logging.getLogger("pikm.macos")


def _caps_lock_toggle():
    import subprocess
    subprocess.run(
        ["osascript", "-e", 'tell application "System Events" to key code 57'],
        capture_output=True,
    )


def init():
    if not OBJC_AVAILABLE:
        raise RuntimeError("PyObjC not available (Quartz/AppKit)")


def _build_cg_flags(mod_byte: int) -> int:
    flags = 0
    for bit, cf in MAC_MOD_FLAGS.items():
        if mod_byte & bit:
            flags |= cf
    return flags


def _mod_bit_to_keycode(bit: int):
    if bit == 0x01:
        return 0x3B
    if bit == 0x02:
        return 0x38
    if bit == 0x04:
        return 0x3A
    if bit == 0x08:
        return 0x37
    if bit == 0x10:
        return 0x3E
    if bit == 0x20:
        return 0x3C
    if bit == 0x40:
        return 0x3D
    if bit == 0x80:
        return 0x37
    return None


def _post_key(keycode: int, is_down: bool, cg_flags: int = 0):
    event = Quartz.CGEventCreateKeyboardEvent(None, keycode, is_down)
    if cg_flags:
        Quartz.CGEventSetFlags(event, cg_flags)
    Quartz.CGEventPost(Quartz.kCGHIDEventTap, event)


def keyboard_report(report: bytes):
    mod_byte = report[0]
    keys = report[2:]

    old_mods = getattr(keyboard_report, "_old_mods", 0)
    old_keys = getattr(keyboard_report, "_old_keys", b'\x00' * 6)

    cg_flags = _build_cg_flags(mod_byte)

    changed_mods = old_mods ^ mod_byte
    for bit in [0x01, 0x02, 0x04, 0x08, 0x10, 0x20, 0x40, 0x80]:
        if changed_mods & bit:
            is_down = bool(mod_byte & bit)
            kc = _mod_bit_to_keycode(bit)
            if kc is not None:
                _post_key(kc, is_down, cg_flags if is_down else 0)

    old_set = set(old_keys)
    new_set = set(keys)

    for hid in old_set - new_set:
        if hid and hid in HID_TO_MAC:
            _post_key(HID_TO_MAC[hid], False)

    for hid in new_set - old_set:
        if hid and hid in HID_TO_MAC:
            _post_key(HID_TO_MAC[hid], True, cg_flags)

    keyboard_report._old_mods = mod_byte
    keyboard_report._old_keys = keys


def mouse_report(report: bytes):
    buttons, dx, dy, scroll = struct.unpack("4b", report)
    old_buttons = getattr(mouse_report, "_old_buttons", 0)

    if dx or dy:
        current = Quartz.CGEventGetLocation(
            Quartz.CGEventCreate(None)
        )
        x = max(0, current.x + dx)
        y = max(0, current.y + dy)
        event_type = Quartz.kCGEventMouseMoved
        if buttons & 0x01:
            event_type = Quartz.kCGEventLeftMouseDragged
        elif buttons & 0x02:
            event_type = Quartz.kCGEventRightMouseDragged
        event = Quartz.CGEventCreateMouseEvent(
            None, event_type, Quartz.CGPoint(x, y), Quartz.kCGMouseButtonLeft,
        )
        if buttons & 0x02:
            Quartz.CGEventSetIntegerValueField(
                event, Quartz.kCGMouseEventButtonNumber, 1
            )
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, event)

    if scroll:
        event = Quartz.CGEventCreateScrollWheelEvent(
            None, Quartz.kCGScrollEventUnitLine, 1, scroll
        )
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, event)

    for i, btn_flag in enumerate([0x01, 0x02, 0x04]):
        was = old_buttons & btn_flag
        now = buttons & btn_flag
        if was and not now:
            _mouse_click(i, False)
        elif not was and now:
            _mouse_click(i, True)

    mouse_report._old_buttons = buttons


def _mouse_click(btn_index: int, down: bool):
    button = Quartz.kCGMouseButtonLeft
    if btn_index == 1:
        button = Quartz.kCGMouseButtonRight
    elif btn_index == 2:
        button = Quartz.kCGMouseButtonCenter

    event_type = {
        0: Quartz.kCGEventLeftMouseDown if down else Quartz.kCGEventLeftMouseUp,
        1: Quartz.kCGEventRightMouseDown if down else Quartz.kCGEventRightMouseUp,
        2: Quartz.kCGEventOtherMouseDown if down else Quartz.kCGEventOtherMouseUp,
    }[btn_index]

    current = Quartz.CGEventGetLocation(Quartz.CGEventCreate(None))
    event = Quartz.CGEventCreateMouseEvent(None, event_type, current, button)
    if btn_index == 2:
        Quartz.CGEventSetIntegerValueField(event, Quartz.kCGMouseEventButtonNumber, 2)

    if btn_index == 0:
        now = time.time()
        if down:
            last = getattr(_mouse_click, "_last_click", None)
            click_count = getattr(_mouse_click, "_click_count", 1)
            if last is not None:
                last_time, last_pos = last
                dt = now - last_time
                dx = current.x - last_pos.x
                dy = current.y - last_pos.y
                if dt < 0.5 and (dx * dx + dy * dy) ** 0.5 < 5:
                    click_count += 1
                else:
                    click_count = 1
            else:
                click_count = 1
            _mouse_click._last_click = (now, current)
            _mouse_click._click_count = click_count
        else:
            click_count = getattr(_mouse_click, "_click_count", 1)
        Quartz.CGEventSetIntegerValueField(
            event, Quartz.kCGMouseEventClickState, click_count
        )

    Quartz.CGEventPost(Quartz.kCGHIDEventTap, event)


def consumer_report(report: bytes):
    usage = struct.unpack("<H", report)[0]
    nx_type = HID_CONSUMER_TO_MAC_NX.get(usage)
    if nx_type is None:
        log.warning(f"unknown consumer usage: 0x{usage:04X}")
        return
    for key_state in [0xA, 0xB]:
        data1 = (nx_type << 16) | (key_state << 8)
        ns_event = AppKit.NSEvent.otherEventWithType_location_modifierFlags_timestamp_windowNumber_context_subtype_data1_data2_(
            AppKit.NSSystemDefined,
            AppKit.NSZeroPoint,
            0,
            0,
            0,
            None,
            8,
            data1,
            -1,
        )
        cg_event = ns_event.CGEvent()
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, cg_event)
