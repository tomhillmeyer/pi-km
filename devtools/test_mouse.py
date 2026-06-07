#!/usr/bin/env python3
"""
Test mouse scenarios against a running node.
Usage:
  python3 devtools/test_mouse.py <host>
"""

import socket
import struct
import sys
import time


def send(conn, msg_type, report):
    conn.sendall(bytes([msg_type]) + report)


def main():
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <host>")
        sys.exit(1)

    host = sys.argv[1]

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(5)
        s.connect((host, 9876))
        print(f"Connected to {host}:9876")

        print("Moving mouse right 50px...")
        report = struct.pack("4b", 0x00, 50, 0, 0)
        send(s, 0x02, report)
        time.sleep(0.3)

        print("Moving mouse down 50px...")
        report = struct.pack("4b", 0x00, 0, 50, 0)
        send(s, 0x02, report)
        time.sleep(0.3)

        print("Left click...")
        report = struct.pack("4b", 0x01, 0, 0, 0)
        send(s, 0x02, report)
        time.sleep(0.1)
        report = struct.pack("4b", 0x00, 0, 0, 0)
        send(s, 0x02, report)
        time.sleep(0.3)

        print("Scroll down 3 clicks...")
        report = struct.pack("4b", 0x00, 0, 0, -3)
        send(s, 0x02, report)
        time.sleep(0.3)

        print("Scroll up 2 clicks...")
        report = struct.pack("4b", 0x00, 0, 0, 2)
        send(s, 0x02, report)
        time.sleep(0.3)

        print("Done.")


if __name__ == "__main__":
    main()
