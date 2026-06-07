#!/usr/bin/env python3
"""
Node test tool — sends raw protocol reports to a running PiKM node.
Usage:
  python3 devtools/send_report.py <host> [type] [params]

  type 0x01 (keyboard):  python3 devtools/send_report.py localhost 0x01 0x00 0x00 0x04 ...
  type 0x02 (mouse):     python3 devtools/send_report.py localhost 0x02 0x00 0x0A 0x00 0x00
  type 0x03 (consumer):  python3 devtools/send_report.py localhost 0x03 0xCD 0x00
"""

import socket
import sys


def main():
    if len(sys.argv) < 4:
        print(__doc__)
        sys.exit(1)

    host = sys.argv[1]
    msg_type = int(sys.argv[2], 0)
    data = bytes(int(x, 0) for x in sys.argv[3:])

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(3)
        s.connect((host, 9876))
        s.sendall(bytes([msg_type]) + data)
        print(f"Sent type=0x{msg_type:02x} data={data.hex()} to {host}:9876")


if __name__ == "__main__":
    main()
