#!/usr/bin/env python3
"""Talk to the fireplace directly with the integration's own client: print the full
DP status, then send each JSON argument as a control command and print every frame
the device sends back. The local key comes from $LK (never pass it as an argument).

usage: LK=... python3 probe.py <host> <device id> ['{"1":true}' '{"103":"1h"}' ...]
"""
import asyncio
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "custom_components/in_flames"))
import tuya_local as t  # noqa: E402


async def main() -> None:
    host, device_id, *steps = sys.argv[1:]
    dev = t.TuyaDevice(host, device_id, os.environ["LK"])
    await dev.connect()
    loop = asyncio.get_running_loop()

    async def drain(seconds: float) -> None:
        end = loop.time() + seconds
        while (left := end - loop.time()) > 0:
            try:
                cmd, payload = await asyncio.wait_for(dev._read_frame(), left)
            except TimeoutError:
                return
            raw = t._decrypt(dev._session_key, payload) if payload else b""
            if raw.startswith(b"3.4"):
                raw = raw[len(t.VERSION_HEADER):]
            if raw:
                print(f"  <- {cmd:#04x} {raw.decode(errors='replace')}")

    await dev.query()
    await drain(2)
    for step in steps:
        dps = json.loads(step)
        print("->", dps)
        await dev.set_dps(dps)
        await drain(5)
    await dev._close()


asyncio.run(main())
