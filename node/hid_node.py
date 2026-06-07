#!/usr/bin/env python3
"""
HID Node — listens for forwarded keyboard/mouse events and writes to USB gadget.
Runs on each Pi Zero W.
"""

import socket
import struct

HOST = "0.0.0.0"
PORT = 9876

KEYBOARD_DEVICE = "/dev/hidg0"
MOUSE_DEVICE    = "/dev/hidg1"

def write_keyboard(report: bytes):
    with open(KEYBOARD_DEVICE, "rb+") as f:
        f.write(report)

def write_mouse(report: bytes):
    with open(MOUSE_DEVICE, "rb+") as f:
        f.write(report)

def recv_exact(conn, n):
    data = bytearray()
    while len(data) < n:
        chunk = conn.recv(n - len(data))
        if not chunk:
            return None
        data.extend(chunk)
    return bytes(data)

def handle_connection(conn):
    with conn:
        write_keyboard(bytes(8))
        write_mouse(bytes(4))
        while True:
            type_byte = recv_exact(conn, 1)
            if type_byte is None:
                break
            msg_type = type_byte[0]
            if msg_type == 0x01:
                report = recv_exact(conn, 8)
                if report is None:
                    break
                write_keyboard(report)
            elif msg_type == 0x02:
                report = recv_exact(conn, 4)
                if report is None:
                    break
                write_mouse(report)

def main():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind((HOST, PORT))
        s.listen()
        print(f"HID node listening on {PORT}")
        while True:
            conn, addr = s.accept()
            print(f"Connection from {addr}")
            handle_connection(conn)
            print(f"Connection from {addr} closed")

if __name__ == "__main__":
    main()
