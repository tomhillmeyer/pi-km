#!/usr/bin/env python3
"""
Test keyboard scenarios against a running node.
Usage:
  python3 devtools/test_keyboard.py <host>
"""

import socket
import struct
import sys
import time


def send(conn, msg_type, report):
    conn.sendall(bytes([msg_type]) + report)


def type_string(conn, text):
    hid = {
        'a': 0x04, 'b': 0x05, 'c': 0x06, 'd': 0x07, 'e': 0x08,
        'f': 0x09, 'g': 0x0a, 'h': 0x0b, 'i': 0x0c, 'j': 0x0d,
        'k': 0x0e, 'l': 0x0f, 'm': 0x10, 'n': 0x11, 'o': 0x12,
        'p': 0x13, 'q': 0x14, 'r': 0x15, 's': 0x16, 't': 0x17,
        'u': 0x18, 'v': 0x19, 'w': 0x1a, 'x': 0x1b, 'y': 0x1c,
        'z': 0x1d,
        '1': 0x1e, '2': 0x1f, '3': 0x20, '4': 0x21, '5': 0x22,
        '6': 0x23, '7': 0x24, '8': 0x25, '9': 0x26, '0': 0x27,
        ' ': 0x2c, '\n': 0x28,
    }
    shift_needed = set('ABCDEFGHIJKLMNOPQRSTUVWXYZ!@#$%^&*()_+{}|:"<>?~')
    for ch in text:
        h = hid.get(ch.lower())
        if h is None:
            continue
        mod = 0x02 if ch in shift_needed else 0x00
        report = struct.pack("8B", mod, 0x00, h, 0, 0, 0, 0, 0)
        send(conn, 0x01, report)
        time.sleep(0.05)
        send(conn, 0x01, struct.pack("8B", 0, 0, 0, 0, 0, 0, 0, 0))
        time.sleep(0.03)


def main():
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <host>")
        sys.exit(1)

    host = sys.argv[1]

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(5)
        s.connect((host, 9876))
        print(f"Connected to {host}:9876")

        print("Testing letters a-z...")
        type_string(s, "hello world from pikm node test")
        time.sleep(0.5)

        print("Testing volume keys...")
        for hid in [0x7F, 0x80, 0x81]:
            report = struct.pack("8B", 0, 0, hid, 0, 0, 0, 0, 0)
            send(s, 0x01, report)
            time.sleep(0.1)
            send(s, 0x01, struct.pack("8B", 0, 0, 0, 0, 0, 0, 0, 0))
            time.sleep(0.3)

        print("Testing consumer keys (media)...")
        for hid in [0x00CD, 0x00B5, 0x00B6]:
            send(s, 0x03, struct.pack("<H", hid))
            time.sleep(0.5)

        print("Done.")


if __name__ == "__main__":
    main()
