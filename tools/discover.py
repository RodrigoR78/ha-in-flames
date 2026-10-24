#!/usr/bin/env python3
"""Listen for Tuya LAN discovery broadcasts (UDP 6666/6667) and print each device's
IP, device id, product key and protocol version. Needs no keys: v3.3/3.4 broadcasts
are encrypted with a fixed, publicly known key.

usage: python3 discover.py [seconds]
"""
import hashlib
import json
import socket
import sys
import time

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

UDP_KEY = hashlib.md5(b"yGAdlopoPVldABfn").digest()


def decrypt(data: bytes) -> dict | None:
    payload = data[20:-8]  # strip header (+retcode) and crc/suffix
    try:
        dec = Cipher(algorithms.AES(UDP_KEY), modes.ECB()).decryptor()
        raw = dec.update(payload) + dec.finalize()
        return json.loads(raw[: -raw[-1]])
    except Exception:
        try:
            return json.loads(data[20:-8])  # v3.1 broadcasts are plain JSON
        except Exception:
            return None


def main() -> None:
    seconds = float(sys.argv[1]) if len(sys.argv) > 1 else 15
    socks = []
    for port in (6666, 6667):
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(("", port))
        s.settimeout(0.5)
        socks.append(s)
    seen = set()
    end = time.time() + seconds
    while time.time() < end:
        for s in socks:
            try:
                data, (ip, _) = s.recvfrom(4096)
            except socket.timeout:
                continue
            info = decrypt(data)
            if info and ip not in seen:
                seen.add(ip)
                print(f"{ip}  id={info.get('gwId')}  product={info.get('productKey')}  version={info.get('version')}")
    if not seen:
        print("no broadcasts heard - is this host on the same L2 segment as the device?")


if __name__ == "__main__":
    main()
